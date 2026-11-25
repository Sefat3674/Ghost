"""Smart Manufacturing dashboard rendering mixed into the desktop UI."""

import threading
import tkinter as tk

from ui_scaling import HiDPICanvas as _HiDPICanvas, px


class SmartManufacturingDashboardMixin:
    def show_smart_manufacturing_dashboard(self, data):
        """Thread-safe entry point for Smart Manufacturing visualization."""
        if not isinstance(data, dict):
            return

        self._safe_ui(self._render_smart_manufacturing_dashboard, data)

    def _render_smart_manufacturing_dashboard(self, data):
        """Render a question-specific Smart Manufacturing dashboard."""
        try:
            win = self._sm_dashboard_window

            if win is None or not win.winfo_exists():
                win = tk.Toplevel(self.root)
                win.title(
                    f"{self.brand['company'].title()} | GHOST — "
                    "Smart Manufacturing Intelligence"
                )
                win.geometry(f"{px(1150)}x{px(780)}")
                win.minsize(px(850), px(550))
                win.configure(bg=self.col["bg"])
                self._sm_dashboard_window = win

            for widget in win.winfo_children():
                widget.destroy()

            kind = str(data.get("kind", "summary")).lower()
            title = str(data.get("title", "Smart Manufacturing"))
            summary = data.get("summary") or {}
            items = data.get("items") or []
            details = data.get("details") or []
            filters = data.get("filters") or {}
            filter_options = data.get("filter_options") or {}

            header = tk.Frame(win, bg=self.col["hdr"], padx=px(20), pady=px(14))
            header.pack(fill="x")

            tk.Label(
                header, text="GHOST  /  SMART MANUFACTURING",
                bg=self.col["hdr"], fg=self.col["pri"],
                font=("Consolas", 11, "bold")
            ).pack(anchor="w")

            tk.Label(
                header, text=title,
                bg=self.col["hdr"], fg=self.col["text"],
                font=("Segoe UI", 19, "bold")
            ).pack(anchor="w", pady=px((7, 0)))

            filter_text = "  |  ".join(
                f"{key.replace('_', ' ').title()}: {value}"
                for key, value in filters.items() if value
            )

            if filter_text:
                tk.Label(
                    header, text=filter_text,
                    bg=self.col["hdr"], fg=self.col["dim"],
                    font=("Segoe UI", 9)
                ).pack(anchor="w", pady=px((5, 0)))

            companies = filter_options.get("companies", [])
            business_units = filter_options.get("business_units", [])
            locations = filter_options.get("locations", [])

            company_var = tk.StringVar(
                value=filters.get("company") or "All Companies"
            )
            business_var = tk.StringVar(
                value=filters.get("business_unit") or "All Business Units"
            )
            location_var = tk.StringVar(
                value=filters.get("location") or "All Locations"
            )

            filter_frame = tk.Frame(header, bg=self.col["hdr"])
            filter_frame.pack(fill="x", pady=px((12, 0)))

            def record_names(records, default):
                return [default] + [
                    item["name"] for item in records
                    if item.get("name")
                ]

            def create_search_dropdown(parent, label, variable, options_getter):
                wrapper = tk.Frame(parent, bg=self.col["hdr"])
                wrapper.pack(side="left", padx=px((0, 9)))

                tk.Label(
                    wrapper,
                    text=label.upper(),
                    bg=self.col["hdr"],
                    fg=self.col["dim"],
                    font=("Segoe UI", 8, "bold")
                ).pack(anchor="w", pady=px((0, 4)))

                button = tk.Button(
                    wrapper,
                    text=f"{variable.get()}  ?",
                    bg=self.col["panel"],
                    fg=self.col["text"],
                    activebackground=self.col["pri"],
                    activeforeground=self.col["bg"],
                    relief="flat",
                    bd=0,
                    padx=px(12),
                    pady=px(8),
                    width=23,
                    anchor="w",
                    font=("Segoe UI", 9),
                    cursor="hand2"
                )
                button.pack(fill="x")

                def update_button(*_):
                    button.configure(text=f"{variable.get()}  ?")

                variable.trace_add("write", update_button)

                def open_popup():
                    popup = tk.Toplevel(win)
                    popup.withdraw()
                    popup.transient(win)
                    popup.configure(bg=self.col["panel"])
                    popup.title(f"Select {label}")

                    popup_width = max(px(280), button.winfo_width())
                    popup_height = px(275)

                    button.update_idletasks()
                    x = button.winfo_rootx()
                    y = button.winfo_rooty() + button.winfo_height() + 3

                    popup.geometry(
                        f"{popup_width}x{popup_height}+{x}+{y}"
                    )
                    popup.resizable(False, False)

                    body = tk.Frame(
                        popup, bg=self.col["panel"], padx=px(10), pady=px(10)
                    )
                    body.pack(fill="both", expand=True)

                    search_var = tk.StringVar()

                    search = tk.Entry(
                        body,
                        textvariable=search_var,
                        bg=self.col["bg"],
                        fg=self.col["text"],
                        insertbackground=self.col["text"],
                        relief="flat",
                        bd=0,
                        font=("Segoe UI", 10)
                    )
                    search.pack(fill="x", ipady=px(9), pady=px((0, 9)))
                    search.insert(0, "")

                    list_frame = tk.Frame(body, bg=self.col["panel"])
                    list_frame.pack(fill="both", expand=True)

                    scrollbar = tk.Scrollbar(list_frame)
                    scrollbar.pack(side="right", fill="y")

                    results = tk.Listbox(
                        list_frame,
                        bg=self.col["panel"],
                        fg=self.col["text"],
                        selectbackground=self.col["pri"],
                        selectforeground=self.col["bg"],
                        activestyle="none",
                        relief="flat",
                        bd=0,
                        highlightthickness=0,
                        font=("Segoe UI", 9),
                        yscrollcommand=scrollbar.set
                    )
                    results.pack(side="left", fill="both", expand=True)
                    scrollbar.configure(command=results.yview)

                    current_options = []

                    def refresh_results(*_):
                        nonlocal current_options

                        query = search_var.get().strip().casefold()
                        available = options_getter()
                        current_options = [
                            item for item in available
                            if query in item.casefold()
                        ]
                        results.delete(0, tk.END)

                        for item in current_options:
                            results.insert(tk.END, "  " + item)

                        if not current_options:
                            results.insert(tk.END, "  No matching results")

                    def choose_item(event=None):
                        selection = results.curselection()
                        if not selection:
                            return "break"

                        index = selection[0]
                        if index >= len(current_options):
                            return "break"

                        variable.set(current_options[index])
                        popup.destroy()
                        return "break"

                    def search_enter(event=None):
                        if current_options:
                            results.selection_clear(0, tk.END)
                            results.selection_set(0)
                            results.activate(0)
                            results.focus_set()
                        return "break"

                    search_var.trace_add("write", refresh_results)
                    results.bind("<Double-Button-1>", choose_item)
                    results.bind("<Return>", choose_item)
                    results.bind("<ButtonRelease-1>", choose_item)
                    search.bind("<Return>", search_enter)
                    popup.bind("<Escape>", lambda e: popup.destroy())

                    refresh_results()
                    popup.deiconify()
                    popup.lift()
                    search.focus_set()

                button.configure(command=open_popup)
                return wrapper

            def company_options():
                return record_names(companies, "All Companies")

            def business_options():
                selected_company = company_var.get()
                selected_record = next(
                    (
                        item for item in companies
                        if item.get("name") == selected_company
                    ),
                    None
                )
                company_id = (
                    selected_record.get("id")
                    if selected_record else None
                )
                available = [
                    item["name"] for item in business_units
                    if item.get("name")
                    and (
                        company_id is None
                        or str(item.get("motherCompanyId")) == str(company_id)
                    )
                ]
                return ["All Business Units"] + available

            def location_options():
                return record_names(locations, "All Locations")

            create_search_dropdown(
                filter_frame, "Mother Company",
                company_var, company_options
            )
            create_search_dropdown(
                filter_frame, "Business Unit",
                business_var, business_options
            )
            create_search_dropdown(
                filter_frame, "Location",
                location_var, location_options
            )

            def update_business_units(*_):
                if business_var.get() not in business_options():
                    business_var.set("All Business Units")

            company_var.trace_add("write", update_business_units)
            update_business_units()

            def apply_sm_filters():
                if not callable(self.on_sm_filter_change):
                    self.write_log(
                        "ERR: Smart Manufacturing filter callback is not connected."
                    )
                    return

                selected = {
                    "company": company_var.get(),
                    "business_unit": business_var.get(),
                    "location": location_var.get()
                }
                threading.Thread(
                    target=self.on_sm_filter_change,
                    args=(selected,),
                    daemon=True
                ).start()

            tk.Button(
                filter_frame,
                text="Apply Filters",
                command=apply_sm_filters,
                bg=self.col["pri"],
                fg=self.col["bg"],
                activebackground=self.col["pri"],
                relief="flat",
                padx=px(12),
                pady=px(8),
                font=("Segoe UI", 9, "bold"),
                cursor="hand2"
            ).pack(side="left", padx=px((5, 0)), pady=px((17, 0)))

            container = tk.Frame(win, bg=self.col["bg"])
            container.pack(fill="both", expand=True)

            canvas = tk.Canvas(
                container, bg=self.col["bg"],
                highlightthickness=0
            )
            scrollbar = tk.Scrollbar(
                container, orient="vertical",
                command=canvas.yview
            )
            body = tk.Frame(canvas, bg=self.col["bg"])

            body.bind(
                "<Configure>",
                lambda event: canvas.configure(
                    scrollregion=canvas.bbox("all")
                )
            )
            body_window = canvas.create_window(
                (0, 0), window=body, anchor="nw"
            )
            canvas.bind(
                "<Configure>",
                lambda event: canvas.itemconfigure(
                    body_window, width=event.width
                )
            )
            canvas.configure(yscrollcommand=scrollbar.set)
            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            body.configure(padx=px(18), pady=px(18))

            def section_heading(text):
                tk.Label(
                    body, text=text.upper(),
                    bg=self.col["bg"], fg=self.col["pri"],
                    font=("Consolas", 11, "bold")
                ).pack(anchor="w", pady=px((12, 8)))

            def show_table(columns, rows, widths=None):
                table_frame = tk.Frame(body, bg=self.col["panel"])
                table_frame.pack(fill="x", pady=px(5))
                table = tk.Frame(table_frame, bg=self.col["panel"])
                table.pack(fill="x", padx=px(8), pady=px(8))

                for col_index, column in enumerate(columns):
                    tk.Label(
                        table, text=column.replace("_", " ").title(),
                        bg=self.col["hdr"], fg=self.col["pri"],
                        font=("Segoe UI", 9, "bold"),
                        anchor="w",
                        padx=px(7), pady=px(9),
                        width=widths[col_index] if widths else 16
                    ).grid(row=0, column=col_index, sticky="nsew")

                for row_index, record in enumerate(rows, start=1):
                    for col_index, column in enumerate(columns):
                        if isinstance(record, dict):
                            value = record.get(column, "")
                        else:
                            value = record
                        tk.Label(
                            table, text=str(value),
                            bg=self.col["panel"], fg=self.col["text"],
                            font=("Segoe UI", 9),
                            anchor="w", padx=px(7), pady=px(7),
                            wraplength=px(180)
                        ).grid(
                            row=row_index, column=col_index,
                            sticky="nsew"
                        )

            if kind == "summary":
                section_heading("Machine audit KPIs")
                metrics = [
                    ("Total Machines", "total_machines"),
                    ("Smartable Machines", "smartable_machines"),
                    ("Smart Machines", "smart_machines"),
                    ("Non-Smartable", "non_smartable_machines"),
                    ("Manual Machines", "manual_machines"),
                    ("OEE Enabled", "oee_enabled_machines"),
                    ("Runtime Enabled", "runtime_enabled_machines"),
                ]
                grid = tk.Frame(body, bg=self.col["bg"])
                grid.pack(fill="x")

                for index, (label, key) in enumerate(metrics):
                    value = summary.get(key, 0)
                    card = tk.Frame(
                        grid, bg=self.col["panel"],
                        padx=px(14), pady=px(13),
                        highlightbackground=self.col["dim"],
                        highlightthickness=px(1)
                    )
                    card.grid(
                        row=index // 3, column=index % 3,
                        padx=px(5), pady=px(5), sticky="nsew"
                    )
                    tk.Label(
                        card, text=label.upper(),
                        bg=self.col["panel"], fg=self.col["dim"],
                        font=("Consolas", 8, "bold")
                    ).pack(anchor="w")
                    tk.Label(
                        card,
                        text=f"{value:,}" if isinstance(value, (int, float))
                        else str(value),
                        bg=self.col["panel"], fg=self.col["pri"],
                        font=("Segoe UI", 21, "bold")
                    ).pack(anchor="w", pady=px((7, 0)))

                for column in range(3):
                    grid.grid_columnconfigure(column, weight=1)

                section_heading("Performance percentages")
                percentages = [
                    ("Smartable", "smartable_machine_percentage"),
                    ("Smart", "smart_machine_percentage"),
                    ("Manual", "manual_machine_percentage"),
                    ("Non-Smartable", "non_smartable_percentage"),
                    ("OEE", "oee_percentage"),
                    ("Runtime", "runtime_percentage"),
                ]
                percentage_rows = [
                    {
                        "metric": label,
                        "percentage": f"{summary.get(key, 0):.2f}%"
                    }
                    for label, key in percentages
                ]
                show_table(["metric", "percentage"], percentage_rows, [24, 18])

            elif kind == "ranking":
                section_heading("Section ranking")
                if not items:
                    tk.Label(
                        body, text="No ranking data available.",
                        bg=self.col["bg"], fg=self.col["text"]
                    ).pack(anchor="w")
                else:
                    chart = _HiDPICanvas(
                        body, scale=self.S,
                        height=px(max(160, len(items) * 58)),
                        bg=self.col["panel"], highlightthickness=0
                    )
                    chart.pack(fill="x", pady=px(5))
                    values = [
                        float(item.get("total_machines", 0) or 0)
                        for item in items
                    ]
                    maximum = max(values or [1]) or 1
                    chart.bind(
                        "<Configure>",
                        lambda event: self._draw_sm_ranking_chart(
                            chart, items, maximum, event.width / self.S
                        )
                    )
                    self._draw_sm_ranking_chart(chart, items, maximum, 1000)
                    ranking_rows = [
                        {
                            "section": item.get("name", ""),
                            "total": item.get("total_machines", 0),
                            "smartable": item.get("smartable_machines", 0),
                            "non_smartable": item.get(
                                "non_smartable_machines", 0
                            ),
                        }
                        for item in items
                    ]
                    section_heading("Ranking data")
                    show_table(
                        ["section", "total", "smartable", "non_smartable"],
                        ranking_rows,
                        [25, 12, 14, 18]
                    )

            elif kind == "zero_sections":
                section_heading("Sections requiring attention")
                rows = [{"section": str(item)} for item in items]
                tk.Label(
                    body, text=f"Total affected sections: {len(rows)}",
                    bg=self.col["panel"], fg=self.col["acc"],
                    font=("Segoe UI", 13, "bold"),
                    padx=px(14), pady=px(12)
                ).pack(fill="x", pady=px(5))
                show_table(["section"], rows, [55])

            elif kind == "details":
                section_heading("Machine audit details")
                detail_columns = [
                    "section", "mother_company", "business_unit",
                    "location", "total_machines", "smartable_machines",
                    "smartable_percentage", "smart_machines",
                    "smart_percentage", "non_smartable_machines",
                    "manual_machines", "oee_enabled", "runtime_enabled",
                    "misbp", "automation_engineer", "business_coordinator"
                ]
                rows = []
                for item in details:
                    row = dict(item)
                    for key in ("smartable_percentage", "smart_percentage"):
                        if key in row:
                            row[key] = f"{float(row[key] or 0):.2f}%"
                    rows.append(row)
                show_table(detail_columns, rows)

            else:
                section_heading("Dashboard")
                tk.Label(
                    body, text=f"Unsupported dashboard type: {kind}",
                    bg=self.col["bg"], fg=self.col["red"]
                ).pack(anchor="w")

            win.lift()

        except Exception as exc:
            self.write_log(f"ERR: Smart Manufacturing dashboard: {exc}")

    def _draw_sm_ranking_chart(self, chart, items, maximum, width):
        """Draw native Tkinter horizontal ranking bars."""
        chart.delete("all")
        bar_left = 220
        bar_right = max(bar_left + 50, width - 100)
        available = bar_right - bar_left

        for index, item in enumerate(items):
            y = 28 + index * 58
            name = str(item.get("name", "Unknown"))
            value = float(item.get("total_machines", 0) or 0)
            bar_width = (value / maximum) * available
            chart.create_text(
                15, y + 10, text=name[:27],
                fill=self.col["text"],
                anchor="w", font=("Segoe UI", 10)
            )
            chart.create_rectangle(
                bar_left, y, bar_right, y + 24,
                fill=self.col["dimmer"], outline=""
            )
            chart.create_rectangle(
                bar_left, y, bar_left + bar_width, y + 24,
                fill=self.col["pri"], outline=""
            )
            chart.create_text(
                bar_right + 8, y + 12,
                text=f"{int(value):,}",
                fill=self.col["text"],
                anchor="w", font=("Consolas", 9, "bold")
            )
