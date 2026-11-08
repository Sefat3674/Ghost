"""Tkinter Akkhor panel. Network work runs on worker threads; Tk updates use after()."""
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox


class AkkhorPanel:
    def __init__(self, parent, service, on_command=None):
        self.parent = parent
        self.service = service
        self.on_command = on_command
        self.win = tk.Toplevel(parent)
        self.win.title("GHOST  |  Akkhor School Integration")
        self.win.geometry("900x680")
        self.win.minsize(720, 540)
        self.win.configure(bg="#071321")
        self.win.transient(parent)
        self._build()
        self._refresh_status()
        self.win.protocol("WM_DELETE_WINDOW", self.win.withdraw)

    def lift(self):
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
        except tk.TclError:
            pass

    def _build(self):
        bg, panel, accent, text, muted = "#071321", "#0D2030", "#38C9D6", "#E3F5F7", "#8AAAB7"
        header = tk.Frame(self.win, bg=panel, padx=22, pady=17)
        header.pack(fill="x")
        tk.Label(header, text="AKKHOR  /  SCHOOL MANAGEMENT", bg=panel, fg=accent,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(header, text="Secure API connection from GHOST AI", bg=panel, fg=muted,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self.win, bg=bg, padx=18, pady=16)
        body.pack(fill="both", expand=True)
        connection = tk.LabelFrame(body, text=" API CONNECTION ", bg=bg, fg=accent,
                                   font=("Segoe UI", 9, "bold"), padx=12, pady=10)
        connection.pack(fill="x")
        self.status_var = tk.StringVar(value="● DISCONNECTED")
        tk.Label(connection, textvariable=self.status_var, bg=bg, fg="#FF8B91",
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 12))
        tk.Label(connection, text="API URL", bg=bg, fg=muted).grid(row=1, column=0, sticky="w", pady=(10, 4))
        self.url_var = tk.StringVar(value=self.service.config["base_url"])
        self.url_entry = tk.Entry(connection, textvariable=self.url_var, bg=panel, fg=text,
                                  insertbackground=text, relief="flat", font=("Consolas", 10))
        self.url_entry.grid(row=2, column=0, columnspan=3, sticky="ew", ipady=7)
        tk.Label(connection, text="EMAIL", bg=bg, fg=muted).grid(row=3, column=0, sticky="w", pady=(10, 4))
        self.email_entry = tk.Entry(connection, bg=panel, fg=text, insertbackground=text,
                                    relief="flat", font=("Segoe UI", 10))
        self.email_entry.grid(row=4, column=0, sticky="ew", ipady=7, padx=(0, 8))
        tk.Label(connection, text="PASSWORD", bg=bg, fg=muted).grid(row=3, column=1, sticky="w", pady=(10, 4))
        self.password_entry = tk.Entry(connection, show="•", bg=panel, fg=text, insertbackground=text,
                                       relief="flat", font=("Segoe UI", 10))
        self.password_entry.grid(row=4, column=1, sticky="ew", ipady=7, padx=(0, 8))
        self.login_btn = tk.Button(connection, text="CONNECT", command=self._login,
                                   bg=accent, fg="#041017", activebackground="#72E2E9",
                                   relief="flat", font=("Segoe UI", 9, "bold"), padx=18, cursor="hand2")
        self.login_btn.grid(row=4, column=2, sticky="ew", ipady=5)
        self.logout_btn = tk.Button(connection, text="DISCONNECT", command=self._logout,
                                    bg=panel, fg=text, activebackground="#28465A",
                                    relief="flat", font=("Segoe UI", 9, "bold"), cursor="hand2")
        self.logout_btn.grid(row=5, column=2, sticky="ew", pady=(8, 0), ipady=4)
        connection.columnconfigure(0, weight=1)
        connection.columnconfigure(1, weight=1)

        modules = tk.LabelFrame(body, text=" AKKHOR MODULES ", bg=bg, fg=accent,
                                font=("Segoe UI", 9, "bold"), padx=12, pady=10)
        modules.pack(fill="x", pady=(14, 12))
        self._resource_buttons = []
        for label, key in (("ASSIGNMENTS", "assignments"), ("SUBMISSIONS", "submissions"), ("STUDENTS / USERS", "students")):
            button = tk.Button(modules, text=label, command=lambda k=key: self._load_resource(k),
                               bg=panel, fg=text, activebackground="#1D4658", activeforeground=accent,
                               relief="flat", font=("Segoe UI", 9, "bold"), padx=12, pady=10,
                               cursor="hand2", state="disabled")
            button.pack(side="left", fill="x", expand=True, padx=4)
            self._resource_buttons.append(button)

        output_frame = tk.LabelFrame(body, text=" API RESPONSE / ACTIVITY ", bg=bg, fg=accent,
                                     font=("Segoe UI", 9, "bold"), padx=8, pady=8)
        output_frame.pack(fill="both", expand=True)
        self.output = tk.Text(output_frame, bg="#06101B", fg=text, insertbackground=text,
                              relief="flat", wrap="word", font=("Consolas", 9), padx=10, pady=8)
        scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output.yview)
        self.output.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.output.pack(side="left", fill="both", expand=True)
        self._write("GHOST Akkhor integration ready. Sign in to load protected API resources.\n")

        footer = tk.Frame(body, bg=bg)
        footer.pack(fill="x", pady=(10, 0))
        tk.Button(footer, text="ASK GHOST ABOUT AKKHOR", command=self._ask_ghost,
                  bg="#123344", fg=accent, activebackground="#1D4658", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=14, pady=8, cursor="hand2").pack(side="left")
        tk.Label(footer, text="Credentials and JWT are not written to disk.", bg=bg, fg=muted,
                 font=("Segoe UI", 8)).pack(side="right")

    def _write(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", str(text) + ("" if str(text).endswith("\n") else "\n"))
        self.output.see("end")
        self.output.configure(state="disabled")

    def _set_status(self, connected, label=None):
        self.status_var.set(("● CONNECTED" if connected else "● DISCONNECTED") + (f"  {label}" if label else ""))
        for button in self._resource_buttons:
            button.configure(state="normal" if connected else "disabled")
        self.login_btn.configure(state="disabled" if connected else "normal")

    def _refresh_status(self):
        status = self.service.status()
        user = status.get("user") or {}
        self._set_status(status["connected"], user.get("email") if status["connected"] else None)

    def _login(self):
        email, password, base_url = self.email_entry.get().strip(), self.password_entry.get(), self.url_var.get().strip()
        if not email or not password:
            messagebox.showwarning("Akkhor login", "Enter your Akkhor email and password.", parent=self.win)
            return
        if not base_url.startswith(("https://", "http://")):
            messagebox.showwarning("API URL", "Enter a valid http:// or https:// API URL.", parent=self.win)
            return
        self.service.config["base_url"] = base_url.rstrip("/")
        self.service.auth.base_url = self.service.config["base_url"]
        self.service.client.base_url = self.service.config["base_url"]
        self.login_btn.configure(state="disabled", text="CONNECTING…")
        self._write(f"Signing in to {self.service.config['base_url']} as {email}…")
        def worker():
            result = self.service.login(email, password)
            self.win.after(0, lambda: self._login_done(result))
        threading.Thread(target=worker, daemon=True).start()

    def _login_done(self, result):
        self.login_btn.configure(text="CONNECT")
        self.password_entry.delete(0, "end")
        if result.get("success"):
            user = result.get("user") or {}
            self._set_status(True, user.get("email"))
            self._write("LOGIN SUCCESS")
            self._write(json.dumps({"user": user, "expiresAt": result.get("expiresAt")}, ensure_ascii=False, indent=2))
            if user.get("role") is None:
                self._write("NOTE: Akkhor returned role=null. Server-side authorization remains authoritative; GHOST will not infer privileges.")
        else:
            self._set_status(False)
            self._write("LOGIN FAILED: " + str(result.get("message", "Unknown error")))

    def _logout(self):
        self.service.logout()
        self._set_status(False)
        self._write("Akkhor session cleared from memory.")

    def _load_resource(self, resource):
        self._write(f"\nGET {self.service.config['endpoints'].get(resource, resource)} …")
        def worker():
            result = self.service.get_resource(resource)
            pretty = json.dumps(result, ensure_ascii=False, indent=2, default=str)
            self.win.after(0, lambda: self._write(pretty))
        threading.Thread(target=worker, daemon=True).start()

    def _ask_ghost(self):
        if not self.on_command:
            self._write("GHOST command bridge is not available yet.")
            return
        try:
            self.on_command("Show my Akkhor school dashboard and summarize the available assignments and submissions.")
            self._write("Sent Akkhor request to GHOST voice/text assistant.")
        except Exception as exc:
            self._write(f"Could not send command to GHOST: {exc}")
