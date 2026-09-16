frappe.ui.form.on("Stock Taking", {

    // =====================================================
    // ONLOAD
    // =====================================================

    onload(frm) {

        apply_warehouse_filter(frm);

        setTimeout(() => {

            const field =
                frm.fields_dict.scan_barcode;

            if (!field || !field.$input) {
                return;
            }

            field.$input.off(
                "input.stock_taking"
            );

            let scan_timer = null;

            field.$input.on(
                "input.stock_taking",
                function () {

                    const value =
                        field.$input
                            .val()
                            .trim();

                    if (!value) {
                        return;
                    }

                    clearTimeout(
                        scan_timer
                    );

                    scan_timer = setTimeout(
                        () => {

                            process_scan(
                                frm,
                                value
                            );

                            field.$input.val("");
                            field.$input.get(0).value = "";

                            frm.doc.scan_barcode = "";

                            field.$input.focus();

                        },
                        200
                    );
                }
            );

            field.$input.focus();

        }, 500);
    },


    // =====================================================
    // REFRESH
    // =====================================================

    refresh(frm) {

        apply_warehouse_filter(frm);

        update_total_quantity(frm);
    },


    // =====================================================
    // COMPANY
    // =====================================================

    company(frm) {

        frm.set_value(
            "warehouse",
            ""
        );

        frm.clear_table(
            "items"
        );

        frm.refresh_field(
            "items"
        );

        apply_warehouse_filter(frm);
    },


    // =====================================================
    // STOCK SELECTION
    // =====================================================

    stock_selection(frm) {

        frm.set_value(
            "warehouse",
            ""
        );

        frm.clear_table(
            "items"
        );

        frm.refresh_field(
            "items"
        );

        apply_warehouse_filter(frm);
    },


    // =====================================================
    // WAREHOUSE
    // =====================================================

    warehouse(frm) {

        update_child_warehouse(frm);

        frm.refresh_field(
            "items"
        );
    },


    // =====================================================
    // BEFORE SAVE
    // =====================================================

    before_save(frm) {

        update_child_warehouse(frm);
    },


    // =====================================================
    // BEFORE SUBMIT
    // =====================================================

    before_submit(frm) {

        frappe.validated = true;

        frappe.msgprint({
            title: __(
                "Stock Taking Submitted"
            ),
            message: `
                <div style="line-height: 1.8;">

                    <div>
                        <b>Stock Taking has been submitted successfully.</b>
                    </div>

                    <div style="margin-top: 8px;">
                        Delivery Note processing is running
                        in the background.
                    </div>

                    <div style="margin-top: 8px; color: #6b7280;">
                        You will receive a notification when
                        the Delivery Note processing is completed.
                    </div>

                </div>
            `,
            indicator: "blue"
        });
    },

    on_submit(frm) {
		frappe.msgprint({
			title: __("Stock Taking Submitted"),
			message: `
				<div style="font-size:14px; line-height:1.7;">
					<p>
						<b>${__("Stock Taking")}:</b>
						${frappe.utils.escape_html(frm.doc.name)}
					</p>

					<p>
						Delivery Notes are being created
						<b>in the background</b>.
					</p>

					<p style="margin-bottom:0;">
						Please wait. You will get another message
						once the Delivery Notes are created.
					</p>
				</div>
			`,
			indicator: "blue",
		});
	},

});


// =========================================================
// LOADER
// =========================================================

function show_stock_taking_loader(
    title,
    message
) {

    let loader =
        document.getElementById(
            "stock-taking-submit-loader"
        );

    if (!loader) {

        loader =
            document.createElement(
                "div"
            );

        loader.id =
            "stock-taking-submit-loader";

        loader.innerHTML = `
            <div class="stock-taking-loader-box">

                <div class="stock-taking-spinner"></div>

                <div class="stock-taking-loader-title"></div>

                <div class="stock-taking-loader-message"></div>

            </div>
        `;

        document.body.appendChild(
            loader
        );

        const style =
            document.createElement(
                "style"
            );

        style.id =
            "stock-taking-loader-style";

        style.innerHTML = `

            #stock-taking-submit-loader {

                position: fixed;

                top: 0;
                left: 0;

                width: 100vw;
                height: 100vh;

                background:
                    rgba(255,255,255,0.75);

                z-index: 999999;

                display: flex;

                align-items: center;
                justify-content: center;

                cursor: wait;
            }

            .stock-taking-loader-box {

                background: #ffffff;

                padding: 35px 55px;

                border-radius: 12px;

                text-align: center;

                min-width: 360px;

                box-shadow:
                    0 10px 40px
                    rgba(0,0,0,0.20);
            }

            .stock-taking-spinner {

                width: 45px;
                height: 45px;

                margin:
                    0 auto 20px auto;

                border:
                    4px solid #e5e7eb;

                border-top:
                    4px solid #2490ef;

                border-radius: 50%;

                animation:
                    stockTakingSpin
                    0.8s linear infinite;
            }

            .stock-taking-loader-title {

                font-size: 18px;

                font-weight: 600;

                margin-bottom: 8px;
            }

            .stock-taking-loader-message {

                font-size: 14px;

                color: #6b7280;
            }

            @keyframes stockTakingSpin {

                from {
                    transform: rotate(0deg);
                }

                to {
                    transform: rotate(360deg);
                }
            }
        `;

        document.head.appendChild(
            style
        );
    }

    const title_element =
        loader.querySelector(
            ".stock-taking-loader-title"
        );

    const message_element =
        loader.querySelector(
            ".stock-taking-loader-message"
        );

    if (title_element) {

        title_element.textContent =
            title;
    }

    if (message_element) {

        message_element.textContent =
            message;
    }

    loader.style.display =
        "flex";

    document.body.style.overflow =
        "hidden";
}


// =========================================================
// HIDE LOADER
// =========================================================

function hide_stock_taking_loader() {

    const loader =
        document.getElementById(
            "stock-taking-submit-loader"
        );

    if (loader) {

        loader.style.display =
            "none";
    }

    document.body.style.overflow =
        "";
}


// =========================================================
// SERIAL SCAN
// =========================================================
function handle_serial_scan(frm, serial) {

    const selected_warehouses = (frm.doc.warehouse || [])
        .map(row => row.warehuose || row.warehouse)
        .filter(Boolean);

    if (!selected_warehouses.length) {
        frappe.msgprint({
            title: __("Warehouse Required"),
            message: __("Please select at least one warehouse."),
            indicator: "red"
        });
        return;
    }

    const serial_name =
        serial.name || "";

    const item_code =
        serial.item_code || "";

    const serial_warehouse =
        serial.warehouse || "";

    const status =
        serial.status || "";

    if (!serial_name || !item_code) {
        frappe.msgprint({
            title: __("Invalid Serial"),
            message: __("Serial Number information is incomplete."),
            indicator: "red"
        });
        return;
    }

    const is_delivered =
        status === "Delivered";

    const in_selected_warehouse =
        selected_warehouses.includes(
            serial_warehouse
        );

    const is_diff_warehouse =
        !is_delivered &&
        !in_selected_warehouse;

    const parent_warehouse =
        selected_warehouses[0];

    // -----------------------------------------
    // Find existing row
    // -----------------------------------------
    let row = frm.doc.items.find(d =>
        d.item_code === item_code &&
        d.warehouse === parent_warehouse
    );

    // -----------------------------------------
    // New row
    // -----------------------------------------
    if (!row) {

        row = frm.add_child("items");

        row.item_code = item_code;
        row.warehouse = parent_warehouse;

        row.serial_no = "";
        row.inventory = 0;
        row.physical_count = 0;
        row.difference = 0;

        row.is_diff_warehouse_row = 0;
        row.is_delivered_row = 0;
    }

    // -----------------------------------------
    // DELIVERED SERIAL
    // -----------------------------------------
    if (is_delivered) {

        row.item_code = item_code;
        row.warehouse = parent_warehouse;

        row.is_delivered_row = 1;
        row.is_diff_warehouse_row = 0;

        const existing_serials =
            row.serial_no
                ? String(row.serial_no)
                    .split("\n")
                    .map(x => x.trim())
                    .filter(Boolean)
                : [];

        if (!existing_serials.includes(serial_name)) {
            existing_serials.push(serial_name);
        }

        row.serial_no =
            existing_serials.join("\n");

        row.physical_count =
            flt(row.physical_count || 0) + 1;

        // Delivered row difference remains 0.
        row.difference = 0;

        frappe.msgprint({
            title: __("Delivered Item"),
            message: __(
                "Item <b>{0}</b> is Delivered."
            ).replace("{0}", item_code),
            indicator: "orange"
        });
    }

    // -----------------------------------------
    // SERIAL FROM DIFFERENT WAREHOUSE
    // -----------------------------------------
    else if (is_diff_warehouse) {

        row.item_code = item_code;
        row.warehouse = parent_warehouse;

        row.is_diff_warehouse_row = 1;
        row.is_delivered_row = 0;

        const existing_serials =
            row.serial_no
                ? String(row.serial_no)
                    .split("\n")
                    .map(x => x.trim())
                    .filter(Boolean)
                : [];

        if (!existing_serials.includes(serial_name)) {
            existing_serials.push(serial_name);
        }

        row.serial_no =
            existing_serials.join("\n");

        row.inventory = 0;

        row.physical_count =
            flt(row.physical_count || 0) + 1;

        row.difference = 0;

        frappe.msgprint({
            title: __("Item Not Available"),
            message: __(
                "Item <b>{0}</b> is not available in warehouse <b>{1}</b>."
            )
                .replace("{0}", item_code)
                .replace("{1}", parent_warehouse),
            indicator: "orange"
        });
    }

    // -----------------------------------------
    // NORMAL ACTIVE SERIAL
    // -----------------------------------------
    else {

        row.item_code = item_code;
        row.warehouse = parent_warehouse;

        row.is_diff_warehouse_row = 0;
        row.is_delivered_row = 0;

        const existing_serials =
            row.serial_no
                ? String(row.serial_no)
                    .split("\n")
                    .map(x => x.trim())
                    .filter(Boolean)
                : [];

        if (!existing_serials.includes(serial_name)) {
            existing_serials.push(serial_name);
        }

        row.serial_no =
            existing_serials.join("\n");

        row.physical_count =
            flt(row.physical_count || 0) + 1;

        row.difference =
            flt(row.physical_count) -
            flt(row.inventory);
    }

    frm.refresh_field("items");

    update_total_quantity(frm);
    calculate_differences(frm);
}
// =========================================================
// PROCESS SCAN
// =========================================================
function process_scan(frm, scanned_code) {
    if (!scanned_code) {
        return;
    }

    if (!frm.doc.stock_selection) {
        frappe.msgprint({
            title: __("Stock Selection Required"),
            message: __("Please select Stock Selection first."),
            indicator: "red"
        });
        return;
    }

    if (!frm.doc.warehouse || !frm.doc.warehouse.length) {
        frappe.msgprint({
            title: __("Warehouse Required"),
            message: __("Please select at least one warehouse."),
            indicator: "red"
        });
        return;
    }

    const selected_warehouses = (frm.doc.warehouse || [])
        .map(row => row.warehuose || row.warehouse)
        .filter(Boolean);

    if (!selected_warehouses.length) {
        frappe.msgprint({
            title: __("Warehouse Required"),
            message: __("Please select at least one warehouse."),
            indicator: "red"
        });
        return;
    }

    frappe.call({
        method: "stock_taking.stock_taking.doctype.stock_taking.stock_taking.scan_barcode",
        args: {
            code: scanned_code,
            warehouses: selected_warehouses
        },

        callback: function (r) {
            const res = r.message;

            if (!res || !res.success) {
                frappe.msgprint({
                    title: __("Scan Failed"),
                    message: res?.message || __("Unable to process scan."),
                    indicator: "red"
                });
                return;
            }

            // =====================================================
            // SERIAL NUMBER SCAN
            // =====================================================
            if (res.type === "serial") {
                handle_serial_scan(frm, res.result);
                return;
            }

            // =====================================================
            // NON-SERIALIZED ITEM SCAN
            // =====================================================
            if (res.type === "item") {

                const selected_warehouses = (frm.doc.warehouse || [])
                    .map(row => row.warehuose || row.warehouse)
                    .filter(Boolean);

                if (!selected_warehouses.length) {
                    frappe.msgprint({
                        title: __("Warehouse Required"),
                        message: __("Please select at least one warehouse."),
                        indicator: "red"
                    });
                    return;
                }

                const parent_warehouse = selected_warehouses[0];

                const bins = res.result || [];

                bins.forEach(bin => {

                    // Debug - temporary
                    console.log("SCAN ITEM BIN:", bin);

                    const is_diff_warehouse =
                        Number(bin.is_diff_warehouse_row || 0) === 1;

                    // =================================================
                    // FIND EXISTING ROW
                    // =================================================
                    let row = frm.doc.items.find(d =>
                        d.item_code === bin.item_code &&
                        d.warehouse === parent_warehouse &&
                        !d.is_delivered_row
                    );

                    // =================================================
                    // CREATE NEW ROW
                    // =================================================
                    if (!row) {
                        row = frm.add_child("items");

                        // IMPORTANT:
                        // Use frappe.model.set_value for Link fields
                        frappe.model.set_value(
                            row.doctype,
                            row.name,
                            "item_code",
                            bin.item_code
                        );

                        frappe.model.set_value(
                            row.doctype,
                            row.name,
                            "warehouse",
                            parent_warehouse
                        );

                        row.serial_no = "";
                        row.inventory = 0;
                        row.physical_count = 0;
                        row.difference = 0;

                        row.is_diff_warehouse_row = 0;
                        row.is_delivered_row = 0;
                    }

                    // =================================================
                    // DIFFERENT WAREHOUSE ITEM
                    // =================================================
                    if (is_diff_warehouse) {

                        row.is_diff_warehouse_row = 1;
                        row.is_delivered_row = 0;

                        // Selected warehouse me stock nahi hai
                        row.inventory = 0;

                        // Scan count
                        row.physical_count =
                            flt(row.physical_count) + 1;

                        // Difference nahi banana
                        row.difference = 0;

                        // Alert
                        frappe.msgprint({
                            title: __("Item Not Available"),
                            message: __(
                                "Item <b>{0}</b> is not available in warehouse <b>{1}</b>."
                            )
                                .replace("{0}", bin.item_code)
                                .replace("{1}", parent_warehouse),
                            indicator: "orange"
                        });

                        return;
                    }

                    // =================================================
                    // NORMAL NON-SERIALIZED ITEM
                    // =================================================
                    row.is_diff_warehouse_row = 0;
                    row.is_delivered_row = 0;

                    // Actual stock in selected warehouse
                    row.inventory = flt(bin.actual_qty);

                    // Scan count +1
                    row.physical_count =
                        flt(row.physical_count) + 1;

                    // Difference
                    row.difference =
                        flt(row.physical_count) -
                        flt(row.inventory);
                });

                // =====================================================
                // REFRESH CHILD TABLE
                // =====================================================
                frm.refresh_field("items");

                // =====================================================
                // UPDATE TOTAL
                // =====================================================
                update_total_quantity(frm);

                // =====================================================
                // UPDATE DIFFERENCE
                // =====================================================
                calculate_differences(frm);

                return;
            }

            // =====================================================
            // UNKNOWN SCAN TYPE
            // =====================================================
            frappe.msgprint({
                title: __("Invalid Scan"),
                message: __("Unable to identify scanned item."),
                indicator: "red"
            });
        },

        error: function () {
            frappe.msgprint({
                title: __("Scan Failed"),
                message: __("Unable to process the scan."),
                indicator: "red"
            });
        }
    });
}

// =========================================================
// CHILD EVENTS
// =========================================================

frappe.ui.form.on(
    "Stock taking Items",
    {

        physical_count(frm) {

            update_total_quantity(
                frm
            );

            calculate_differences(
                frm
            );
        },

        items_remove(frm) {

            update_total_quantity(
                frm
            );

            calculate_differences(
                frm
            );
        }
    }
);


// =========================================================
// TOTAL
// =========================================================

function update_total_quantity(
    frm
) {

    let total = 0;

    (
        frm.doc.items || []
    ).forEach(
        row => {

            total +=
                flt(
                    row.physical_count || 0
                );
        }
    );

    frm.set_value(
        "total_quantity",
        total
    );
}


// =========================================================
// DIFFERENCE
// =========================================================

function calculate_differences(frm) {
    let changed = false;

    (frm.doc.items || []).forEach(row => {

        // Delivered item
        if (row.is_delivered_row) {
            if (row.difference !== 0) {
                row.difference = 0;
                changed = true;
            }

            return;
        }

        // Different warehouse item
        if (row.is_diff_warehouse_row) {
            if (row.difference !== 0) {
                row.difference = 0;
                changed = true;
            }

            return;
        }

        const inventory = flt(row.inventory) || 0;
        const physical = flt(row.physical_count) || 0;

        const diff = physical - inventory;

        if (row.difference !== diff) {
            row.difference = diff;
            changed = true;
        }
    });

    if (changed) {
        frm.refresh_field("items");
    }
}


// =========================================================
// UPDATE CHILD WAREHOUSE
// =========================================================

function update_child_warehouse(
    frm
) {

    if (
        !frm.doc.warehouse ||
        !frm.doc.warehouse.length
    ) {
        return;
    }

    const parent_warehouse =
        frm.doc.warehouse[0].warehuose ||
        frm.doc.warehouse[0].warehouse;

    if (!parent_warehouse) {
        return;
    }

    (
        frm.doc.items || []
    ).forEach(
        row => {

            // =================================================
            // EXISTING DIFFERENT WAREHOUSE ROW
            // =================================================

            if (
                row.warehouse &&
                row.warehouse !==
                    parent_warehouse
            ) {

                row.is_diff_warehouse_row =
                    1;

                row.warehouse =
                    parent_warehouse;
            }
        }
    );

    frm.refresh_field(
        "items"
    );

    calculate_differences(
        frm
    );
}


// =========================================================
// WAREHOUSE FILTER
// =========================================================

function get_warehouse_filter(
    frm
) {

    const company =
        frm.doc.company;

    const stock_selection =
        frm.doc.stock_selection;

    if (!company) {

        return {
            filters: {
                name: [
                    "is",
                    "set_to_null"
                ]
            }
        };
    }

    const filters = {
        company:
            company
    };

    if (
        stock_selection ===
        "Warehouse Selection"
    ) {

        filters.is_group =
            1;

        filters.parent_warehouse =
            [
                "in",
                [
                    "",
                    null
                ]
            ];

    } else if (
        stock_selection ===
        "Zone Selection"
    ) {

        filters.is_group =
            0;

        filters.parent_warehouse =
            [
                "!=",
                ""
            ];

    } else if (
        stock_selection ===
        "Bin Selection"
    ) {

        filters.is_group =
            0;
    }

    return {
        filters:
            filters
    };
}


// =========================================================
// APPLY WAREHOUSE FILTER
// =========================================================

function apply_warehouse_filter(
    frm
) {

    const query =
        () =>
            get_warehouse_filter(
                frm
            );

    // =====================================================
    // PARENT WAREHOUSE
    // =====================================================

    if (
        frm.fields_dict["warehouse"]
    ) {

        frm.set_query(
            "warehouse",
            query
        );
    }

    // =====================================================
    // CHILD TABLE WAREHOUSE
    // =====================================================

    if (
        frm.fields_dict["items"]
    ) {

        const grid =
            frm.fields_dict[
                "items"
            ].grid;

        [
            "warehouse",
            "s_warehouse",
            "t_warehouse"
        ].forEach(
            fieldname => {

                if (
                    grid.get_field(
                        fieldname
                    )
                ) {

                    grid.get_field(
                        fieldname
                    ).get_query =
                        query;
                }
            }
        );

        grid.refresh();
    }
}


// ============================================================
// STOCK TAKING BACKGROUND PROCESSING - STARTED/COMPLETED
// ============================================================

if (frappe.realtime) {

	frappe.realtime.off("stock_taking_complete");

	frappe.realtime.on(
		"stock_taking_complete",
		function (data) {

			if (!data || !data.stock_taking) {
				return;
			}

			// Current form ke liye hi message show karo.
			if (
				typeof cur_frm === "undefined" ||
				!cur_frm.doc ||
				cur_frm.doc.name !== data.stock_taking
			) {
				return;
			}

			let rows = [];

			if (data.delivery_note) {

				rows.push(`
					<tr>
						<td style="padding:6px 12px 6px 0;">
							<b>${__("Delivery Note")}</b>
						</td>

						<td style="padding:6px 0;">
							<a href="/app/delivery-note/${encodeURIComponent(data.delivery_note)}"
								target="_blank">
								${frappe.utils.escape_html(data.delivery_note)}
							</a>

							<span class="indicator-pill yellow"
								style="margin-left:8px;">
								${__("Draft")}
							</span>
						</td>
					</tr>
				`);
			}

			if (data.return_delivery_note) {

				let return_status =
					data.return_delivery_note_status || "Draft";

				let indicator =
					return_status === "Submitted"
						? "green"
						: "yellow";

				rows.push(`
					<tr>
						<td style="padding:6px 12px 6px 0;">
							<b>${__("Return Delivery Note")}</b>
						</td>

						<td style="padding:6px 0;">
							<a href="/app/delivery-note/${encodeURIComponent(data.return_delivery_note)}"
								target="_blank">
								${frappe.utils.escape_html(data.return_delivery_note)}
							</a>

							<span class="indicator-pill ${indicator}"
								style="margin-left:8px;">
								${frappe.utils.escape_html(return_status)}
							</span>
						</td>
					</tr>
				`);
			}

			if (!rows.length) {

				rows.push(`
					<tr>
						<td colspan="2">
							${__("No Delivery Note was required.")}
						</td>
					</tr>
				`);
			}

			frappe.msgprint({
				title: __("Stock Taking Processing Completed"),

				message: `
					<div style="font-size:14px;">

						<p style="margin-bottom:12px;">
							<b>${__("Stock Taking")}:</b>
							${frappe.utils.escape_html(data.stock_taking)}
						</p>

						<p>
							${__(
								"Delivery Note processing has been completed."
							)}
						</p>

						<table style="width:100%; margin-top:10px;">
							<tbody>
								${rows.join("")}
							</tbody>
						</table>

						<p style="margin-top:14px; color:#666;">
							${__(
								"The documents have been created against this Stock Taking."
							)}
						</p>

					</div>
				`,

				indicator: "green",

				primary_action: {
					label: __("Refresh"),

					action() {
						cur_frm.reload_doc();
					},
				},
			});

			// Form status refresh
			if (
				typeof cur_frm !== "undefined" &&
				cur_frm.reload_doc
			) {
				cur_frm.reload_doc();
			}
		}
	);


	// ============================================================
	// BACKGROUND PROCESSING FAILED
	// ============================================================

	frappe.realtime.off("stock_taking_failed");

	frappe.realtime.on(
		"stock_taking_failed",
		function (data) {

			if (!data || !data.stock_taking) {
				return;
			}

			if (
				typeof cur_frm === "undefined" ||
				!cur_frm.doc ||
				cur_frm.doc.name !== data.stock_taking
			) {
				return;
			}

			frappe.msgprint({
				title: __("Stock Taking Processing Failed"),

				message: `
					<div style="font-size:14px;">
						<p>
							${__(
								"Delivery Note creation failed while processing this Stock Taking."
							)}
						</p>

						<p>
							<b>${__("Stock Taking")}:</b>
							${frappe.utils.escape_html(data.stock_taking)}
						</p>

						<p style="color:#888;">
							${__(
								"Please check Error Log for the detailed error."
							)}
						</p>
					</div>
				`,

				indicator: "red",
			});
		}
	);
}

if (frappe.realtime) {

	frappe.realtime.off("stock_taking_return_submitted");

	frappe.realtime.on(
		"stock_taking_return_submitted",
		function (data) {

			if (!data || !data.stock_taking) {
				return;
			}

			if (
				typeof cur_frm === "undefined" ||
				!cur_frm.doc ||
				cur_frm.doc.name !== data.stock_taking
			) {
				return;
			}

			frappe.msgprint({
				title: __("Return Delivery Note Submitted"),

				message: `
					<div style="font-size:14px; line-height:1.7;">

						<p>
							${__(
								"Return Delivery Note has been linked with the Delivery Note and submitted automatically."
							)}
						</p>

						<p>
							<b>${__("Delivery Note")}:</b>
							<a href="/app/delivery-note/${encodeURIComponent(data.delivery_note)}"
								target="_blank">
								${frappe.utils.escape_html(data.delivery_note)}
							</a>
						</p>

						<p>
							<b>${__("Return Delivery Note")}:</b>
							<a href="/app/delivery-note/${encodeURIComponent(data.return_delivery_note)}"
								target="_blank">
								${frappe.utils.escape_html(data.return_delivery_note)}
							</a>
						</p>

					</div>
				`,

				indicator: "green",
			});

			cur_frm.reload_doc();
		}
	);
}