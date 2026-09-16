# Copyright (c) 2025, bhumika.d@stackerbee.com and contributors
# For license information, please see license.txt

import json
from decimal import Decimal, ROUND_HALF_UP

import frappe
from frappe import _
from frappe.model.document import Document
from datetime import timedelta
from frappe.utils import flt, cint, nowdate, getdate, now_datetime,get_datetime

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

        customer = get_stock_taking_customer(self.company)

        if not customer:
            frappe.throw(
                _("Customer is not configured for Company {0} in Stock Taking Settings.").format(
                    self.company
                )
            )

        self.normal_dn_status = "Pending"
        self.return_dn_status = "Pending"


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
	1. Set both DN statuses to Process.
	2. Analyze stock.
	3. Create Return DN.
	4. Update Return DN status.
	5. Create Normal DN.
	6. Update Normal DN status.
	7. Commit both DNs together.
	8. Notify browser after processing.

	DN Status values:
	- Pending
	- Process
	- Completed
	- Failed
	"""

	# ---------------------------------------------------------
	# INITIAL STATUS
	# ---------------------------------------------------------

	frappe.db.set_value(
		"Stock Taking",
		stock_taking_name,
		{
			"normal_dn_status": "Process",
			"return_dn_status": "Process",
		},
		update_modified=False,
	)

	frappe.db.commit()

	try:
		st = frappe.get_doc(
			"Stock Taking",
			stock_taking_name,
		)

		if st.docstatus != 1:
			return

		warehouse_data = get_stock_taking_warehouse_data(st)

		if not warehouse_data:
			frappe.throw(
				_("No warehouse found in Stock Taking.")
			)

		# ---------------------------------------------------------
		# BUILD SCANNED DATA
		# ---------------------------------------------------------

		scanned_items = {}

		for row in st.items or []:
			item_code = row.item_code
			warehouse = row.warehouse

			if not item_code or not warehouse:
				continue

			physical_count = flt(
				row.physical_count or 0
			)

			serials = parse_serial_numbers(
				row.serial_no
			)

			key = (
				item_code,
				warehouse,
			)

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
				scanned_items[key]["serials"].extend(
					serials
				)

			if flt(row.is_diff_warehouse_row):
				scanned_items[key]["is_diff_warehouse_row"] = 1

			if flt(row.is_delivered_row):
				scanned_items[key]["is_delivered_row"] = 1

		# ---------------------------------------------------------
		# ANALYZE
		# ---------------------------------------------------------

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

		# ---------------------------------------------------------
		# MERGE
		# ---------------------------------------------------------

		all_issue_items = merge_issue_items(
			all_issue_items
		)

		all_receipt_items = merge_receipt_items(
			all_receipt_items
		)

		return_dn = None
		normal_dn = None

		# =========================================================
		# CREATE RETURN DN
		# =========================================================

		if all_receipt_items:

			try:
				return_dn = create_delivery_note_return(
					stock_taking=st,
					items=all_receipt_items,
				)

				if return_dn:
					frappe.db.set_value(
						"Stock Taking",
						stock_taking_name,
						"return_dn_status",
						"Completed",
						update_modified=False,
					)

				else:
					frappe.db.set_value(
						"Stock Taking",
						stock_taking_name,
						"return_dn_status",
						"Failed",
						update_modified=False,
					)

			except Exception:

				frappe.db.set_value(
					"Stock Taking",
					stock_taking_name,
					"return_dn_status",
					"Failed",
					update_modified=False,
				)

				frappe.log_error(
					frappe.get_traceback(),
					f"Return Delivery Note Creation Failed - {stock_taking_name}",
				)

		else:
			# No Return DN required
			frappe.db.set_value(
				"Stock Taking",
				stock_taking_name,
				"return_dn_status",
				"Completed",
				update_modified=False,
			)

		# =========================================================
		# CREATE NORMAL DN
		# =========================================================

		if all_issue_items:

			try:
				normal_dn = create_delivery_note(
					stock_taking=st,
					items=all_issue_items,
				)

				if normal_dn:
					frappe.db.set_value(
						"Stock Taking",
						stock_taking_name,
						"normal_dn_status",
						"Completed",
						update_modified=False,
					)

				else:
					frappe.db.set_value(
						"Stock Taking",
						stock_taking_name,
						"normal_dn_status",
						"Failed",
						update_modified=False,
					)

			except Exception:

				frappe.db.set_value(
					"Stock Taking",
					stock_taking_name,
					"normal_dn_status",
					"Failed",
					update_modified=False,
				)

				frappe.log_error(
					frappe.get_traceback(),
					f"Normal Delivery Note Creation Failed - {stock_taking_name}",
				)

		else:
			# No Normal DN required
			frappe.db.set_value(
				"Stock Taking",
				stock_taking_name,
				"normal_dn_status",
				"Completed",
				update_modified=False,
			)

		# ---------------------------------------------------------
		# STANDALONE RETURN
		#
		# DO NOT AUTO SUBMIT
		# ---------------------------------------------------------

		return_dn_submitted = False

		# IMPORTANT:
		# Return DN manually submit hoga.
		#
		# if return_dn and not normal_dn:
		# 	return_dn.submit()
		# 	return_dn_submitted = True

		# ---------------------------------------------------------
		# SINGLE COMMIT
		#
		# Both DNs + status updates commit together.
		# ---------------------------------------------------------

		frappe.db.commit()

		# ---------------------------------------------------------
		# COMPLETION EVENT
		# ---------------------------------------------------------

		event_data = {
			"stock_taking": stock_taking_name,
		}

		if normal_dn:
			event_data["delivery_note"] = normal_dn.name
			event_data["delivery_note_status"] = "Draft"

		if return_dn:
			event_data["return_delivery_note"] = return_dn.name

			if return_dn_submitted:
				event_data["return_delivery_note_status"] = "Submitted"
			else:
				event_data["return_delivery_note_status"] = "Draft"

		frappe.publish_realtime(
			"stock_taking_complete",
			event_data,
		)

	except Exception:

		frappe.db.rollback()

		# ---------------------------------------------------------
		# OUTER FAILURE
		#
		# This handles failures before individual DN creation,
		# such as analysis / warehouse / scanned data processing.
		# ---------------------------------------------------------

		frappe.db.set_value(
			"Stock Taking",
			stock_taking_name,
			{
				"normal_dn_status": "Failed",
				"return_dn_status": "Failed",
			},
			update_modified=False,
		)

		frappe.db.commit()

		frappe.log_error(
			frappe.get_traceback(),
			f"Stock Taking Processing Failed - {stock_taking_name}",
		)

		frappe.publish_realtime(
			"stock_taking_failed",
			{
				"stock_taking": stock_taking_name,
				"message": _(
					"Stock Taking processing failed. Please check Error Log."
				),
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

	Optimized:
	Non-serialized Bin quantities are fetched in one query.
	"""

	issue_items = []
	receipt_items = []

	# ---------------------------------------------------------
	# SCANNED DATA FOR THIS WAREHOUSE
	# ---------------------------------------------------------

	warehouse_scanned = {
		key: value
		for key, value in scanned_items.items()
		if key[1] == warehouse
	}

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
	# SERIALIZED ITEMS
	# ---------------------------------------------------------

	for item_code, system_serials in system_serials_by_item.items():

		key = (
			item_code,
			warehouse,
		)

		scanned_data = warehouse_scanned.get(
			key,
			{},
		)

		scanned_serials = set(
			scanned_data.get("serials") or []
		)

		# System serial missing from physical scan
		# => Issue DN
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

			# Delivered / another warehouse
			# => Receipt
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
	# NON-SERIALIZED STOCK
	#
	# OPTIMIZED:
	# One Bin query instead of one query per Item.
	# ---------------------------------------------------------

	bin_rows = frappe.db.sql(
		"""
		SELECT
			b.item_code,
			b.actual_qty
		FROM `tabBin` b
		INNER JOIN `tabItem` i
			ON i.name = b.item_code
		WHERE
			b.warehouse = %s
			AND i.has_serial_no = 0
			AND i.disabled = 0
		""",
		(warehouse,),
		as_dict=True,
	)

	system_qty_map = {}

	for row in bin_rows:

		item_code = row.item_code

		system_qty_map[item_code] = flt(
			row.actual_qty or 0
		)

	# ---------------------------------------------------------
	# IMPORTANT:
	# Only items with actual stock OR scanned physical count
	# need comparison.
	# ---------------------------------------------------------

	items_to_check = set(
		system_qty_map.keys()
	)

	for key in warehouse_scanned:

		item_code = key[0]

		# Add only non-serialized items.
		has_serial_no = frappe.db.get_value(
			"Item",
			item_code,
			"has_serial_no",
		)

		if not has_serial_no:
			items_to_check.add(item_code)

	# ---------------------------------------------------------
	# COMPARE NON-SERIALIZED
	# ---------------------------------------------------------

	for item_code in items_to_check:

		bin_qty = flt(
			system_qty_map.get(item_code) or 0
		)

		key = (
			item_code,
			warehouse,
		)

		scanned_data = warehouse_scanned.get(
			key,
			{},
		)

		physical_count = flt(
			scanned_data.get("physical_count") or 0
		)

		# No difference
		if bin_qty == physical_count:
			continue

		# -----------------------------------------------------
		# SYSTEM > PHYSICAL
		# -----------------------------------------------------

		if bin_qty > physical_count:

			issue_items.append(
				{
					"item_code": item_code,
					"warehouse": warehouse,
					"qty": bin_qty - physical_count,
					"serial_no": "",
				}
			)

		# -----------------------------------------------------
		# PHYSICAL > SYSTEM
		# -----------------------------------------------------

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

	# ---------------------------------------------------------
	# DELIVERY NOTE HEADER
	# ---------------------------------------------------------

	dn.customer = customer
	dn.company = company
	dn.is_return = 0
	dn.return_against = None
	dn.posting_date = getdate()
	dn.posting_time = now_datetime().strftime("%H:%M:%S")
	dn.set_posting_time = 0
	dn.custom_stock_taking = stock_taking.name
	dn.custom_abbr = abbr

	# ---------------------------------------------------------
	# ITEMS
	# ---------------------------------------------------------

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

	# ---------------------------------------------------------
	# NOTHING TO INSERT
	# ---------------------------------------------------------

	if not dn.items:
		return None

	# ---------------------------------------------------------
	# INSERT AS DRAFT
	# ---------------------------------------------------------

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

	# ---------------------------------------------------------
	# RETURN DELIVERY NOTE HEADER
	# ---------------------------------------------------------

	dn.customer = customer
	dn.company = company
	dn.is_return = 1
	dn.return_against = None
	dn.posting_date = getdate()
	dn.posting_time = now_datetime().strftime("%H:%M:%S")
	dn.set_posting_time = 1
	dn.custom_stock_taking = stock_taking.name
	dn.custom_abbr = abbr

	# ---------------------------------------------------------
	# ITEMS
	# ---------------------------------------------------------

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

	# ---------------------------------------------------------
	# NOTHING TO INSERT
	# ---------------------------------------------------------

	if not dn.items:
		return None

	# ---------------------------------------------------------
	# INSERT AS DRAFT
	# ---------------------------------------------------------

	dn.insert(
		ignore_permissions=True,
		ignore_mandatory=True,
		ignore_links=True,
	)

	return dn


def link_return_delivery_note(doc, method=None):
	"""
	After NORMAL Delivery Note is submitted:

	1. Find draft Return DN of same Stock Taking.
	2. Set Return DN posting timestamp after Normal DN.
	3. Set return_against = Normal DN.
	4. Save Return DN.
	5. Return DN remains Draft.
	"""

	if not doc:
		return

	# Return DN par function dobara nahi chalega
	if doc.is_return:
		return

	# Stock Taking related DN only
	stock_taking = doc.get("custom_stock_taking")

	if not stock_taking:
		return

	# Find draft Return DN
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

	return_dn = frappe.get_doc(
		"Delivery Note",
		return_dn_name,
	)

	if return_dn.docstatus != 0:
		return

	# ---------------------------------------------------------
	# IMPORTANT:
	# Return DN timestamp must be AFTER Normal DN timestamp
	# ---------------------------------------------------------

	normal_dn_datetime = get_datetime(
		f"{doc.posting_date} {doc.posting_time}"
	)

	return_dn_datetime = normal_dn_datetime + timedelta(seconds=1)

	return_dn.posting_date = return_dn_datetime.date()
	return_dn.posting_time = return_dn_datetime.strftime("%H:%M:%S.%f")
	return_dn.set_posting_time = 1

	# ---------------------------------------------------------
	# Link Return DN with Normal DN
	# ---------------------------------------------------------

	return_dn.return_against = doc.name

	# ---------------------------------------------------------
	# SAVE ONLY
	# Return DN submit nahi hoga
	# ---------------------------------------------------------

	return_dn.save(
		ignore_permissions=True
	)

	frappe.clear_document_cache(
		"Delivery Note",
		return_dn.name,
	)

	frappe.publish_realtime(
		"stock_taking_return_linked",
		{
			"stock_taking": stock_taking,
			"delivery_note": doc.name,
			"return_delivery_note": return_dn.name,
		},
	)
 
def update_stock_taking_dn_timestamp(doc, method=None):
	"""
	Update posting timestamp immediately before submitting
	Stock Taking related Delivery Note.
	"""

	if not doc:
		return

	if not doc.get("custom_stock_taking"):
		return

	if doc.docstatus != 0:
		return

	now = now_datetime()

	doc.posting_date = now.date()
	doc.posting_time = now.strftime("%H:%M:%S.%f")
	doc.set_posting_time = 1