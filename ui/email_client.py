"""Outlook-style mail workspace for the GHOST desktop UI."""

from html.parser import HTMLParser
import re
import threading
import tkinter as tk
from tkinter import ttk


_FOLDERS = (
    ("Inbox", "inbox"),
    ("Drafts", "drafts"),
    ("Sent Items", "sentitems"),
    ("Archive", "archive"),
    ("Junk Email", "junkemail"),
    ("Deleted Items", "deleteditems"),
)


def is_email_client_command(command):
    return parse_email_client_command(command) is not None


def parse_recipients(value):
    recipients = []
    for address in re.split(r"[,;]", value or ""):
        address = address.strip()
        if address.casefold() == "none":
            continue
        match = re.search(r"<([^<>]+)>$", address)
        recipients.append(match.group(1).strip() if match else address)
    return [address for address in recipients if address]


def _strip_html(value):
    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_data(self, data):
            self.parts.append(data)

        def handle_starttag(self, tag, attrs):
            if tag.lower() in {"br", "p", "div", "li"}:
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag.lower() in {"p", "div", "li"}:
                self.parts.append("\n")

    extractor = TextExtractor()
    extractor.feed(value)
    return "".join(extractor.parts).strip()


def plain_text_body(value, body_type=None):
    if isinstance(value, dict):
        body_type = value.get("contentType", body_type)
        value = value.get("content", "")
    if not isinstance(value, str):
        return ""
    if str(body_type or "").casefold() == "html":
        return _strip_html(value)
    return value


def format_recipients(value):
    if not isinstance(value, list):
        return str(value or "None")
    formatted = []
    for recipient in value:
        if isinstance(recipient, dict):
            email = str(recipient.get("email") or "").strip()
            name = str(recipient.get("name") or "").strip()
            formatted.append(f"{name} <{email}>" if name and email and name != email else email or name)
        else:
            formatted.append(str(recipient))
    return ", ".join(item for item in formatted if item) or "None"


def _folder_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def parse_email_client_command(command):
    normalized = re.sub(r"[^a-z0-9]+", " ", str(command or "").casefold()).strip()
    for prefix in ("ghost please ", "please ", "ghost "):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
            break

    folders = {
        "drafts": {
            "drafts",
            "draft",
            "open draft",
            "open drafts",
            "open my drafts",
            "open outlook draft",
            "open outlook drafts",
            "open outlook mail drafts",
            "open email drafts",
            "show draft",
            "show drafts",
            "show me drafts",
            "show my drafts",
            "show outlook draft",
            "show outlook drafts",
            "show outlook mail drafts",
            "show email drafts",
        },
        "sentitems": {
            "sent",
            "sent items",
            "sent mail",
            "open sent",
            "open my sent items",
            "open my sent mail",
            "open sent items",
            "open sent mail",
            "open outlook sent",
            "open outlook sent items",
            "open outlook mail sent items",
            "show sent",
            "show me sent items",
            "show sent items",
            "show sent mail",
            "show outlook sent",
            "show outlook sent items",
            "show outlook mail sent items",
        },
        "inbox": {
            "inbox",
            "open inbox",
            "open my inbox",
            "show inbox",
            "show me inbox",
        },
    }
    for folder, phrases in folders.items():
        if normalized in phrases:
            return {"action": "open", "folder": folder}

    if normalized in {
        "new email",
        "new mail",
        "create email",
        "create new email",
        "compose email",
        "compose an email",
        "compose mail",
        "compose a mail",
        "compose new email",
        "open compose",
        "write email",
        "write an email",
        "write a mail",
        "write a new mail",
        "write a new email",
        "send email",
        "send an email",
        "send a mail",
        "open new email",
        "open new mail",
    }:
        return {"action": "compose"}

    if normalized in {
        "open email",
        "open my email",
        "open mail",
        "open my mail",
        "open outlook",
        "open outlook mail",
        "open email interface",
        "open outlook email interface",
        "open mail interface",
        "open outlook interface",
        "open interface",
        "interface open",
        "show email",
        "show me email",
        "show mail",
        "show me mail",
        "show outlook",
        "show outlook mail",
        "show me outlook mail",
        "launch email",
        "launch outlook mail",
    }:
        return {"action": "open"}
    return None


def build_send_request(draft_id):
    if not isinstance(draft_id, str) or not draft_id.strip():
        raise ValueError("A valid Outlook draft ID is required.")
    return (
        "Send the selected Personal Outlook draft once. "
        f"Draft ID: {draft_id.strip()}. Re-read and display its actual complete "
        "To, CC, BCC, subject, and body, then ask for separate explicit approval. "
        "Do not send before approval, create another draft, or retry a send."
    )


class OutlookEmailClientMixin:
    def open_email_client(self, folder=None, compose=False):
        if threading.current_thread() is not self._main_thread:
            self._safe_ui(self.open_email_client, folder, compose)
            return

        folder_labels = {value: label for label, value in _FOLDERS}
        requested_folder = folder if folder in folder_labels else None
        existing = getattr(self, "_email_client_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.deiconify()
                existing.lift()
                existing.focus_force()
                if requested_folder:
                    if self._email_busy:
                        self._email_pending_folder = (
                            requested_folder, folder_labels[requested_folder]
                        )
                    else:
                        self._email_select_folder(
                            requested_folder, folder_labels[requested_folder]
                        )
                if compose:
                    self._email_new_message()
                return
        except tk.TclError:
            pass

        self._email_busy = False
        self._email_request_id = getattr(self, "_email_request_id", 0) + 1
        self._email_current_folder = requested_folder or "inbox"
        self._email_current_label = folder_labels.get(
            self._email_current_folder, "Inbox"
        )
        self._email_search_query = ""
        self._email_next_cursor = None
        self._email_seen_cursors = set()
        self._email_message_rows = {}
        self._email_reviewed_drafts = set()
        self._email_send_requested = getattr(self, "_email_send_requested", set())
        self._email_pending_folder = None
        self._email_previous_ttk_theme = None
        self._email_folders = []
        self._email_current_message = None

        self._email_client_window = tk.Toplevel(self.root)
        self._email_client_window.title("GHOST | Outlook Mail")
        self._email_client_window.geometry("1260x780")
        self._email_client_window.minsize(980, 620)
        self._email_client_window.configure(bg=self.col["bg"])
        self._email_client_window.protocol(
            "WM_DELETE_WINDOW", self._close_email_client
        )
        self._build_email_client()
        self._email_render_folders([])
        self._email_load_folders()
        if compose:
            self._email_client_window.after_idle(self._email_new_message)

    def _email_window_exists(self):
        window = getattr(self, "_email_client_window", None)
        try:
            return window is not None and bool(window.winfo_exists())
        except tk.TclError:
            return False

    def _close_email_client(self):
        window = getattr(self, "_email_client_window", None)
        self._email_request_id = getattr(self, "_email_request_id", 0) + 1
        self._email_busy = False
        self._email_client_window = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
        previous_theme = getattr(self, "_email_previous_ttk_theme", None)
        if previous_theme:
            try:
                ttk.Style(self.root).theme_use(previous_theme)
            except tk.TclError:
                pass
            self._email_previous_ttk_theme = None

    def _build_email_client(self):
        col = self.col
        win = self._email_client_window

        header = tk.Frame(win, bg=col["hdr"], highlightthickness=1,
                          highlightbackground=col["inp_border"])
        header.pack(fill="x", padx=8, pady=(8, 6))
        title = tk.Label(
            header, text="GHOST  /  OUTLOOK MAIL", bg=col["hdr"], fg=col["pri"],
            font=("Consolas", 13, "bold"), padx=14, pady=10,
        )
        title.pack(side="left")
        self._email_status = tk.Label(
            header, text="Connecting to Personal Outlook...", bg=col["hdr"],
            fg=col["mid"], font=("Consolas", 9),
        )
        self._email_status.pack(side="right", padx=12)

        toolbar = tk.Frame(win, bg=col["bg"])
        toolbar.pack(fill="x", padx=8, pady=(0, 6))
        self._email_search = tk.Entry(
            toolbar, bg=col["input"], fg=col["text"],
            insertbackground=col["text"], relief="flat",
            highlightthickness=1, highlightbackground=col["inp_border"],
            highlightcolor=col["pri"], font=("Segoe UI", 10),
        )
        self._email_search.pack(side="left", fill="x", expand=True, ipady=7)
        self._email_search.insert(0, "Search all mail...")
        self._email_search.bind("<FocusIn>", self._email_search_focus)
        self._email_search.bind("<Return>", lambda _event: self._email_search_mail())
        self._email_button(toolbar, "Search", self._email_search_mail).pack(
            side="left", padx=(6, 4)
        )
        self._email_button(toolbar, "Refresh", self._email_refresh).pack(
            side="left", padx=4
        )
        self._email_button(toolbar, "New Email", self._email_new_message,
                           accent=col["pri"]).pack(side="left", padx=(4, 0))

        content = tk.Frame(win, bg=col["bg"])
        content.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._email_sidebar = tk.Frame(
            content, bg=col["panel"], width=178,
            highlightthickness=1, highlightbackground=col["inp_border"],
        )
        self._email_sidebar.pack(side="left", fill="y")
        self._email_sidebar.pack_propagate(False)
        tk.Label(
            self._email_sidebar, text="FOLDERS", bg=col["panel"], fg=col["mid"],
            font=("Consolas", 9, "bold"), anchor="w", padx=12, pady=12,
        ).pack(fill="x")
        folder_shell = tk.Frame(self._email_sidebar, bg=col["panel"])
        folder_shell.pack(fill="both", expand=True)
        self._email_folder_canvas = tk.Canvas(
            folder_shell, bg=col["panel"], highlightthickness=0, borderwidth=0
        )
        self._email_folder_canvas.pack(side="left", fill="both", expand=True)
        folder_scroll = ttk.Scrollbar(
            folder_shell, orient="vertical",
            command=self._email_folder_canvas.yview,
        )
        folder_scroll.pack(side="right", fill="y")
        self._email_folder_canvas.configure(yscrollcommand=folder_scroll.set)
        self._email_folder_area = tk.Frame(
            self._email_folder_canvas, bg=col["panel"]
        )
        folder_window = self._email_folder_canvas.create_window(
            (0, 0), window=self._email_folder_area, anchor="nw"
        )
        self._email_folder_area.bind(
            "<Configure>",
            lambda _event: self._email_folder_canvas.configure(
                scrollregion=self._email_folder_canvas.bbox("all")
            ),
        )
        self._email_folder_canvas.bind(
            "<Configure>",
            lambda event: self._email_folder_canvas.itemconfigure(
                folder_window, width=event.width
            ),
        )

        center = tk.Frame(content, bg=col["panel"], width=455,
                          highlightthickness=1, highlightbackground=col["inp_border"])
        center.pack(side="left", fill="y", padx=(6, 0))
        center.pack_propagate(False)
        self._email_list_title = tk.Label(
            center, text="INBOX", bg=col["panel"], fg=col["pri"],
            font=("Consolas", 10, "bold"), anchor="w", padx=10, pady=10,
        )
        self._email_list_title.pack(fill="x")
        style = ttk.Style(win)
        current_theme = style.theme_use()
        if current_theme != "clam" and "clam" in style.theme_names():
            self._email_previous_ttk_theme = current_theme
            style.theme_use("clam")
        style.configure(
            "GhostMail.Treeview", background=col["input"], foreground=col["text"],
            fieldbackground=col["input"], rowheight=28, borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "GhostMail.Treeview.Heading", background=col["hdr"],
            foreground=col["mid"], relief="flat", font=("Consolas", 8, "bold"),
        )
        style.map(
            "GhostMail.Treeview", background=[("selected", col["dim"])],
            foreground=[("selected", col["text"])],
        )
        list_shell = tk.Frame(center, bg=col["panel"])
        list_shell.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._email_tree = ttk.Treeview(
            list_shell, columns=("sender", "subject", "date"),
            show="headings", style="GhostMail.Treeview", selectmode="browse",
        )
        for column, heading, width in (
            ("sender", "FROM", 118),
            ("subject", "SUBJECT", 190),
            ("date", "RECEIVED", 98),
        ):
            self._email_tree.heading(column, text=heading)
            self._email_tree.column(column, width=width, minwidth=54,
                                    stretch=column == "subject")
        self._email_tree.tag_configure(
            "unread", foreground=col["text"], font=("Segoe UI", 9, "bold")
        )
        self._email_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_shell, orient="vertical",
                               command=self._email_tree.yview)
        scroll.pack(side="right", fill="y")
        self._email_tree.configure(yscrollcommand=scroll.set)
        self._email_tree.bind("<<TreeviewSelect>>", self._email_select_message)
        self._email_more_button = self._email_button(
            center, "Load more", self._email_load_more
        )
        self._email_more_button.pack(fill="x", padx=8, pady=(0, 8))
        self._email_more_button.configure(state="disabled")

        self._email_reader_frame = tk.Frame(
            content, bg=col["panel"], highlightthickness=1,
            highlightbackground=col["inp_border"],
        )
        self._email_reader_frame.pack(
            side="left", fill="both", expand=True, padx=(6, 0)
        )
        self._email_build_reader()
        self._email_render_message(None)

    def _email_build_reader(self):
        reader = getattr(self, "_email_reader_frame", None)
        if reader is None or not reader.winfo_exists():
            return
        for child in reader.winfo_children():
            child.destroy()

        col = self.col
        self._email_reader_subject = tk.Label(
            reader, text="Select a message", bg=col["panel"], fg=col["text"],
            font=("Segoe UI", 15, "bold"), anchor="w", justify="left",
            wraplength=600, padx=16, pady=0,
        )
        self._email_reader_subject.pack(fill="x", pady=(16, 8))
        self._email_reader_meta = tk.Label(
            reader, text="", bg=col["panel"], fg=col["mid"],
            font=("Segoe UI", 9), anchor="w", justify="left",
            padx=16, pady=0,
        )
        self._email_reader_meta.pack(fill="x", pady=(0, 8))
        self._email_actions = tk.Frame(reader, bg=col["panel"])
        self._email_actions.pack(fill="x", padx=10, pady=(0, 6))
        first_action_row = tk.Frame(self._email_actions, bg=col["panel"])
        first_action_row.pack(fill="x")
        second_action_row = tk.Frame(self._email_actions, bg=col["panel"])
        second_action_row.pack(fill="x")
        self._email_action_buttons = {}
        for name, label, callback in (
            ("reply", "Reply", self._email_reply),
            ("reply_all", "Reply All", self._email_reply_all),
            ("forward", "Forward", self._email_forward),
            ("edit", "Edit Draft", self._email_edit_draft),
            ("send", "Send via GHOST", self._email_request_send),
            ("archive", "Archive", self._email_archive),
            ("delete", "Delete", self._email_delete),
        ):
            row = (
                first_action_row
                if name in {"reply", "reply_all", "forward", "edit"}
                else second_action_row
            )
            button = self._email_button(row, label, callback)
            button.pack(side="left", padx=3)
            self._email_action_buttons[name] = button
            button.configure(state="disabled")

        body_shell = tk.Frame(reader, bg=col["panel"])
        body_shell.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._email_reader_body = tk.Text(
            body_shell, wrap="word", bg=col["input"], fg=col["text"],
            insertbackground=col["text"], relief="flat", padx=16, pady=14,
            font=("Segoe UI", 10), state="disabled",
        )
        self._email_reader_body.pack(side="left", fill="both", expand=True)
        body_scroll = tk.Scrollbar(
            body_shell, orient="vertical", command=self._email_reader_body.yview,
            bg=col["panel"], troughcolor=col["hdr"], activebackground=col["mid"],
            relief="flat", borderwidth=0, width=8,
        )
        body_scroll.pack(side="right", fill="y")
        self._email_reader_body.configure(yscrollcommand=body_scroll.set)

    def _email_button(self, parent, text, command, accent=None):
        col = self.col
        return tk.Button(
            parent, text=text, command=command,
            bg=col["input"], fg=accent or col["text"],
            activebackground=col["dim"], activeforeground=col["text"],
            relief="flat", borderwidth=0, padx=8, pady=6,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
        )

    def _email_search_focus(self, _event=None):
        if self._email_search.get() == "Search all mail...":
            self._email_search.delete(0, tk.END)

    def _email_render_folders(self, folders):
        self._email_folders = list(folders)
        for child in self._email_folder_area.winfo_children():
            child.destroy()

        entries = list(_FOLDERS)
        seen = {
            _folder_key(name)
            for label, value in entries
            for name in (label, value)
        }
        for folder in folders:
            if not isinstance(folder, dict):
                continue
            value = str(folder.get("path") or folder.get("name") or "").strip()
            label = str(folder.get("name") or value).strip()
            keys = {_folder_key(value), _folder_key(label)}
            if not value or keys & seen:
                continue
            seen.update(keys)
            entries.append((label, value))

        self._email_folder_entries = entries
        for label, value in entries:
            is_selected = value.casefold() == self._email_current_folder.casefold()
            button = tk.Button(
                self._email_folder_area, text=label, anchor="w",
                command=lambda folder=value, name=label: self._email_select_folder(folder, name),
                bg=self.col["dim"] if is_selected else self.col["panel"],
                fg=self.col["pri"] if is_selected else self.col["text"],
                activebackground=self.col["dim"], activeforeground=self.col["pri"],
                relief="flat", borderwidth=0, padx=13, pady=8,
                font=("Segoe UI", 9), cursor="hand2",
            )
            button.pack(fill="x")

    def _email_load_folders(self):
        def operation():
            collected = []
            cursor = None
            seen = set()
            for _page in range(20):
                arguments = {"recursive": True}
                if cursor:
                    arguments["cursor"] = cursor
                data = self._email_call_tool(
                    "outlook_list_folders", arguments, "Mail folders"
                )
                page = data.get("folders")
                if not isinstance(page, list):
                    raise ValueError("Outlook folder response has no folders list.")
                collected.extend(item for item in page if isinstance(item, dict))
                if not data.get("has_more"):
                    return collected
                cursor = data.get("cursor")
                if not cursor or cursor in seen:
                    raise ValueError("Outlook folder pagination cursor is missing or repeated.")
                seen.add(cursor)
            raise ValueError("Outlook folder list exceeded the safety page limit.")

        self._email_run("Loading mail folders...", operation, self._email_folders_loaded)

    def _email_folders_loaded(self, folders):
        self._email_render_folders(folders)
        self._email_load_messages(reset=True)

    def _email_refresh(self):
        if self._email_busy:
            return
        self._email_load_folders()

    def _email_select_folder(self, folder, label):
        if self._email_busy:
            self._email_pending_folder = (folder, label)
            return
        self._email_pending_folder = None
        self._email_current_folder = folder
        self._email_current_label = label
        self._email_search_query = ""
        self._email_search.delete(0, tk.END)
        self._email_render_folders(getattr(self, "_email_folders", []))
        self._email_load_messages(reset=True)

    def _email_load_messages(self, reset=False, cursor=None):
        if self._email_busy:
            return
        if reset:
            self._email_next_cursor = None
            self._email_seen_cursors = set()
            cursor = None

        query = self._email_search_query
        folder = self._email_current_folder
        is_drafts = folder.casefold() in {"draft", "drafts"}
        if is_drafts and not query:
            tool_name = "outlook_list_drafts"
            arguments = {"count": 50, "concise": True}
        elif query:
            tool_name = "outlook_search_mail"
            arguments = {
                "query": query,
                "count": 50,
                "concise": True,
            }
        else:
            tool_name = "outlook_list_inbox"
            arguments = {"folder": folder, "count": 50, "concise": True}
        if cursor:
            arguments["cursor"] = cursor

        def operation():
            return self._email_call_tool(tool_name, arguments, self._email_current_label)

        self._email_run(
            f"Loading {self._email_current_label}...",
            operation,
            lambda data: self._email_messages_loaded(data, append=bool(cursor)),
        )

    def _email_search_mail(self):
        query = self._email_search.get().strip()
        if not query or query == "Search all mail...":
            self._email_set_status("Enter a search term.", error=True)
            return
        self._email_search_query = query
        self._email_load_messages(reset=True)

    def _email_load_more(self):
        if self._email_next_cursor and not self._email_busy:
            self._email_load_messages(cursor=self._email_next_cursor)

    def _email_messages_loaded(self, data, append=False):
        messages = data.get("messages")
        if not isinstance(messages, list):
            raise ValueError("Outlook message response has no messages list.")
        if not append:
            for row in self._email_tree.get_children():
                self._email_tree.delete(row)
            self._email_message_rows.clear()

        start = len(self._email_message_rows)
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or not message.get("id"):
                continue
            row_id = str(start + index)
            self._email_message_rows[row_id] = message
            sender = (
                message.get("from_name")
                or message.get("from_email")
                or message.get("sender_name")
                or message.get("sender_email")
                or "Unknown sender"
            )
            subject = str(message.get("subject") or "(No subject)")
            received = (
                message.get("received")
                or message.get("received_at")
                or message.get("sent")
                or message.get("sent_at")
                or ""
            )
            date_text = str(received).replace("T", " ")[:10]
            tags = ("unread",) if message.get("is_read") is False else ()
            self._email_tree.insert(
                "", "end", iid=row_id,
                values=(sender, subject, date_text), tags=tags,
            )

        next_cursor = data.get("cursor") if data.get("has_more") else None
        if data.get("has_more") and not next_cursor:
            raise ValueError("Outlook indicated more messages without a continuation cursor.")
        if next_cursor and next_cursor in self._email_seen_cursors:
            raise ValueError("Outlook repeated a message pagination cursor.")
        if next_cursor:
            self._email_seen_cursors.add(next_cursor)
        self._email_next_cursor = next_cursor
        self._email_more_button.configure(
            state="normal" if self._email_next_cursor else "disabled"
        )
        count = len(self._email_tree.get_children())
        self._email_list_title.configure(
            text=(self._email_search_query or self._email_current_label).upper()
        )
        if self._email_current_folder.casefold() in {"draft", "drafts"}:
            date_heading = "SAVED"
        elif self._email_current_folder.casefold() == "sentitems":
            date_heading = "SENT"
        else:
            date_heading = "RECEIVED"
        self._email_tree.heading("date", text=date_heading)
        list_label = (
            "Search results" if self._email_search_query
            else self._email_current_label
        )
        self._email_set_status(
            f"{list_label}: {count} messages"
            + (" - more available" if self._email_next_cursor else "")
        )
        self._email_render_message(None)
        target_id = getattr(self, "_email_open_after_list_id", None)
        if target_id:
            self._email_open_after_list_id = None
            for row_id, message in self._email_message_rows.items():
                if message.get("id") == target_id:
                    self._email_tree.selection_set(row_id)
                    self._email_tree.focus(row_id)
                    self._email_tree.see(row_id)
                    self._email_select_message()
                    return
            self._email_set_status(
                "Draft was saved, but it was not present in the refreshed Drafts list.",
                error=True,
            )

    def _email_select_message(self, _event=None):
        selected = self._email_tree.selection()
        if not selected:
            return
        message = self._email_message_rows.get(selected[0])
        if not message or not message.get("id"):
            self._email_set_status("Selected Outlook message has no ID.", error=True)
            return

        def operation():
            return self._email_call_tool(
                "outlook_read_message",
                {
                    "message_id": message["id"],
                    "format": "full",
                    "concise": False,
                },
                "Read message",
            )

        self._email_run("Reading message...", operation, self._email_render_message)

    def _email_render_message(self, message):
        self._email_current_message = message
        widgets = [
            getattr(self, "_email_reader_subject", None),
            getattr(self, "_email_reader_meta", None),
            getattr(self, "_email_reader_body", None),
        ]
        widgets.extend(getattr(self, "_email_action_buttons", {}).values())
        try:
            reader_ready = all(
                widget is not None and bool(widget.winfo_exists())
                for widget in widgets
            )
        except (AttributeError, tk.TclError):
            reader_ready = False
        if not reader_ready:
            self._email_build_reader()
            widgets = [
                getattr(self, "_email_reader_subject", None),
                getattr(self, "_email_reader_meta", None),
                getattr(self, "_email_reader_body", None),
            ]
            widgets.extend(getattr(self, "_email_action_buttons", {}).values())
            try:
                reader_ready = all(
                    widget is not None and bool(widget.winfo_exists())
                    for widget in widgets
                )
            except (AttributeError, tk.TclError):
                reader_ready = False
        if not reader_ready:
            self._email_set_status(
                "The message reader could not be initialized. Close and reopen Outlook Mail.",
                error=True,
            )
            return

        if message is None:
            self._email_reader_subject.configure(text="Select a message")
            self._email_reader_meta.configure(text="")
            self._email_reader_body.configure(state="normal")
            self._email_reader_body.delete("1.0", tk.END)
            self._email_reader_body.insert("1.0", "Your message will appear here.")
            self._email_reader_body.configure(state="disabled")
            for button in self._email_action_buttons.values():
                button.configure(state="disabled")
            return

        if not isinstance(message, dict):
            raise ValueError("Outlook returned an invalid message.")
        self._email_reader_subject.configure(
            text=str(message.get("subject") or "(No subject)")
        )
        sender = (
            message.get("from_name")
            or message.get("from_email")
            or message.get("sender_name")
            or message.get("sender_email")
            or "Unknown sender"
        )
        received = (
            message.get("received")
            or message.get("received_at")
            or message.get("sent")
            or message.get("sent_at")
            or "Unknown date"
        )
        if message.get("is_draft") is True:
            message_kind = "Draft"
        elif self._email_current_folder.casefold() == "sentitems":
            message_kind = "Sent"
        else:
            message_kind = "Email"
        if message_kind == "Draft":
            date_label = "Saved"
        elif message_kind == "Sent":
            date_label = "Sent"
        else:
            date_label = "Received"
        meta = (
            f"Type: {message_kind}\n"
            f"From: {sender}\n"
            f"To: {format_recipients(message.get('to'))}\n"
            f"CC: {format_recipients(message.get('cc'))}\n"
            f"BCC: {format_recipients(message.get('bcc'))}\n"
            f"Folder: {self._email_current_label}\n"
            f"{date_label}: {received}"
        )
        if message.get("has_attachments"):
            meta += "\nAttachments: Yes"
        self._email_reader_meta.configure(text=meta)
        body = plain_text_body(message.get("body"), message.get("body_type"))
        self._email_reader_body.configure(state="normal")
        self._email_reader_body.delete("1.0", tk.END)
        self._email_reader_body.insert("1.0", body or "(Empty message body)")
        self._email_reader_body.configure(state="disabled")

        review_error = None
        if message.get("is_draft") is True:
            draft_id = message.get("id")
            callback = getattr(self, "on_outlook_draft_reviewed", None)
            if draft_id and callable(callback):
                try:
                    if callback(draft_id, message):
                        self._email_reviewed_drafts.add(draft_id)
                    else:
                        review_error = "Draft details are incomplete; GHOST cannot approve sending it."
                except Exception as exc:
                    review_error = f"Draft review could not be registered with GHOST: {exc}"
        self._email_set_action_states(message)
        if review_error:
            self._email_set_status(review_error, error=True)
        else:
            self._email_set_status("Message loaded.")

    def _email_set_action_states(self, message):
        is_draft = message.get("is_draft") is True
        message_id = message.get("id")
        normal_state = "normal" if message_id else "disabled"
        for name in ("reply", "reply_all", "forward"):
            self._email_action_buttons[name].configure(
                state="disabled" if is_draft else normal_state
            )
        self._email_action_buttons["edit"].configure(
            state="normal" if is_draft else "disabled"
        )
        can_send = (
            is_draft
            and message_id in self._email_reviewed_drafts
            and message_id not in self._email_send_requested
        )
        self._email_action_buttons["send"].configure(
            state="normal" if can_send else "disabled"
        )
        self._email_action_buttons["archive"].configure(
            state="disabled" if is_draft else normal_state
        )
        self._email_action_buttons["delete"].configure(state=normal_state)

    def _email_reply(self):
        message = self._email_current_message
        if message:
            self._email_open_compose("reply", message)

    def _email_reply_all(self):
        message = self._email_current_message
        if message:
            self._email_open_compose("reply_all", message)

    def _email_forward(self):
        message = self._email_current_message
        if message:
            self._email_open_compose("forward", message)

    def _email_new_message(self):
        self._email_open_compose("new", None)

    def _email_edit_draft(self):
        message = self._email_current_message
        if message and message.get("is_draft") is True:
            self._email_open_compose("edit", message)

    def _email_open_compose(self, mode, message):
        col = self.col
        win = tk.Toplevel(self._email_client_window)
        title = {
            "new": "New email",
            "reply": "Reply",
            "reply_all": "Reply all",
            "forward": "Forward",
            "edit": "Edit draft",
        }.get(mode, "New email")
        win.title(f"GHOST | {title}")
        win.geometry("760x640")
        win.minsize(620, 480)
        win.configure(bg=col["bg"])
        win.transient(self._email_client_window)

        header = tk.Label(
            win, text=title.upper(), bg=col["hdr"], fg=col["pri"],
            font=("Consolas", 12, "bold"), anchor="w", padx=16, pady=12,
        )
        header.pack(fill="x", padx=8, pady=(8, 12))

        fields = {}
        form = tk.Frame(win, bg=col["bg"])
        form.pack(fill="x", padx=16)
        initial = {}
        if mode == "reply" and message:
            initial["to"] = (
                message.get("from_email")
                or message.get("sender_email")
                or ""
            )
            original_subject = str(message.get("subject") or "")
            initial["subject"] = (
                original_subject if original_subject.casefold().startswith("re:")
                else f"Re: {original_subject}"
            )
        elif mode == "reply_all" and message:
            original_subject = str(message.get("subject") or "")
            initial["subject"] = (
                original_subject if original_subject.casefold().startswith("re:")
                else f"Re: {original_subject}"
            )
        elif mode == "forward" and message:
            original_subject = str(message.get("subject") or "")
            initial["subject"] = (
                original_subject if original_subject.casefold().startswith("fw:")
                else f"Fwd: {original_subject}"
            )
        elif mode == "edit" and message:
            initial["to"] = format_recipients(message.get("to"))
            initial["cc"] = format_recipients(message.get("cc"))
            initial["bcc"] = format_recipients(message.get("bcc"))
            initial["subject"] = str(message.get("subject") or "")

        for label, key in (("To", "to"), ("CC", "cc"), ("BCC", "bcc"),
                           ("Subject", "subject")):
            row = tk.Frame(form, bg=col["bg"])
            row.pack(fill="x", pady=4)
            tk.Label(
                row, text=label, width=9, anchor="w", bg=col["bg"],
                fg=col["mid"], font=("Consolas", 9, "bold"),
            ).pack(side="left")
            entry = tk.Entry(
                row, bg=col["input"], fg=col["text"],
                insertbackground=col["text"], relief="flat",
                highlightthickness=1, highlightbackground=col["inp_border"],
                font=("Segoe UI", 10),
            )
            entry.pack(side="left", fill="x", expand=True, ipady=6)
            if initial.get(key) and initial[key] != "None":
                entry.insert(0, initial[key])
            fields[key] = entry

        body_frame = tk.Frame(win, bg=col["bg"])
        body_frame.pack(fill="both", expand=True, padx=16, pady=(10, 8))
        tk.Label(
            body_frame, text="MESSAGE", bg=col["bg"], fg=col["mid"],
            font=("Consolas", 9, "bold"),
        ).pack(anchor="w", pady=(0, 5))
        body = tk.Text(
            body_frame, wrap="word", bg=col["input"], fg=col["text"],
            insertbackground=col["text"], relief="flat", padx=10, pady=10,
            font=("Segoe UI", 10),
        )
        body.pack(fill="both", expand=True)
        if mode == "edit" and message:
            body.insert("1.0", plain_text_body(message.get("body"), message.get("body_type")))

        status_text = (
            "Send via GHOST saves a draft and asks for your approval."
            if mode != "edit"
            else ""
        )
        status = tk.Label(
            win, text=status_text, bg=col["bg"], fg=col["mid"],
            font=("Segoe UI", 9), anchor="w",
        )
        status.pack(fill="x", padx=16, pady=(0, 4))
        buttons = tk.Frame(win, bg=col["bg"])
        buttons.pack(fill="x", padx=16, pady=(0, 12))

        def save(send_after_save=False):
            values = {key: entry.get().strip() for key, entry in fields.items()}
            text = body.get("1.0", "end-1c")
            to = parse_recipients(values["to"])
            cc = parse_recipients(values["cc"])
            bcc = parse_recipients(values["bcc"])

            if mode in {"new", "forward"} and not to:
                status.configure(text="Enter at least one recipient.", fg=col["red"])
                return
            if not values["subject"]:
                status.configure(text="Subject is required.", fg=col["red"])
                return

            if mode == "edit":
                if message and message.get("bcc"):
                    status.configure(
                        text="This draft has BCC recipients; GHOST will not edit it "
                             "because the current Outlook update tool cannot preserve BCC.",
                        fg=col["red"],
                    )
                    return
                command = self._email_build_update_command(
                    message.get("id"), to, cc, values["subject"], text
                )
                if not self._email_submit_ghost_command(
                    command, "Draft update requested. Confirm it in GHOST before changes execute."
                ):
                    status.configure(text="GHOST is not ready to process this request.", fg=col["red"])
                else:
                    win.destroy()
                return

            arguments = {"body": text, "is_html": False}
            if mode == "new":
                arguments.update({
                    "to": to, "subject": values["subject"],
                    "cc": cc, "bcc": bcc,
                })
            elif mode in {"reply", "reply_all"}:
                arguments["reply_to_message_id"] = message["id"]
                arguments["reply_all"] = mode == "reply_all"
                arguments["subject"] = values["subject"]
                if to:
                    arguments["to"] = to
                if cc:
                    arguments["cc"] = cc
            elif mode == "forward":
                arguments["forward_message_id"] = message["id"]
                arguments["to"] = to
                arguments["subject"] = values["subject"]
                if cc:
                    arguments["cc"] = cc
                if bcc:
                    arguments["bcc"] = bcc

            for button in buttons.winfo_children():
                button.configure(state="disabled")
            status.configure(text="Saving draft to Outlook...", fg=col["mid"])

            def operation():
                created = self._email_call_tool(
                    "outlook_create_draft", arguments, "Create draft"
                )
                draft_id = created.get("draft_id") or created.get("id")
                if not isinstance(draft_id, str) or not draft_id.strip():
                    raise ValueError("Outlook did not return a draft ID.")
                snapshot = self._email_call_tool(
                    "outlook_read_message",
                    {
                        "message_id": draft_id,
                        "format": "full",
                        "concise": False,
                    },
                    "Verify saved draft",
                )
                if not isinstance(snapshot, dict):
                    raise ValueError("Outlook returned an invalid saved draft.")
                if snapshot.get("is_draft") is not True:
                    raise ValueError("Outlook did not confirm the saved item is a draft.")
                snapshot_id = snapshot.get("id")
                if snapshot_id and snapshot_id != draft_id:
                    raise ValueError("Outlook returned a different draft ID.")
                snapshot.setdefault("id", draft_id)
                return snapshot

            self._email_run(
                "Saving draft...",
                operation,
                lambda snapshot: self._email_compose_saved(
                    win, snapshot, send_after_save
                ),
                on_error=lambda exc: self._email_compose_failed(status, buttons, exc),
            )

        if mode != "edit":
            self._email_button(
                buttons, "Send via GHOST",
                lambda: save(send_after_save=True), accent=col["green"],
            ).pack(side="left")
        self._email_button(
            buttons, "Request Update" if mode == "edit" else "Save Draft",
            save, accent=col["pri"]
        ).pack(side="right", padx=(6, 0))
        self._email_button(
            buttons, "Cancel", win.destroy
        ).pack(side="right")
        fields["to"].focus_set()
        win.grab_set()

    def _email_compose_saved(self, compose_window, snapshot, send_after_save=False):
        try:
            compose_window.destroy()
        except tk.TclError:
            pass
        self._email_current_folder = "drafts"
        self._email_current_label = "Drafts"
        self._email_search_query = ""
        if send_after_save:
            self._email_render_message(snapshot)
            self._email_request_send()
        self._email_open_after_list_id = snapshot.get("id")
        self._email_render_folders(getattr(self, "_email_folders", []))
        self._email_load_messages(reset=True)

    def _email_compose_failed(self, status, buttons, error):
        try:
            status.configure(
                text=f"Could not verify the saved draft: {error}. Refresh Drafts before retrying.",
                fg=self.col["red"],
            )
            for button in buttons.winfo_children():
                button.configure(
                    state="normal" if button.cget("text") == "Cancel" else "disabled"
                )
        except tk.TclError:
            pass

    @staticmethod
    def _email_build_update_command(draft_id, to, cc, subject, body):
        if not isinstance(draft_id, str) or not draft_id.strip():
            raise ValueError("A valid Outlook draft ID is required.")
        return (
            "Update this existing Personal Outlook draft only; do not send it. "
            f"Draft ID: {draft_id.strip()}. Set To to {to!r}, CC to {cc!r}, "
            f"subject to {subject!r}, and body to {body!r}. "
            "Read it back after updating. Obtain the required explicit approval first."
        )

    def _email_request_send(self):
        message = self._email_current_message
        if not isinstance(message, dict) or message.get("is_draft") is not True:
            self._email_set_status("Select a saved draft before requesting send.", error=True)
            return
        draft_id = message.get("id")
        if draft_id not in self._email_reviewed_drafts:
            self._email_set_status(
                "This draft has not been fully reviewed in GHOST yet.", error=True
            )
            return
        if draft_id in self._email_send_requested:
            self._email_set_status(
                "A send request for this draft was already submitted. Check GHOST before retrying.",
                error=True,
            )
            return
        try:
            command = build_send_request(draft_id)
        except ValueError as exc:
            self._email_set_status(str(exc), error=True)
            return
        if self._email_submit_ghost_command(
            command,
            "Send request submitted. Review the draft and approve the send in GHOST.",
        ):
            self._email_send_requested.add(draft_id)
            self._email_action_buttons["send"].configure(state="disabled")

    def _email_archive(self):
        message = self._email_current_message
        if message and message.get("id"):
            self._email_submit_ghost_command(
                f"Archive this Personal Outlook message once. Message ID: {message['id']}. "
                "Ask for approval before moving it.",
                "Archive request submitted; approve it in GHOST.",
            )

    def _email_delete(self):
        message = self._email_current_message
        if message and message.get("id"):
            kind = "draft" if message.get("is_draft") else "message"
            self._email_submit_ghost_command(
                f"Delete this Personal Outlook {kind} once. ID: {message['id']}. "
                "Explain the exact item and ask for approval before deleting.",
                "Delete request submitted; approve it in GHOST.",
            )

    def _email_submit_ghost_command(self, command, status):
        callback = getattr(self, "on_text_command", None)
        if not callable(callback):
            self._email_set_status("GHOST is not ready to process this action.", error=True)
            return False
        result = callback(command)
        if result is False:
            self._email_set_status("GHOST is not ready to process this action.", error=True)
            return False
        self._email_set_status(status)
        return True

    def _email_run(self, status, operation, on_success, on_error=None):
        if self._email_busy:
            return
        self._email_busy = True
        self._email_request_id += 1
        request_id = self._email_request_id
        self._email_set_status(status)

        def run():
            try:
                result = operation()
            except Exception as exc:
                self._safe_ui(
                    self._email_finished, request_id, exc, None, None, on_error
                )
            else:
                self._safe_ui(
                    self._email_finished, request_id, None, result, on_success, on_error
                )

        threading.Thread(
            target=run, daemon=True, name="GhostOutlookMailRequest"
        ).start()

    def _email_finished(self, request_id, error, result, on_success, on_error):
        if request_id != self._email_request_id:
            return
        self._email_busy = False
        if not self._email_window_exists():
            return
        if error is not None:
            self._email_set_status(f"Outlook error: {error}", error=True)
            if on_error is not None:
                on_error(error)
            self._email_apply_pending_folder()
            return
        try:
            on_success(result)
        except Exception as exc:
            self._email_set_status(f"Outlook response could not be displayed: {exc}", error=True)
        self._email_apply_pending_folder()

    def _email_apply_pending_folder(self):
        if self._email_busy or not self._email_window_exists():
            return
        pending = getattr(self, "_email_pending_folder", None)
        if pending is None:
            return
        self._email_pending_folder = None
        self._email_select_folder(*pending)

    @staticmethod
    def _email_call_tool(tool_name, arguments, label):
        from integrations.personal_outlook_mcp import (
            _preview_decode,
            personal_outlook_action,
        )

        result = personal_outlook_action({
            "action": "call",
            "tool_name": tool_name,
            "arguments": arguments,
        })
        if isinstance(result, str) and result.lstrip().startswith("Personal Outlook error:"):
            raise RuntimeError(result.strip())
        return _preview_decode(result, label)

    def _email_set_status(self, text, error=False):
        if not self._email_window_exists():
            return
        try:
            self._email_status.configure(
                text=str(text),
                fg=self.col["red"] if error else self.col["mid"],
            )
            if error:
                self.write_log(f"ERR: Outlook mail interface: {text}")
        except tk.TclError:
            pass
