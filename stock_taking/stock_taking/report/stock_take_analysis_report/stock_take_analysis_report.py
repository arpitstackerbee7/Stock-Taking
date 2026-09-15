import frappe
from frappe import _
from frappe.utils import getdate


# =========================================================
# EXECUTE
# =========================================================

def execute(filters=None):

    filters = frappe._dict(filters or {})

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


# =========================================================
# COLUMNS
# =========================================================

def get_columns(filters=None):

    filters = frappe._dict(filters or {})

    columns = [

        {
            "label": "Stock Taking",
            "fieldname": "stock_taking",
            "fieldtype": "Link",
            "options": "Stock Taking",
            "width": 180,
        },

        {
            "label": "Owner Site",
            "fieldname": "owner_site",
            "fieldtype": "Data",
            "width": 180,
        },

        {
            "label": "Status",
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 120,
        },

        {
            "label": "Item Code",
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 180,
        },
    ]

    # =====================================================
    # SERIAL NO
    # =====================================================

    if filters.get("show_serial_no"):

        columns.append({
            "label": "Serial No",
            "fieldname": "serial_no",
            "fieldtype": "HTML",
            "width": 400,
        })

    columns.extend([

        # =================================================
        # ITEM DETAILS
        # =================================================

        {
            "label": "Brand Name",
            "fieldname": "brand_name",
            "fieldtype": "Data",
            "width": 180,
        },

        {
            "label": "MRP",
            "fieldname": "mrp",
            "fieldtype": "Currency",
            "width": 120,
        },

        {
            "label": "STD",
            "fieldname": "std",
            "fieldtype": "Currency",
            "width": 120,
        },

        {
            "label": "WSP",
            "fieldname": "wsp",
            "fieldtype": "Currency",
            "width": 120,
        },

        {
            "label": "Silhouette",
            "fieldname": "silhouette",
            "fieldtype": "Data",
            "width": 150,
        },

        {
            "label": "Division",
            "fieldname": "division",
            "fieldtype": "Data",
            "width": 150,
        },

        {
            "label": "Stock Adj Date",
            "fieldname": "stock_adj_date",
            "fieldtype": "Date",
            "width": 120,
        },

        {
            "label": "Plan Date",
            "fieldname": "plan_date",
            "fieldtype": "Date",
            "width": 120,
        },

        {
            "label": "Plan Description",
            "fieldname": "plan_description",
            "fieldtype": "Data",
            "width": 220,
        },

        # =================================================
        # CATEGORY
        # =================================================

        {
            "label": "Count Of Pcs",
            "fieldname": "category1",
            "fieldtype": "Data",
            "width": 120,
        },

        {
            "label": "Top Fabric",
            "fieldname": "category2",
            "fieldtype": "Data",
            "width": 120,
        },

        {
            "label": "Color",
            "fieldname": "category3",
            "fieldtype": "Data",
            "width": 120,
        },

        {
            "label": "Sup Design No",
            "fieldname": "category4",
            "fieldtype": "Data",
            "width": 120,
        },

        {
            "label": "Size",
            "fieldname": "category5",
            "fieldtype": "Data",
            "width": 120,
        },

        {
            "label": "Block",
            "fieldname": "category6",
            "fieldtype": "Data",
            "width": 120,
        },

        # =================================================
        # OPENING
        # =================================================

        # {
        #     "label": "Opening Qty",
        #     "fieldname": "opening_qty",
        #     "fieldtype": "Float",
        #     "width": 120,
        # },

        # =================================================
        # BALANCE
        # =================================================

        # {
        #     "label": "Balance Qty",
        #     "fieldname": "balance_qty",
        #     "fieldtype": "Float",
        #     "width": 120,
        # },

        # =================================================
        # BOOK STOCK
        # =================================================

        {
            "label": "Book Stock",
            "fieldname": "book_stock",
            "fieldtype": "Float",
            "width": 120,
        },

        # =================================================
        # PHYSICAL
        # =================================================

        {
            "label": "Physical Stock",
            "fieldname": "physical_stock",
            "fieldtype": "Float",
            "width": 120,
        },

        # =================================================
        # DIFFERENCE
        # =================================================

        {
            "label": "Difference",
            "fieldname": "difference",
            "fieldtype": "Float",
            "width": 120,
        },

        # =================================================
        # EXCESS
        # =================================================

        {
            "label": "Excess Qty",
            "fieldname": "excess_qty",
            "fieldtype": "Float",
            "width": 120,
        },

        # =================================================
        # SHORT
        # =================================================

        {
            "label": "Short Qty",
            "fieldname": "short_qty",
            "fieldtype": "Float",
            "width": 120,
        },

        # =================================================
        # STOCK ADJUSTMENT
        # =================================================

        {
            "label": "Stock Adj Qty",
            "fieldname": "stock_adj_qty",
            "fieldtype": "Float",
            "width": 120,
        },

        # =================================================
        # WAREHOUSE
        # =================================================

        {
            "label": "Stock Point",
            "fieldname": "stock_point",
            "fieldtype": "Link",
            "options": "Warehouse",
            "width": 180,
        },
    ])

    return columns


# =========================================================
# DATA
# =========================================================

def get_data(filters):

    filters = frappe._dict(filters or {})

    values = {}

    # =====================================================
    # DATES
    # =====================================================

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")

    if not from_date:
        from_date = "1900-01-01"

    if not to_date:
        to_date = getdate()

    from_date = getdate(from_date)
    to_date = getdate(to_date)

    values["from_date"] = from_date
    values["to_date"] = to_date

    # =====================================================
    # MAIN CONDITIONS
    # =====================================================

    conditions = []

    # =====================================================
    # COMPANY
    # =====================================================

    if filters.get("company"):

        conditions.append(
            "st.company = %(company)s"
        )

        values["company"] = filters.get("company")

    # =====================================================
    # STOCK TAKING
    # =====================================================

    if filters.get("stock_taking"):

        conditions.append(
            "st.name = %(stock_taking)s"
        )

        values["stock_taking"] = filters.get("stock_taking")

    # =====================================================
    # ITEM
    # =====================================================

    if filters.get("item_code"):

        conditions.append(
            "iw.item_code = %(item_code)s"
        )

        values["item_code"] = filters.get("item_code")

    # =====================================================
    # WAREHOUSE
    # =====================================================

    if filters.get("warehouse"):

        conditions.append(
            "iw.warehouse = %(warehouse)s"
        )

        values["warehouse"] = filters.get("warehouse")

    # =====================================================
    # PLAN DATE
    # =====================================================

    if filters.get("from_date"):

        conditions.append(
            "st.plan_date >= %(plan_from_date)s"
        )

        values["plan_from_date"] = filters.get("from_date")

    if filters.get("to_date"):

        conditions.append(
            "st.plan_date <= %(plan_to_date)s"
        )

        values["plan_to_date"] = filters.get("to_date")

    # =====================================================
    # STATUS
    # =====================================================

    if filters.get("status"):

        status_map = {
            "Draft": 0,
            "Submitted": 1,
            "Cancelled": 2
        }

        status_value = status_map.get(
            filters.get("status")
        )

        if status_value is not None:

            conditions.append(
                "st.docstatus = %(docstatus)s"
            )

            values["docstatus"] = status_value

    # =====================================================
    # WHERE
    # =====================================================

    where_conditions = ""

    if conditions:

        where_conditions = (
            " AND " +
            " AND ".join(conditions)
        )

    # =====================================================
    # MAIN QUERY
    # =====================================================

    data = frappe.db.sql(
        f"""
        SELECT

            -- =================================================
            -- STOCK TAKING
            -- =================================================

            st.name AS stock_taking,

            st.company AS owner_site,

            CASE
                WHEN st.docstatus = 0 THEN 'Draft'
                WHEN st.docstatus = 1 THEN 'Submitted'
                WHEN st.docstatus = 2 THEN 'Cancelled'
            END AS status,

            -- =================================================
            -- ITEM
            -- =================================================

            iw.item_code,

            -- =================================================
            -- SERIAL
            -- =================================================

            REPLACE(
                COALESCE(
                    sti.serial_no,
                    ''
                ),
                '\\\\n',
                '<br>'
            ) AS serial_no,

            -- =================================================
            -- ITEM MASTER
            -- =================================================

            i.brand AS brand_name,

            -- =================================================
            -- MRP
            -- =================================================

            (
                SELECT ip.price_list_rate

                FROM `tabItem Price` ip

                WHERE ip.item_code = iw.item_code
                  AND ip.price_list = 'MRP'

                ORDER BY
                    ip.modified DESC,
                    ip.name DESC

                LIMIT 1

            ) AS mrp,

            -- =================================================
            -- STD
            -- =================================================

            (
                SELECT ip.price_list_rate

                FROM `tabItem Price` ip

                WHERE ip.item_code = iw.item_code
                  AND ip.price_list = 'STD'

                ORDER BY
                    ip.modified DESC,
                    ip.name DESC

                LIMIT 1

            ) AS std,

            -- =================================================
            -- WSP
            -- =================================================

            (
                SELECT ip.price_list_rate

                FROM `tabItem Price` ip

                WHERE ip.item_code = iw.item_code
                  AND ip.price_list = 'WSP'

                ORDER BY
                    ip.modified DESC,
                    ip.name DESC

                LIMIT 1

            ) AS wsp,

            -- =================================================
            -- ITEM CUSTOM FIELDS
            -- =================================================

            i.custom_silvet AS silhouette,

            i.item_group AS division,

            -- =================================================
            -- STOCK ADJUSTMENT DATE
            -- =================================================

            (
                SELECT MAX(se.posting_date)

                FROM `tabStock Entry` se

                WHERE se.custom_stock_taking = st.name

                  AND se.docstatus IN (0, 1)

                  AND TIMESTAMP(
                        se.posting_date,
                        se.posting_time
                      )
                      <= TIMESTAMP(
                        st.plan_date,
                        st.plan_time
                      )

            ) AS stock_adj_date,

            -- =================================================
            -- PLAN
            -- =================================================

            st.plan_date AS plan_date,

            st.remark AS plan_description,

            -- =================================================
            -- CATEGORY
            -- =================================================

            i.custom_count_of_pcs AS category1,

            i.custom_top_fabrics AS category2,

            i.custom_colour_name AS category3,

            i.custom_sup_design_no AS category4,

            i.custom_size AS category5,

            i.custom_block AS category6,

            -- =================================================
            -- WAREHOUSE
            -- =================================================

            iw.warehouse AS stock_point,

            -- =================================================
            -- OPENING QTY
            --
            -- ONLY Stock Reconciliation where
            -- purpose = Opening Stock
            --
            -- If item is not in Opening Stock:
            -- 0
            -- =================================================

            COALESCE(
                opening.opening_qty,
                0
            ) AS opening_qty,

            -- =================================================
            -- BALANCE QTY
            --
            -- ERPNext STOCK BALANCE CONCEPT
            --
            -- Cumulative Stock Ledger balance
            -- up to To Date.
            --
            -- NOT from_date.
            -- =================================================

            COALESCE(
                balance.balance_qty,
                0
            ) AS balance_qty,

            -- =================================================
            -- BOOK STOCK
            --
            -- Ending book stock = Balance Qty
            -- =================================================

            (
                COALESCE(
                    opening.opening_qty,
                    0
                )
                +
                COALESCE(
                    balance.balance_qty,
                    0
                )
            ) AS book_stock,

            -- =================================================
            -- PHYSICAL
            -- =================================================

            COALESCE(
                sti.physical_count,
                0
            ) AS physical_stock,

            -- =================================================
            -- DIFFERENCE
            --
            -- Physical - Book Stock
            -- =================================================

            (
                COALESCE(
                    sti.physical_count,
                    0
                )
                -
                (
                    COALESCE(
                        opening.opening_qty,
                        0
                    )
                    +
                    COALESCE(
                        balance.balance_qty,
                        0
                    )
                )
            ) AS difference,

            -- =================================================
            -- EXCESS
            -- =================================================

            (
                -1 *
                COALESCE(
                    excess.excess_qty,
                    0
                )
            ) AS excess_qty,

            -- =================================================
            -- SHORT
            -- =================================================

            (
                -1 *
                COALESCE(
                    short_data.short_qty,
                    0
                )
            ) AS short_qty,

            -- =================================================
            -- STOCK ADJUSTMENT
            -- =================================================

            (
                (
                    -1 *
                    COALESCE(
                        short_data.short_qty,
                        0
                    )
                )
                +
                (
                    -1 *
                    COALESCE(
                        excess.excess_qty,
                        0
                    )
                )
            ) AS stock_adj_qty


        -- =====================================================
        -- STOCK TAKING
        -- =====================================================

        FROM `tabStock Taking` st


        -- =====================================================
        -- ITEM DATASET
        --
        -- 1. OPENING STOCK ITEMS
        -- 2. ALL STOCK ITEMS
        -- 3. SCANNED ITEMS
        --
        -- IMPORTANT:
        --
        -- Stock items are taken from SLE up to To Date.
        -- Therefore items whose stock was created before
        -- From Date are also included.
        -- =====================================================

        INNER JOIN (

            SELECT DISTINCT

                all_items.stock_taking,

                all_items.item_code,

                all_items.warehouse

            FROM (

                -- =================================================
                -- 1. OPENING STOCK ITEMS
                -- =================================================

                SELECT DISTINCT

                    st_open.name AS stock_taking,

                    sri_open.item_code,

                    sri_open.warehouse

                FROM `tabStock Taking` st_open

                INNER JOIN `tabStock Reconciliation` sr_open

                    ON sr_open.company =
                       st_open.company

                    AND sr_open.purpose =
                        'Opening Stock'

                    AND sr_open.docstatus = 1

                    AND sr_open.posting_date <=
                        st_open.plan_date

                INNER JOIN `tabStock Reconciliation Item`
                    sri_open

                    ON sri_open.parent =
                       sr_open.name

                WHERE

                    sri_open.item_code IS NOT NULL

                    AND sri_open.warehouse IS NOT NULL


                UNION


                -- =================================================
                -- 2. NORMAL STOCK ITEMS
                --
                -- ALL items having non-zero cumulative stock
                -- up to To Date.
                --
                -- This is the important Stock Balance logic.
                -- =================================================

                SELECT DISTINCT

                    st_normal.name AS stock_taking,

                    sle_normal.item_code,

                    sle_normal.warehouse

                FROM `tabStock Taking` st_normal

                INNER JOIN `tabStock Ledger Entry`
                    sle_normal

                    ON sle_normal.company =
                       st_normal.company

                    AND sle_normal.is_cancelled = 0

                    AND sle_normal.posting_date <=
                        %(to_date)s

                INNER JOIN (

                    SELECT DISTINCT

                        parent,

                        warehouse

                    FROM `tabStock taking Items`

                    WHERE
                        warehouse IS NOT NULL

                ) st_wh_normal

                    ON st_wh_normal.parent =
                       st_normal.name

                    AND st_wh_normal.warehouse =
                        sle_normal.warehouse

                GROUP BY

                    st_normal.name,

                    sle_normal.item_code,

                    sle_normal.warehouse

                HAVING

                    SUM(
                        sle_normal.actual_qty
                    ) != 0


                UNION


                -- =================================================
                -- 3. SCANNED ITEMS
                -- =================================================

                SELECT DISTINCT

                    sti_scanned.parent AS stock_taking,

                    sti_scanned.item_code,

                    sti_scanned.warehouse

                FROM `tabStock taking Items`
                    sti_scanned

                WHERE

                    sti_scanned.item_code IS NOT NULL

                    AND sti_scanned.warehouse IS NOT NULL

            ) all_items

        ) iw

            ON iw.stock_taking =
               st.name


        -- =====================================================
        -- OPENING STOCK
        --
        -- Purpose = Opening Stock
        --
        -- IMPORTANT:
        --
        -- We only use Opening Stock reconciliation quantity
        -- for Opening Qty.
        --
        -- Normal stock items get Opening Qty = 0.
        -- =====================================================

        LEFT JOIN (

            SELECT

                x.company,

                x.item_code,

                x.warehouse,

                SUM(
                    x.qty
                ) AS opening_qty

            FROM (

                SELECT

                    sr.company,

                    sri.item_code,

                    sri.warehouse,

                    sri.qty

                FROM `tabStock Reconciliation` sr

                INNER JOIN `tabStock Reconciliation Item`
                    sri

                    ON sri.parent =
                       sr.name

                WHERE

                    sr.purpose =
                    'Opening Stock'

                    AND sr.docstatus = 1

                    AND sr.posting_date <=
                        %(to_date)s

                    AND sri.item_code IS NOT NULL

                    AND sri.warehouse IS NOT NULL

            ) x

            GROUP BY

                x.company,

                x.item_code,

                x.warehouse

        ) opening

            ON opening.company =
               st.company

            AND opening.item_code =
                iw.item_code

            AND opening.warehouse =
                iw.warehouse


        -- =====================================================
        -- BALANCE STOCK
        --
        -- THIS IS THE MAIN FIX
        --
        -- ERPNext Stock Balance:
        --
        -- Balance Qty =
        -- SUM(actual_qty)
        -- for Item + Warehouse
        -- up to To Date
        --
        -- We DO NOT use from_date here.
        -- =====================================================

        LEFT JOIN (

            SELECT

                sle.company,

                sle.item_code,

                sle.warehouse,

                SUM(
                    sle.actual_qty
                ) AS balance_qty

            FROM `tabStock Ledger Entry` sle

            WHERE

                sle.is_cancelled = 0

                AND sle.posting_date <=
                    %(to_date)s

            GROUP BY

                sle.company,

                sle.item_code,

                sle.warehouse

            HAVING

                SUM(
                    sle.actual_qty
                ) != 0

        ) balance

            ON balance.company =
               st.company

            AND balance.item_code =
                iw.item_code

            AND balance.warehouse =
                iw.warehouse


        -- =====================================================
        -- STOCK TAKING ITEMS
        -- =====================================================

        LEFT JOIN (

            SELECT

                parent,

                item_code,

                warehouse,

                SUM(
                    COALESCE(
                        physical_count,
                        0
                    )
                ) AS physical_count,

                GROUP_CONCAT(
                    DISTINCT
                    NULLIF(
                        serial_no,
                        ''
                    )
                    SEPARATOR '\\n'
                ) AS serial_no

            FROM `tabStock taking Items`

            GROUP BY

                parent,

                item_code,

                warehouse

        ) sti

            ON sti.parent =
               st.name

            AND sti.item_code =
                iw.item_code

            AND sti.warehouse =
                iw.warehouse


        -- =====================================================
        -- ITEM MASTER
        -- =====================================================

        LEFT JOIN `tabItem` i

            ON i.name =
               iw.item_code


        -- =====================================================
        -- EXCESS / RETURN
        -- =====================================================

        LEFT JOIN (

            SELECT

                dn.custom_stock_taking AS stock_taking,

                dni.item_code,

                dni.warehouse,

                SUM(
                    dni.qty
                ) AS excess_qty

            FROM `tabDelivery Note` dn

            INNER JOIN `tabDelivery Note Item` dni

                ON dni.parent =
                   dn.name

            WHERE

                dn.is_return = 1

                AND dn.docstatus IN (0, 1)

                AND dn.custom_stock_taking IS NOT NULL

            GROUP BY

                dn.custom_stock_taking,

                dni.item_code,

                dni.warehouse

        ) excess

            ON excess.stock_taking =
               st.name

            AND excess.item_code =
                iw.item_code

            AND excess.warehouse =
                iw.warehouse


        -- =====================================================
        -- SHORT / NORMAL DELIVERY
        -- =====================================================

        LEFT JOIN (

            SELECT

                dn.custom_stock_taking AS stock_taking,

                dni.item_code,

                dni.warehouse,

                SUM(
                    dni.qty
                ) AS short_qty

            FROM `tabDelivery Note` dn

            INNER JOIN `tabDelivery Note Item` dni

                ON dni.parent =
                   dn.name

            WHERE

                IFNULL(
                    dn.is_return,
                    0
                ) = 0

                AND dn.docstatus IN (0, 1)

                AND dn.custom_stock_taking IS NOT NULL

            GROUP BY

                dn.custom_stock_taking,

                dni.item_code,

                dni.warehouse

        ) short_data

            ON short_data.stock_taking =
               st.name

            AND short_data.item_code =
                iw.item_code

            AND short_data.warehouse =
                iw.warehouse


        -- =====================================================
        -- FILTERS
        -- =====================================================

        WHERE 1 = 1

        {where_conditions}


        -- =====================================================
        -- ORDER
        --
        -- Opening Stock items first.
        -- Then other stock items.
        -- =====================================================

        ORDER BY

            st.name DESC,

            CASE
                WHEN COALESCE(
                    opening.opening_qty,
                    0
                ) != 0
                THEN 0
                ELSE 1
            END,

            iw.item_code ASC

        """,

        values,

        as_dict=True
    )

    return data