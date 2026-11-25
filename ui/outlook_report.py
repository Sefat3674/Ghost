"""GHOST Outlook Inbox report dashboard."""

import threading
import tkinter as tk
from datetime import datetime

from .scaling import px


def _validate_inbox_report(report):
    if not isinstance(report, dict):
        raise ValueError("Outlook Inbox summary must be a report object.")
    if not isinstance(report.get("overview"), str) or not report["overview"].strip():
        raise ValueError("Outlook Inbox report requires an overview.")
    if not isinstance(report.get("scan_complete"), bool):
        raise ValueError("Outlook Inbox report requires a scan completion status.")
    if not isinstance(report.get("coverage_note"), str):
        raise ValueError("Outlook Inbox report requires a coverage note.")
    if not report["scan_complete"] and not report["coverage_note"].strip():
        raise ValueError("Partial Inbox reports must explain their coverage gaps.")

    metrics = report.get("metrics")
    metric_names = (
        "received_count",
        "unread_count",
        "action_needed_count",
        "meeting_invite_count",
    )
    if not isinstance(metrics, dict):
        raise ValueError("Outlook Inbox report requires metric counts.")
    for name in metric_names:
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Outlook Inbox report has an invalid {name}.")
        if name != "received_count" and value > metrics.get("received_count", 0):
            raise ValueError(f"Outlook Inbox report has an inconsistent {name}.")

    section_fields = {
        "priority_emails": (
            "sender",
            "received",
            "subject",
            "summary",
            "priority",
            "action",
        ),
        "action_items": ("title", "deadline", "source"),
        "upcoming_meetings": ("title", "date", "time", "details"),
        "email_volume_by_hour": ("hour", "count"),
        "category_counts": ("name", "count"),
        "top_senders": ("name", "count"),
    }
    for section, fields in section_fields.items():
        rows = report.get(section)
        if not isinstance(rows, list):
            raise ValueError(f"Outlook Inbox report requires {section}.")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"Outlook Inbox report has an invalid {section} row.")
            for field in fields:
                value = row.get(field)
                if field == "count":
                    if (
                        isinstance(value, bool)
                        or not isinstance(value, int)
                        or value < 0
                    ):
                        raise ValueError(
                            f"Outlook Inbox report has an invalid {section} count."
                        )
                elif not isinstance(value, str):
                    raise ValueError(
                        f"Outlook Inbox report has an invalid {section} field."
                    )
            if (
                section == "priority_emails"
                and row["priority"].casefold() not in {"high", "medium", "low"}
            ):
                raise ValueError("Outlook Inbox report has an invalid priority.")
    return report


class OutlookReportDashboardMixin:
    def show_outlook_inbox_summary(self, report):
        report = _validate_inbox_report(report)
        if threading.current_thread() is not self._main_thread:
            self._safe_ui(self.show_outlook_inbox_summary, report)
            return
        self._render_outlook_inbox_summary(report)

    def _render_outlook_inbox_summary(self, report):
        _validate_inbox_report(report)
        window = getattr(self, "_outlook_inbox_summary_window", None)
        try:
            if window is not None and window.winfo_exists():
                window.deiconify()
                window.lift()
                for child in window.winfo_children():
                    child.destroy()
            else:
                window = tk.Toplevel(self.root)
                self._outlook_inbox_summary_window = window
                window.title("GHOST | Outlook Report")
                window.geometry(f"{px(1180)}x{px(860)}")
                window.minsize(px(900), px(680))
                window.configure(bg=self.col["bg"])
                window.transient(self.root)
        except tk.TclError:
            window = tk.Toplevel(self.root)
            self._outlook_inbox_summary_window = window
            window.title("GHOST | Outlook Report")
            window.geometry(f"{px(1180)}x{px(860)}")
            window.minsize(px(900), px(680))
            window.configure(bg=self.col["bg"])

        header = tk.Frame(
            window,
            bg=self.col["hdr"],
            padx=px(22),
            pady=px(17),
        )
        header.pack(fill="x")
        header_top = tk.Frame(header, bg=self.col["hdr"])
        header_top.pack(fill="x")
        tk.Label(
            header_top,
            text="GHOST  /  OUTLOOK INTELLIGENCE",
            bg=self.col["hdr"],
            fg=self.col["pri"],
            font=("Consolas", 10, "bold"),
        ).pack(side="left")
        tk.Label(
            header_top,
            text="COMPLETE SCAN" if report["scan_complete"] else "PARTIAL SCAN",
            bg=self.col["panel"] if report["scan_complete"] else self.col["red"],
            fg=self.col["green"] if report["scan_complete"] else self.col["bg"],
            padx=px(10),
            pady=px(5),
            font=("Segoe UI", 8, "bold"),
        ).pack(side="right")
        tk.Label(
            header,
            text="Outlook Intelligence Report",
            bg=self.col["hdr"],
            fg=self.col["text"],
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w", pady=px((10, 2)))
        tk.Label(
            header,
            text="Full Inbox | All pages | Read-only",
            bg=self.col["hdr"],
            fg=self.col["dim"],
            font=("Segoe UI", 10),
        ).pack(anchor="w")

        body = tk.Frame(
            window,
            bg=self.col["bg"],
            padx=px(14),
            pady=px(8),
        )
        body.pack(fill="both", expand=True)
        canvas = tk.Canvas(
            body,
            bg=self.col["bg"],
            highlightthickness=0,
        )
        scrollbar = tk.Scrollbar(
            body,
            orient="vertical",
            command=canvas.yview,
            bg=self.col["panel"],
            troughcolor=self.col["bg"],
            activebackground=self.col["pri"],
            highlightthickness=0,
            bd=0,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        content = tk.Frame(canvas, bg=self.col["bg"], padx=px(6), pady=px(6))
        content_window = canvas.create_window(
            (0, 0),
            window=content,
            anchor="nw",
        )
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(content_window, width=event.width),
        )

        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        def create_section(title, row, column, columnspan=1):
            section = tk.Frame(
                content,
                bg=self.col["panel"],
                highlightbackground=self.col["inp_border"],
                highlightthickness=1,
                padx=px(14),
                pady=px(12),
            )
            section.grid(
                row=row,
                column=column,
                columnspan=columnspan,
                sticky="nsew",
                padx=px(6),
                pady=px(6),
            )
            tk.Label(
                section,
                text=title.upper(),
                bg=self.col["panel"],
                fg=self.col["pri"],
                font=("Consolas", 9, "bold"),
            ).pack(anchor="w", pady=px((0, 8)))
            section_body = tk.Frame(section, bg=self.col["panel"])
            section_body.pack(fill="both", expand=True)
            return section_body

        overview_body = create_section("At a glance", 0, 0, 2)
        overview_label = tk.Label(
            overview_body,
            text=report["overview"],
            bg=self.col["panel"],
            fg=self.col["text"],
            font=("Segoe UI", 10),
            justify="left",
            anchor="w",
        )
        overview_label.pack(fill="x")
        overview_label.bind(
            "<Configure>",
            lambda event: overview_label.configure(
                wraplength=max(px(300), event.width)
            ),
        )

        metric_frame = tk.Frame(content, bg=self.col["bg"])
        metric_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        metric_specs = (
            ("Received", "received_count", self.col["pri"]),
            ("Unread", "unread_count", self.col["green"]),
            ("Needs your action", "action_needed_count", self.col["red"]),
            ("Meeting invites", "meeting_invite_count", self.col["mid"]),
        )
        for column, (title, key, accent) in enumerate(metric_specs):
            metric_frame.grid_columnconfigure(column, weight=1)
            card = tk.Frame(
                metric_frame,
                bg=self.col["panel"],
                highlightbackground=self.col["inp_border"],
                highlightthickness=1,
                padx=px(14),
                pady=px(11),
            )
            card.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=px(6),
                pady=px(6),
            )
            tk.Label(
                card,
                text=str(report["metrics"][key]),
                bg=self.col["panel"],
                fg=accent,
                font=("Segoe UI", 22, "bold"),
            ).pack(anchor="w")
            tk.Label(
                card,
                text=title.upper(),
                bg=self.col["panel"],
                fg=self.col["dim"],
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w", pady=px((2, 0)))

        priority_body = create_section("Priority emails | Top 5", 2, 0, 2)
        if not report["priority_emails"]:
            tk.Label(
                priority_body,
                text="No priority messages found.",
                bg=self.col["panel"],
                fg=self.col["dim"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")
        for item in report["priority_emails"]:
            priority = item["priority"].casefold()
            accent = (
                self.col["red"]
                if priority in {"high", "urgent", "critical"}
                else self.col["mid"]
                if priority == "medium"
                else self.col["green"]
            )
            message_card = tk.Frame(
                priority_body,
                bg=self.col["bg"],
                padx=px(12),
                pady=px(10),
            )
            message_card.pack(fill="x", pady=px(4))
            sender_line = tk.Frame(message_card, bg=self.col["bg"])
            sender_line.pack(fill="x")
            initials = "".join(
                part[0].upper() for part in item["sender"].split()[:2]
            ) or "?"
            tk.Label(
                sender_line,
                text=initials,
                bg=self.col["inp_border"],
                fg=self.col["pri"],
                width=4,
                pady=px(3),
                font=("Segoe UI", 8, "bold"),
            ).pack(side="left", padx=(0, px(8)))
            tk.Label(
                sender_line,
                text=item["sender"],
                bg=self.col["bg"],
                fg=self.col["text"],
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left")
            tk.Label(
                sender_line,
                text=item["received"],
                bg=self.col["bg"],
                fg=self.col["dim"],
                font=("Segoe UI", 8),
            ).pack(side="right")
            tk.Label(
                message_card,
                text=item["subject"],
                bg=self.col["bg"],
                fg=self.col["text"],
                font=("Segoe UI", 10, "bold"),
                anchor="w",
                justify="left",
            ).pack(fill="x", pady=px((7, 2)))
            tk.Label(
                message_card,
                text=item["summary"],
                bg=self.col["bg"],
                fg=self.col["dim"],
                font=("Segoe UI", 9),
                anchor="w",
                justify="left",
                wraplength=px(940),
            ).pack(fill="x")
            if item["action"].strip().casefold() not in {"", "none", "n/a"}:
                tk.Label(
                    message_card,
                    text="ACTION  " + item["action"],
                    bg=self.col["bg"],
                    fg=accent,
                    font=("Segoe UI", 8, "bold"),
                    anchor="w",
                    justify="left",
                    wraplength=px(940),
                ).pack(fill="x", pady=px((5, 0)))

        action_body = create_section("Action items", 3, 0)
        if not report["action_items"]:
            tk.Label(
                action_body,
                text="No action items found.",
                bg=self.col["panel"],
                fg=self.col["dim"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")
        for item in report["action_items"]:
            row = tk.Frame(action_body, bg=self.col["panel"])
            row.pack(fill="x", pady=px(5))
            tk.Label(
                row,
                text=">",
                bg=self.col["panel"],
                fg=self.col["green"],
                font=("Consolas", 10, "bold"),
            ).pack(side="left", padx=(0, px(7)))
            details = tk.Frame(row, bg=self.col["panel"])
            details.pack(side="left", fill="x", expand=True)
            tk.Label(
                details,
                text=item["title"],
                bg=self.col["panel"],
                fg=self.col["text"],
                font=("Segoe UI", 9, "bold"),
                anchor="w",
                justify="left",
                wraplength=px(360),
            ).pack(fill="x")
            tk.Label(
                details,
                text=item["source"],
                bg=self.col["panel"],
                fg=self.col["dim"],
                font=("Segoe UI", 8),
                anchor="w",
            ).pack(fill="x")
            tk.Label(
                row,
                text=item["deadline"],
                bg=self.col["panel"],
                fg=self.col["mid"],
                font=("Segoe UI", 8, "bold"),
            ).pack(side="right", padx=(px(8), 0))

        meetings_body = create_section("Upcoming meetings from email", 3, 1)
        if not report["upcoming_meetings"]:
            tk.Label(
                meetings_body,
                text="No upcoming meetings found in Inbox messages.",
                bg=self.col["panel"],
                fg=self.col["dim"],
                font=("Segoe UI", 9),
            ).pack(anchor="w")
        for item in report["upcoming_meetings"]:
            meeting = tk.Frame(meetings_body, bg=self.col["bg"], padx=px(10), pady=px(8))
            meeting.pack(fill="x", pady=px(3))
            tk.Label(
                meeting,
                text=item["date"] + "  " + item["time"],
                bg=self.col["bg"],
                fg=self.col["pri"],
                font=("Consolas", 8, "bold"),
            ).pack(anchor="w")
            tk.Label(
                meeting,
                text=item["title"],
                bg=self.col["bg"],
                fg=self.col["text"],
                font=("Segoe UI", 9, "bold"),
                anchor="w",
            ).pack(fill="x", pady=px((3, 0)))
            tk.Label(
                meeting,
                text=item["details"],
                bg=self.col["bg"],
                fg=self.col["dim"],
                font=("Segoe UI", 8),
                anchor="w",
                justify="left",
                wraplength=px(420),
            ).pack(fill="x")

        def draw_bars(parent, items, label_key, accent):
            if not items:
                tk.Label(
                    parent,
                    text="No data available.",
                    bg=self.col["panel"],
                    fg=self.col["dim"],
                    font=("Segoe UI", 9),
                ).pack(anchor="w")
                return
            maximum = max((item["count"] for item in items), default=0) or 1
            for item in items:
                row = tk.Frame(parent, bg=self.col["panel"])
                row.pack(fill="x", pady=px(3))
                tk.Label(
                    row,
                    text=item[label_key],
                    bg=self.col["panel"],
                    fg=self.col["text"],
                    width=18,
                    anchor="w",
                    font=("Segoe UI", 8),
                ).pack(side="left")
                bar = tk.Canvas(
                    row,
                    height=px(12),
                    bg=self.col["bg"],
                    highlightthickness=0,
                )
                bar.pack(side="left", fill="x", expand=True, padx=px(7))
                count = item["count"]

                def redraw(event, canvas=bar, value=count):
                    canvas.delete("all")
                    if value:
                        width = max(2, int(event.width * value / maximum))
                        canvas.create_rectangle(
                            0,
                            px(2),
                            width,
                            px(10),
                            fill=accent,
                            outline="",
                        )

                bar.bind("<Configure>", redraw)
                tk.Label(
                    row,
                    text=str(count),
                    bg=self.col["panel"],
                    fg=self.col["dim"],
                    width=4,
                    anchor="e",
                    font=("Consolas", 8),
                ).pack(side="right")

        volume_body = create_section("Email volume by hour", 4, 0)
        draw_bars(
            volume_body,
            report["email_volume_by_hour"],
            "hour",
            self.col["pri"],
        )
        categories_body = create_section("By category", 4, 1)
        draw_bars(
            categories_body,
            report["category_counts"],
            "name",
            self.col["green"],
        )
        senders_body = create_section("Top senders", 5, 0)
        draw_bars(
            senders_body,
            report["top_senders"],
            "name",
            self.col["mid"],
        )
        coverage_body = create_section("Report coverage", 5, 1)
        tk.Label(
            coverage_body,
            text=report["coverage_note"],
            bg=self.col["panel"],
            fg=self.col["text"] if report["scan_complete"] else self.col["red"],
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=px(430),
        ).pack(fill="x")

        footer = tk.Frame(
            window,
            bg=self.col["bg"],
            padx=px(20),
            pady=px((0, 12)),
        )
        footer.pack(fill="x")
        tk.Label(
            footer,
            text=(
                "GENERATED  "
                + datetime.now().astimezone().strftime("%Y-%m-%d  %H:%M")
            ),
            bg=self.col["bg"],
            fg=self.col["dim"],
            font=("Consolas", 8),
        ).pack(side="left")
        tk.Button(
            footer,
            text="CLOSE",
            command=window.destroy,
            bg=self.col["pri"],
            fg=self.col["bg"],
            activebackground=self.col["acc2"],
            activeforeground=self.col["bg"],
            relief="flat",
            bd=0,
            padx=px(18),
            pady=px(8),
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="right")
        window.deiconify()
        window.lift()

