# Copyright (c) 2025, bhumika.d@stackerbee.com and contributors
# For license information, please see license.txt

import json
from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, nowdate, getdate

class StockTaking(Document):


    def before_cancel(self, method=None):
        """
        Cancel/delete Delivery Notes created from this Stock Taking.
        """
        delivery_notes = frappe.get_all(
            "Delivery Note",
            filters={
                "custom_stock_taking": self.name,
            },
            pluck="name",
        )

        for dn_name in delivery_notes:
            dn = frappe.get_doc("Delivery Note", dn_name)

            if dn.docstatus == 1:
                dn.cancel()
            elif dn.docstatus == 0:
                frappe.delete_doc(
                    "Delivery Note",
                    dn.name,
                    ignore_permissions=True,
                )


    def before_submit(self, method=None):
        if not self.company:
            frappe.throw(_("Company is mandatory."))

        customer = get_stock_taking_customer(
            self.company
        )

        if not customer:
            frappe.throw(
                _(
                    "Customer is not configured for Company {0} in Stock Taking Settings."
                ).format(self.company)
        )


    def on_submit(self, method=None):
        """
        Process Stock Taking after submit.
        """
        frappe.enqueue(
            "stock_taking.stock_taking.doctype.stock_taking.stock_taking.process_stock_taking",
            stock_taking_name=self.name,
            queue="short",
            timeout=900,
            enqueue_after_commit=True,
            job_name=f"Process Stock Taking {self.name}",
        )


@frappe.whitelist()
def scan_barcode(code, warehouses=None):
	"""
	Scan Serial No / Item Barcode / Item Code.

	For non-serialized items:
	- Returns actual Bin qty for selected warehouses.
	- If item is not available in selected warehouse, still returns success.
	"""

	try:
		code = (code or "").strip()

		if not code:
			return {
				"success": False,
				"message": _("Barcode is required."),
			}

		if isinstance(warehouses, str):
			warehouses = frappe.parse_json(warehouses)

		warehouses = warehouses or []

		# ---------------------------------------------------------
		# SERIAL NUMBER
		# ---------------------------------------------------------
		if frappe.db.exists("Serial No", code):
			serial = frappe.get_doc("Serial No", code)

			serial_warehouse = serial.warehouse or ""
			status = serial.status or ""

			in_selected_warehouse = (
				serial_warehouse in warehouses
				if warehouses
				else False
			)

			is_delivered = status == "Delivered"

			return {
				"success": True,
				"type": "serial",
				"result": {
					"name": serial.name,
					"item_code": serial.item_code,
					"warehouse": serial_warehouse,
					"status": status,
					"in_selected_warehouse": in_selected_warehouse,
					"is_diff_warehouse_row": (
						1
						if not in_selected_warehouse and not is_delivered
						else 0
					),
					"is_delivered_row": 1 if is_delivered else 0,
				},
			}

		# ---------------------------------------------------------
		# ITEM BARCODE
		# ---------------------------------------------------------
		item_code = frappe.db.get_value(
			"Item Barcode",
			{"barcode": code},
			"parent",
		)

		# ---------------------------------------------------------
		# ITEM CODE
		# ---------------------------------------------------------
		if not item_code and frappe.db.exists("Item", code):
			item_code = code

		if not item_code:
			return {
				"success": False,
				"message": _("No Serial Number or Item found for {0}.").format(
					frappe.bold(code)
				),
			}

		item_name = frappe.db.get_value(
			"Item",
			item_code,
			"item_name",
		)

		has_serial_no = frappe.db.get_value(
			"Item",
			item_code,
			"has_serial_no",
		)

		result = []

		for warehouse in warehouses:
			actual_qty = frappe.db.get_value(
				"Bin",
				{
					"item_code": item_code,
					"warehouse": warehouse,
				},
				"actual_qty",
			)

			actual_qty = flt(actual_qty or 0)

			result.append(
				{
					"item_code": item_code,
					"item_name": item_name,
					"warehouse": warehouse,
					"actual_qty": actual_qty,
					"has_serial_no": 1 if has_serial_no else 0,

					# Selected warehouse has zero stock.
					"is_diff_warehouse_row": (
						1 if actual_qty <= 0 else 0
					),

					"is_delivered_row": 0,
				}
			)

		# No warehouse selected on backend.
		if not result:
			result.append(
				{
					"item_code": item_code,
					"item_name": item_name,
					"warehouse": "",
					"actual_qty": 0,
					"has_serial_no": 1 if has_serial_no else 0,
					"is_diff_warehouse_row": 0,
					"is_delivered_row": 0,
				}
			)

		return {
			"success": True,
			"type": "item",
			"result": result,
		}

	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			"Stock Taking - scan_barcode",
		)

		return {
			"success": False,
			"message": _("Unable to process scan."),
		}


def process_stock_taking(stock_taking_name):
	"""
	Main Stock Taking processing.

	Flow:
	1. Analyze stock.
	2. Create Return DN first.
	3. Create Normal DN second.
	4. Both remain Draft.
	5. Return DN gets linked to Normal DN after Normal DN submit.
	"""

	try:
		st = frappe.get_doc("Stock Taking", stock_taking_name)

		if st.docstatus != 1:
			return

		warehouse_data = get_stock_taking_warehouse_data(st)

		if not warehouse_data:
			frappe.throw(
				_("No warehouse found in Stock Taking.")
			)

		scanned_items = {}

		for row in st.items or []:
			item_code = row.item_code
			warehouse = row.warehouse

			if not item_code or not warehouse:
				continue

			physical_count = flt(row.physical_count or 0)

			serials = parse_serial_numbers(row.serial_no)

			key = (item_code, warehouse)

			if key not in scanned_items:
				scanned_items[key] = {
					"item_code": item_code,
					"warehouse": warehouse,
					"physical_count": 0,
					"serials": [],
					"is_diff_warehouse_row": 0,
					"is_delivered_row": 0,
				}

			scanned_items[key]["physical_count"] += physical_count

			if serials:
				scanned_items[key]["serials"].extend(serials)

			if flt(row.is_diff_warehouse_row):
				scanned_items[key]["is_diff_warehouse_row"] = 1

			if flt(row.is_delivered_row):
				scanned_items[key]["is_delivered_row"] = 1

		all_issue_items = []
		all_receipt_items = []

		for warehouse in warehouse_data:
			result = analyze_stock_taking(
				stock_taking=st,
				warehouse=warehouse,
				scanned_items=scanned_items,
			)

			all_issue_items.extend(
				result.get("issue_items") or []
			)

			all_receipt_items.extend(
				result.get("receipt_items") or []
			)

		# Remove duplicate issue rows.
		all_issue_items = merge_issue_items(
			all_issue_items
		)

		# Remove duplicate receipt rows.
		all_receipt_items = merge_receipt_items(
			all_receipt_items
		)

		# ---------------------------------------------------------
		# DEBUG LOG
		# ---------------------------------------------------------
		frappe.log_error(
			frappe.as_json(
				{
					"stock_taking": stock_taking_name,
					"issue_items_count": len(all_issue_items),
					"receipt_items_count": len(all_receipt_items),
					"issue_items": all_issue_items,
					"receipt_items": all_receipt_items,
				},
				indent=2,
			),
			f"Stock Taking DN Debug - {stock_taking_name}",
		)

		return_dn = None
		normal_dn = None

		# ---------------------------------------------------------
		# RETURN DN FIRST
		# ---------------------------------------------------------
		if all_receipt_items:
			return_dn = create_delivery_note_return(
				stock_taking=st,
				items=all_receipt_items,
			)

		# ---------------------------------------------------------
		# NORMAL DN SECOND
		# ---------------------------------------------------------
		if all_issue_items:
			normal_dn = create_delivery_note(
				stock_taking=st,
				items=all_issue_items,
			)

		frappe.db.commit()

		frappe.publish_realtime(
			"stock_taking_complete",
			{
				"stock_taking": stock_taking_name,
				"return_delivery_note": (
					return_dn.name
					if return_dn
					else None
				),
				"delivery_note": (
					normal_dn.name
					if normal_dn
					else None
				),
			},
		)

	except Exception:
		frappe.db.rollback()

		frappe.log_error(
			frappe.get_traceback(),
			f"Stock Taking Processing Failed - {stock_taking_name}",
		)

		frappe.publish_realtime(
			"stock_taking_failed",
			{
				"stock_taking": stock_taking_name,
				"message": _("Stock Taking processing failed."),
			},
		)

		raise


def get_stock_taking_warehouse_data(stock_taking):
	"""
	Get unique warehouses from Stock Taking warehouse child table.
	"""

	warehouses = []

	for row in stock_taking.warehouse or []:
		warehouse = (
			row.warehuose
			or row.warehouse
		)

		if warehouse and warehouse not in warehouses:
			warehouses.append(warehouse)

	return warehouses


def parse_serial_numbers(value):
	if not value:
		return []

	if isinstance(value, list):
		return [
			str(x).strip()
			for x in value
			if str(x).strip()
		]

	return [
		x.strip()
		for x in str(value).replace(",", "\n").splitlines()
		if x.strip()
	]


def analyze_stock_taking(
	stock_taking,
	warehouse,
	scanned_items,
):
	"""
	Compare system stock with physical stock.

	Issue:
	System > Physical

	Receipt:
	Physical > System

	Serialized:
	Active serials missing from scan = Issue.
	Scanned serial not active in selected warehouse = Receipt.
	"""

	issue_items = []
	receipt_items = []

	# ---------------------------------------------------------
	# SYSTEM SERIALS
	# ---------------------------------------------------------
	system_serial_rows = frappe.get_all(
		"Serial No",
		filters={
			"warehouse": warehouse,
			"status": "Active",
		},
		fields=[
			"name",
			"item_code",
			"warehouse",
		],
	)

	system_serials_by_item = {}

	for serial in system_serial_rows:
		system_serials_by_item.setdefault(
			serial.item_code,
			[],
		).append(serial.name)

	# ---------------------------------------------------------
	# SCANNED DATA
	# ---------------------------------------------------------
	warehouse_scanned = {
		key: value
		for key, value in scanned_items.items()
		if key[1] == warehouse
	}

	# ---------------------------------------------------------
	# SERIALIZED ITEMS
	# ---------------------------------------------------------
	for item_code, system_serials in system_serials_by_item.items():

		key = (item_code, warehouse)

		scanned_data = warehouse_scanned.get(
			key,
			{},
		)

		scanned_serials = set(
			scanned_data.get("serials") or []
		)

		# Missing system serials -> Issue DN
		for serial_no in system_serials:
			if serial_no not in scanned_serials:
				issue_items.append(
					{
						"item_code": item_code,
						"warehouse": warehouse,
						"qty": 1,
						"serial_no": serial_no,
					}
				)

	# ---------------------------------------------------------
	# SCANNED SERIALS
	# ---------------------------------------------------------
	for key, scanned_data in warehouse_scanned.items():

		item_code, selected_warehouse = key

		scanned_serials = list(
			dict.fromkeys(
				scanned_data.get("serials") or []
			)
		)

		if not scanned_serials:
			continue

		for serial_no in scanned_serials:

			serial_data = frappe.db.get_value(
				"Serial No",
				serial_no,
				[
					"item_code",
					"warehouse",
					"status",
				],
				as_dict=True,
			)

			if not serial_data:
				continue

			serial_warehouse = (
				serial_data.warehouse or ""
			)

			status = serial_data.status or ""

			is_active_here = (
				status == "Active"
				and serial_warehouse == selected_warehouse
			)

			# Delivered or serial from another warehouse
			# => Receipt DN
			if not is_active_here:
				receipt_items.append(
					{
						"item_code": item_code,
						"warehouse": selected_warehouse,
						"qty": 1,
						"serial_no": serial_no,
					}
				)

	# ---------------------------------------------------------
	# NON SERIALIZED ITEMS
	# ---------------------------------------------------------
	non_serial_items = frappe.get_all(
		"Item",
		filters={
			"has_serial_no": 0,
			"disabled": 0,
		},
		pluck="name",
	)

	for item_code in non_serial_items:

		bin_qty = frappe.db.get_value(
			"Bin",
			{
				"item_code": item_code,
				"warehouse": warehouse,
			},
			"actual_qty",
		)

		bin_qty = flt(bin_qty or 0)

		key = (item_code, warehouse)

		scanned_data = warehouse_scanned.get(
			key,
			{},
		)

		physical_count = flt(
			scanned_data.get("physical_count") or 0
		)

		# Do not create zero/zero DN.
		if bin_qty == physical_count:
			continue

		# System stock > Physical stock
		if bin_qty > physical_count:
			issue_items.append(
				{
					"item_code": item_code,
					"warehouse": warehouse,
					"qty": bin_qty - physical_count,
					"serial_no": "",
				}
			)

		# Physical stock > System stock
		elif physical_count > bin_qty:
			receipt_items.append(
				{
					"item_code": item_code,
					"warehouse": warehouse,
					"qty": physical_count - bin_qty,
					"serial_no": "",
				}
			)

	return {
		"issue_items": issue_items,
		"receipt_items": receipt_items,
	}


def merge_issue_items(items):
	"""
	Merge issue rows by item + warehouse + serial.
	"""

	merged = {}

	for row in items:
		item_code = row.get("item_code")
		warehouse = row.get("warehouse")
		serial_no = row.get("serial_no") or ""

		if not item_code or not warehouse:
			continue

		key = (
			item_code,
			warehouse,
			serial_no,
		)

		if key not in merged:
			merged[key] = {
				"item_code": item_code,
				"warehouse": warehouse,
				"qty": 0,
				"serial_no": serial_no,
			}

		merged[key]["qty"] += flt(
			row.get("qty") or 0
		)

	return list(merged.values())


def merge_receipt_items(items):
	"""
	Merge receipt rows.

	Serialized:
	Keep serial numbers together.

	Non-serialized:
	Merge quantities.
	"""

	merged = {}

	for row in items:
		item_code = row.get("item_code")
		warehouse = row.get("warehouse")
		serial_no = row.get("serial_no") or ""

		if not item_code or not warehouse:
			continue

		key = (
			item_code,
			warehouse,
		)

		if key not in merged:
			merged[key] = {
				"item_code": item_code,
				"warehouse": warehouse,
				"qty": 0,
				"serial_no": "",
			}

		merged[key]["qty"] += flt(
			row.get("qty") or 0
		)

		if serial_no:
			existing = parse_serial_numbers(
				merged[key]["serial_no"]
			)

			if serial_no not in existing:
				existing.append(serial_no)

			merged[key]["serial_no"] = "\n".join(
				existing
			)

	return list(merged.values())


def get_item_delivery_rate_map(item_codes):
	"""
	MRP priority:

	1. Opening Stock Reconciliation valuation rate
	2. Item Price MRP
	3. Purchase Receipt Item base_price_list_rate
	4. 0
	"""

	result = {}

	if not item_codes:
		return result

	for item_code in item_codes:

		rate = None

		# -----------------------------------------------------
		# 1. OPENING STOCK
		# -----------------------------------------------------
		rate = frappe.db.sql(
			"""
			SELECT sed.valuation_rate
			FROM `tabStock Reconciliation` sr
			INNER JOIN `tabStock Reconciliation Item` sed
				ON sed.parent = sr.name
			WHERE
				sr.docstatus = 1
				AND sr.purpose = 'Opening Stock'
				AND sed.item_code = %s
				AND sed.valuation_rate IS NOT NULL
				AND sed.valuation_rate > 0
			ORDER BY
				sr.posting_date DESC,
				sr.posting_time DESC,
				sr.modified DESC
			LIMIT 1
			""",
			(item_code,),
			as_dict=True,
		)

		if rate:
			result[item_code] = flt(
				rate[0].valuation_rate
			)
			continue

		# -----------------------------------------------------
		# 2. ITEM PRICE MRP
		# -----------------------------------------------------
		rate = frappe.db.sql(
			"""
			SELECT price_list_rate
			FROM `tabItem Price`
			WHERE
				item_code = %s
				AND price_list = 'MRP'
				AND price_list_rate IS NOT NULL
				AND price_list_rate > 0
			ORDER BY
				modified DESC
			LIMIT 1
			""",
			(item_code,),
			as_dict=True,
		)

		if rate:
			result[item_code] = flt(
				rate[0].price_list_rate
			)
			continue

		# -----------------------------------------------------
		# 3. PURCHASE RECEIPT
		# -----------------------------------------------------
		rate = frappe.db.sql(
			"""
			SELECT pri.base_price_list_rate
			FROM `tabPurchase Receipt Item` pri
			INNER JOIN `tabPurchase Receipt` pr
				ON pr.name = pri.parent
			WHERE
				pr.docstatus = 1
				AND pri.item_code = %s
				AND pri.base_price_list_rate IS NOT NULL
				AND pri.base_price_list_rate > 0
			ORDER BY
				pr.posting_date DESC,
				pr.posting_time DESC,
				pr.modified DESC
			LIMIT 1
			""",
			(item_code,),
			as_dict=True,
		)

		if rate:
			result[item_code] = flt(
				rate[0].base_price_list_rate
			)
			continue

		result[item_code] = 0

	return result



def get_item_tax_template_for_item(
	item_code,
	company,
):
	"""
	Get Item Tax Template configured on Item
	and ensure it belongs to the current Company.
	"""

	if not item_code:
		return None

	tax_template = frappe.db.get_value(
		"Item Tax",
		{
			"parent": item_code,
			"parenttype": "Item",
			"parentfield": "taxes",
			"item_tax_template": ["is", "set"],
		},
		"item_tax_template",
		order_by="idx asc",
	)

	if not tax_template:
		return None

	template_company = frappe.db.get_value(
		"Item Tax Template",
		tax_template,
		"company",
	)

	if company and template_company and template_company != company:
		return None

	return tax_template


def get_stock_taking_customer(company):
	"""
	Get Customer from Stock Taking Settings
	based on Company.
	"""

	if not company:
		return None

	if not frappe.db.exists(
		"DocType",
		"Stock Taking Settings",
	):
		return None

	customer = frappe.db.get_value(
		"Stock Taking Customer",
		{
			"parent": "Stock Taking Settings",
			"parenttype": "Stock Taking Settings",
			"company": company,
		},
		"customer",
	)

	return customer

def create_delivery_note(
	stock_taking,
	items,
):
	"""
	Create NORMAL Delivery Note in Draft.
	"""

	customer = get_stock_taking_customer(
        stock_taking.company
    )

	if not customer:
		frappe.throw(
			_("Customer is not configured in Stock Taking Settings.")
		)

	if not items:
		return None

	company = stock_taking.company

	abbr = frappe.db.get_value(
		"Company",
		company,
		"abbr",
	)

	item_codes = list(
		{
			row["item_code"]
			for row in items
			if row.get("item_code")
		}
	)

	mrp_map = get_item_delivery_rate_map(
		item_codes
	)

	dn = frappe.new_doc("Delivery Note")

	dn.customer = customer
	dn.company = company
	dn.is_return = 0
	dn.return_against = None
	dn.posting_date = getdate() or nowdate()
	dn.set_posting_time = 1
	dn.custom_stock_taking = stock_taking.name
	dn.custom_abbr = abbr

	for row in items:

		qty = flt(row.get("qty") or 0)

		if qty <= 0:
			continue

		item_code = row.get("item_code")
		warehouse = row.get("warehouse")

		if not item_code or not warehouse:
			continue

		dn_item = dn.append(
			"items",
			{},
		)

		dn_item.item_code = item_code
		dn_item.warehouse = warehouse
		dn_item.qty = abs(qty)
		dn_item.uom = frappe.db.get_value(
			"Item",
			item_code,
			"stock_uom",
		)

		dn_item.rate = flt(
			mrp_map.get(item_code) or 0
		)

		dn_item.price_list_rate = flt(
			mrp_map.get(item_code) or 0
		)

		dn_item.custom_mrp = flt(
			mrp_map.get(item_code) or 0
		)

		dn_item.allow_zero_valuation_rate = 1

		serial_no = row.get("serial_no") or ""

		if serial_no:
			dn_item.serial_no = serial_no

		tax_template = get_item_tax_template_for_item(
			item_code,
			company,
		)

		if tax_template:
			dn_item.item_tax_template = tax_template

	# Nothing to insert
	if not dn.items:
		return None

	dn.insert(
		ignore_permissions=True,
		ignore_mandatory=True,
		ignore_links=True,
	)

	return dn

def create_delivery_note_return(
	stock_taking,
	items,
):
	"""
	Create RETURN Delivery Note in Draft.

	- Customer is fetched company-wise from Stock Taking Settings.
	- Return quantity is negative.
	- Rate/MRP remain positive.
	- return_against remains blank initially.
	"""

	customer = get_stock_taking_customer(
		stock_taking.company
	)

	if not customer:
		frappe.throw(
			_(
				"Customer is not configured for Company {0} in Stock Taking Settings."
			).format(stock_taking.company)
		)

	if not items:
		return None

	company = stock_taking.company

	abbr = frappe.db.get_value(
		"Company",
		company,
		"abbr",
	)

	item_codes = list(
		{
			row.get("item_code")
			for row in items
			if row.get("item_code")
		}
	)

	mrp_map = get_item_delivery_rate_map(
		item_codes
	)

	dn = frappe.new_doc("Delivery Note")

	dn.customer = customer
	dn.company = company
	dn.is_return = 1
	dn.return_against = None
	dn.posting_date = getdate()
	dn.set_posting_time = 1
	dn.custom_stock_taking = stock_taking.name
	dn.custom_abbr = abbr

	for row in items:
		qty = flt(
			row.get("qty") or 0
		)

		if qty <= 0:
			continue

		item_code = row.get("item_code")
		warehouse = row.get("warehouse")

		if not item_code or not warehouse:
			continue

		dn_item = dn.append(
			"items",
			{},
		)

		dn_item.item_code = item_code
		dn_item.warehouse = warehouse

		# Return quantity must be negative.
		dn_item.qty = -abs(qty)

		dn_item.uom = frappe.db.get_value(
			"Item",
			item_code,
			"stock_uom",
		)

		# Rate / MRP remain positive.
		dn_item.rate = flt(
			mrp_map.get(item_code) or 0
		)

		dn_item.price_list_rate = flt(
			mrp_map.get(item_code) or 0
		)

		dn_item.custom_mrp = flt(
			mrp_map.get(item_code) or 0
		)

		dn_item.allow_zero_valuation_rate = 1

		serial_no = row.get("serial_no") or ""

		if serial_no:
			dn_item.serial_no = serial_no

		tax_template = get_item_tax_template_for_item(
			item_code,
			company,
		)

		if tax_template:
			dn_item.item_tax_template = tax_template

	if not dn.items:
		return None

	dn.insert(
		ignore_permissions=True,
		ignore_mandatory=True,
		ignore_links=True,
	)

	return dn

def link_return_delivery_note(doc, method=None):
	"""
	After NORMAL Delivery Note is submitted,
	link latest draft RETURN DN of same Stock Taking.
	"""

	if doc.is_return:
		return

	stock_taking = doc.get("custom_stock_taking")

	if not stock_taking:
		return

	return_dn_name = frappe.db.get_value(
		"Delivery Note",
		{
			"custom_stock_taking": stock_taking,
			"is_return": 1,
			"docstatus": 0,
			"return_against": ["is", "not set"],
		},
		"name",
		order_by="creation desc",
	)

	if not return_dn_name:
		return

	frappe.db.set_value(
		"Delivery Note",
		return_dn_name,
		"return_against",
		doc.name,
		update_modified=False,
	)

	frappe.clear_document_cache(
		"Delivery Note",
		return_dn_name,
	)