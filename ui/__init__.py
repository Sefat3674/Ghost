import os, json, time, math, random, threading
import tkinter as tk
from collections import deque
from importlib import import_module

try:
    Image = import_module("PIL.Image")
    ImageTk = import_module("PIL.ImageTk")
    ImageDraw = import_module("PIL.ImageDraw")
    ImageFont = import_module("PIL.ImageFont")
    ImageOps = import_module("PIL.ImageOps")
except ImportError:
    # Pillow is optional; the UI can still run without image-based features.
    Image = ImageTk = ImageDraw = ImageFont = ImageOps = None

import sys
from pathlib import Path
from vision.arcade import VisionArcade
from .theme import (
    DEFAULT_BRAND,
    THEMES,
    load_brand,
    load_theme_name,
    save_theme_name,
)
from .scaling import (
    HiDPICanvas as _HiDPICanvas,
    pick_scale as _pick_scale,
    px,
    set_ui_scale,
)
from .smart_manufacturing import SmartManufacturingDashboardMixin


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR   = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
API_FILE   = CONFIG_DIR / "api_keys.json"
THEME_FILE = CONFIG_DIR / "ui_theme.json"

SYSTEM_NAME = "GHOST"
MODEL_BADGE = "GHOST"

# ── High-DPI awareness: crisp text on 125% / 150% laptop scaling ───────────
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _load_theme_name() -> str:
    return load_theme_name(THEME_FILE, THEMES)


def _save_theme_name(name: str) -> None:
    save_theme_name(name, CONFIG_DIR, THEME_FILE)


# ── Resolution independence ─────────────────────────────────────────────────
# The whole UI is laid out and drawn in LOGICAL units. _S converts logical ->
# real pixels (1.0 on 1080p, 2.0 on a 4K panel). Fonts follow through Tk's own
# "scaling" so text, widgets and canvas art stay in proportion at any size.
_S = 1.0


# ── Branding (config/brand.json overrides any of these) ─────────────────────
BRAND_FILE = CONFIG_DIR / "brand.json"
def _load_brand() -> dict:
    return load_brand(BRAND_FILE, DEFAULT_BRAND)


class _DeckButton:
    """Flat robotic button: accent strip, icon, label, hover / active glow."""

    def __init__(self, ui, parent, text, icon, accent, on_click, mode=None):
        col = ui.col
        self.ui, self.mode, self.accent = ui, mode, accent
        self.hover = False
        self.active = False
        self.border = tk.Frame(parent, bg=col["inp_border"], cursor="hand2")
        self.border.pack(fill="x", padx=px(10), pady=px(3))
        self.body = tk.Frame(self.border, bg=col["input"])
        self.body.pack(fill="x", padx=px(1), pady=px(1))
        self.strip = tk.Frame(self.body, bg=accent, width=px(3))
        self.strip.pack(side="left", fill="y")
        self.icon = tk.Label(self.body, text=icon, bg=col["input"], fg=accent,
                             font=("Segoe UI Symbol", 10), width=2)
        self.icon.pack(side="left", padx=px((8, 2)), pady=px(6))
        self.label = tk.Label(self.body, text=text, anchor="w", bg=col["input"],
                              fg=col["text"], font=("Segoe UI", 8, "bold"))
        self.label.pack(side="left", fill="x", expand=True, pady=px(6))
        self.arrow = tk.Label(self.body, text="\u203a", bg=col["input"], fg=col["dim"],
                              font=("Segoe UI", 11, "bold"))
        self.arrow.pack(side="right", padx=px((0, 10)))
        for w in (self.border, self.body, self.strip, self.icon, self.label, self.arrow):
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            w.bind("<Button-1>", lambda e: on_click())
        self.render()

    def _enter(self, _e=None):
        self.hover = True
        self.render()

    def _leave(self, _e=None):
        self.hover = False
        self.render()

    def set_active(self, on):
        if on != self.active:
            self.active = on
            self.render()

    def render(self):
        ui, col = self.ui, self.ui.col
        hot = self.hover or self.active
        bg = ui._mixc(col["input"], self.accent, 0.16) if hot else col["input"]
        try:
            self.body.configure(bg=bg)
            for w in (self.icon, self.label, self.arrow):
                w.configure(bg=bg)
            self.border.configure(bg=self.accent if hot else col["inp_border"])
            self.strip.configure(bg=self.accent if hot else ui._mixc(self.accent, col["input"], 0.6))
            self.label.configure(fg=self.accent if hot else col["text"])
            self.icon.configure(fg=self.accent)
            self.arrow.configure(text="\u25cf" if self.active else "\u203a",
                                 fg=self.accent if hot else col["dim"])
        except tk.TclError:
            pass


class GHOSTUI(SmartManufacturingDashboardMixin):
    def __init__(self, face_path, size=None):
        global _S
        self.root = tk.Tk()
        self.brand = _load_brand()
        self.root.title(f"{self.brand['product']}  |  {self.brand['company'].title()}  \u2014  {self.brand['division']}")
        self.root.resizable(True, True)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        try:
            dpi = self.root.winfo_fpixels("1i")
        except Exception:
            dpi = 96.0
        S = _pick_scale(sw, sh, dpi)
        self.S = S
        _S = S
        set_ui_scale(S)
        # Fonts are in points, so Tk "scaling" makes them follow the UI scale.
        self.root.tk.call("tk", "scaling", 96.0 * S / 72.0)

        # W / H are LOGICAL units (real pixels / S); everything lays out in them.
        W  = int(min(sw / S - 40, 1500))
        H  = int(min(sh / S - 80, 980))
        self.root.geometry(f"{int(W * S)}x{int(H * S)}+{(sw - int(W * S)) // 2}+{(sh - int(H * S)) // 2}")
        self.root.configure(bg="#000000")
        self.root.minsize(int(760 * S), int(600 * S))
        self._fs = False

        self.W = W
        self.H = H

        self.FACE_SZ = min(int(H * 0.40), 360)
        self.FCX     = W // 2
        self.FCY     = int(H * 0.11) + self.FACE_SZ // 2

        # ── State ────────────────────────────────────────────────────────────
        self.speaking     = False
        self.muted        = False          # Mute flag — main.py reads it
        self.silent_mode  = False          # Text-only mode: keep transcript, suppress TTS
        self.scale        = 1.0
        self.target_scale = 1.0
        self.halo_a       = 60.0
        self.target_halo  = 60.0
        self.last_t       = time.time()
        self.tick         = 0
        self.scan_angle   = 0.0
        self.scan2_angle  = 180.0
        self.rings_spin   = [0.0, 120.0, 240.0]
        self.pulse_r      = [0.0, self.FACE_SZ * 0.26, self.FACE_SZ * 0.52]
        self.status_text  = "INITIALISING"
        self.status_blink = True

        self._state = "INITIALISING"

        self.typing_queue = deque()
        self.is_typing    = False
        self._ui_deferred = deque()
        self._main_thread = threading.current_thread()

        # Persona / connection info (updated by main.py)
        self.persona_mode  = "normal"
        self.persona_mood  = "calm"
        self.persona_voice = "Aoede"
        self.connected     = False
        self.connecting    = False
        self.last_event    = ""
        self._batt_cache   = None
        self._batt_ts      = 0.0

        self.on_text_command = None
        self.on_sm_filter_change = None
        self.akkhor_service = None
        self._akkhor_panel = None
        self._sm_dashboard_window = None
        self.vision_mode = "STANDBY"
        self.vision_signal = "Awaiting camera input"
        self.vision_preview_open = False
        self._preview_window = None
        self._preview_label = None
        self._preview_image = None
        self.arcade_open = False
        self._arcade_window = None
        self._arcade_label = None
        self._arcade_image = None
        self._arcade = VisionArcade()
        self._deck_buttons = []
        self._dock_rects = []
        self._dock_hover = None
        self._act = 0.3
        self._stats = None
        self._stats_ts = 0.0
        self._disp = {"cpu": 0.0, "mem": 0.0}
        self._tele = [0.3, 0.5, 0.4, 0.2]
        self._tele_t = [0.3, 0.5, 0.4, 0.2]

        self._theme = _load_theme_name()
        self.col    = dict(THEMES[self._theme])
        self.root.configure(bg=self.col["bg"])

        self._face_pil         = None
        self._has_face         = False
        self._face_scale_cache = None
        self._load_face(face_path)

        # ── Canvas (background animation) ────────────────────────────────────
        self._logo, self._logo_w = None, 0
        self._load_logo()
        self.bg = _HiDPICanvas(self.root, scale=S, width=int(W * S), height=int(H * S),
                               bg=self.col["bg"], highlightthickness=0)
        self._pl(self.bg, x=0, y=0)
        self.bg.bind("<Motion>", self._on_stage_motion)
        self.bg.bind("<Leave>", self._on_stage_leave)
        self.bg.bind("<Button-1>", self._on_stage_click)

        # ── JARVIS command deck ────────────────────────────────────────────
        # This is intentionally built from native Tk widgets so it remains
        # lightweight and works together with the existing animated canvas.
        self._build_command_deck()

        # ── Log area ─────────────────────────────────────────────────────────
        LW = max(320, W - 440) if W >= 900 else int(W * 0.72)
        LH = int(H * 0.11)
        LOG_Y = H - LH - int(H * 0.13)
        self._build_chat_panel(LW, LH, LOG_Y)

        # ── Keyboard input ────────────────────────────────────────────────────
        # Keep the footer controls below the input even on compact windows.
        INPUT_Y = min(LOG_Y + LH + 6, H - 112)
        self._build_input_bar(LW, INPUT_Y)

        # ── Mute button ───────────────────────────────────────────────────────
        self._build_mute_button()

        # ── Hotkeys ───────────────────────────────────────────────────────────
        self.root.bind("<F4>", lambda e: self._toggle_mute())
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.root.bind("<Escape>", lambda e: self._exit_fullscreen())
        self.root.bind("<F6>", lambda e: self._toggle_silent_mode())
        self.root.bind("<F5>", lambda e: self.cycle_theme())

        # Re-layout widgets when the window is resized
        self.root.bind("<Configure>", self._on_configure)
        self._relayout()

        # ── API key ───────────────────────────────────────────────────────────
        self._api_key_ready = self._api_keys_exist()
        if not self._api_key_ready:
            self._show_setup_ui()

        self.root.deiconify()
        self.root.lift()

        self._animate()
        self.root.protocol("WM_DELETE_WINDOW", lambda: os._exit(0))

    # ── Theme ────────────────────────────────────────────────────────────────


    def _apply_arcade_signal(self, gesture, x):
        self._arcade.on_gesture(gesture, x)

    def _apply_deck_theme(self):
        """Decks are cheap to build, so a theme change simply rebuilds them."""
        for name in ("_left_deck_shell", "_right_deck_shell"):
            shell = getattr(self, name, None)
            if shell is not None:
                try:
                    shell.destroy()
                except tk.TclError:
                    pass
        self._build_command_deck()
        self._relayout()
        self._refresh_deck_status()

    def _build_input_bar(self, lw: int, y: int):
        col = self.col
        x0    = (self.W - lw) // 2
        BTN_W = 62
        CLR_W = 62
        INP_W = lw - BTN_W - CLR_W - 8

        self._input_shell = tk.Frame(
            self.root, bg=col["input"], highlightthickness=px(1),
            highlightbackground=col["inp_border"], highlightcolor=col["inp_border"]
        )
        self._pl(self._input_shell, x=x0, y=y, width=INP_W, height=46)
        self._input_glyph = tk.Label(self._input_shell, text="\u276f", bg=col["input"],
                                     fg=col["mid"], font=("Segoe UI Symbol", 13, "bold"))
        self._input_glyph.pack(side="left", padx=px((12, 4)))
        self._input_text = tk.Text(
            self._input_shell, fg=col["text"], bg=col["input"],
            insertbackground=col["pri"], borderwidth=0, highlightthickness=0,
            font=("Segoe UI", 10), wrap="word", height=2, padx=px(4), pady=px(5),
            relief="flat"
        )
        self._input_text.pack(side="left", fill="both", expand=True)
        self._input_hint = tk.Label(
            self._input_shell, text="Type a command or ask GHOST\u2026   (Enter \u00b7 send,  Shift+Enter \u00b7 new line)",
            bg=col["input"], fg=self._mixc(col["mid"], col["input"], 0.35),
            font=("Segoe UI", 9), cursor="xterm"
        )
        self._input_hint.bind("<Button-1>", lambda e: self._input_text.focus_set())
        self._input_text.bind("<FocusIn>", lambda e: self._input_focus(True))
        self._input_text.bind("<FocusOut>", lambda e: self._input_focus(False))
        self._input_text.bind("<KeyRelease>", self._update_input_hint)
        self._input_text.bind("<Return>", self._on_input_submit)
        self._input_text.bind("<KP_Enter>", self._on_input_submit)
        self._input_text.bind("<Shift-Return>", self._on_newline)
        self._input_text.bind("<Shift-KP_Enter>", self._on_newline)
        self._input_text.bind("<Up>", self._on_hist_prev)
        self._input_text.bind("<Down>", self._on_hist_next)
        self._update_input_hint()

        self._cmd_history = []
        self._hist_idx    = -1
        self._draft       = ""

        self._clear_btn = tk.Button(
            self.root, text="CLEAR", command=self._on_clear_log,
            fg=col["mid"], bg=col["panel"],
            activeforeground=col["bg"], activebackground=col["acc2"],
            font=("Segoe UI", 9, "bold"), borderwidth=0, cursor="hand2",
            highlightthickness=px(1), highlightbackground=col["inp_border"],
        )
        self._pl(self._clear_btn, x=x0 + INP_W + 4, y=y, width=CLR_W, height=46)

        self._send_btn = tk.Button(
            self.root, text="SEND \u25b8", command=self._on_input_submit,
            fg=col["bg"], bg=col["pri"],
            activeforeground=col["bg"], activebackground=col["acc2"],
            font=("Segoe UI", 9, "bold"), borderwidth=0, cursor="hand2",
            highlightthickness=px(1), highlightbackground=col["pri"],
        )
        self._pl(self._send_btn, x=x0 + INP_W + CLR_W + 8, y=y, width=BTN_W, height=46)

    def _build_mute_button(self):
        BTN_W, BTN_H = 110, 32
        BTN_X = 18
        BTN_Y = self.H - 70

        self._mute_canvas = _HiDPICanvas(
            self.root, scale=self.S, width=px(BTN_W), height=px(BTN_H),
            bg=self.col["bg"], highlightthickness=0, cursor="hand2"
        )
        self._pl(self._mute_canvas, x=BTN_X, y=BTN_Y)
        self._mute_canvas.bind("<Button-1>", lambda e: self._toggle_mute())
        self._draw_mute_button()

        self._silent_canvas = _HiDPICanvas(
            self.root, scale=self.S, width=px(150), height=px(32),
            bg=self.col["bg"], highlightthickness=0, cursor="hand2"
        )
        self._pl(self._silent_canvas, x=136, y=BTN_Y)
        self._silent_canvas.bind("<Button-1>", lambda e: self._toggle_silent_mode())
        self._draw_silent_button()

    def _draw_mute_button(self):
        c = self._mute_canvas
        c.delete("all")
        if self.muted:
            border = self.col["mutcol"]
            fill   = "#1a0008"
            icon   = "🔇"
            label  = " MUTED"
            fg     = self.col["mutcol"]
        else:
            border = self.col["mid"]
            fill   = self.col["panel"]
            icon   = "🎙"
            label  = " LIVE"
            fg     = self.col["green"]

        c.create_rectangle(0, 0, 110, 32, outline=border, fill=fill, width=1)
        c.create_text(55, 16, text=f"{icon}{label}",
                      fill=fg, font=("Segoe UI", 10, "bold"))

    def _draw_silent_button(self):
        c = getattr(self, "_silent_canvas", None)
        if c is None:
            return
        c.delete("all")
        active = self.silent_mode
        border = self.col["acc2"] if active else self.col["mid"]
        fill = "#211900" if active else self.col["panel"]
        fg = self.col["acc2"] if active else self.col["text"]
        label = " TEXT-ONLY" if active else " VOICE ON"
        c.create_rectangle(0, 0, 150, 32, outline=border, fill=fill, width=1)
        c.create_text(75, 16, text=f"▣{label}", fill=fg, font=("Segoe UI", 10, "bold"))

    def _get_input(self) -> str:
        return self._input_text.get("1.0", "end-1c")

    # ── Scaling / window helpers ─────────────────────────────────────────────

    def _pl(self, widget, **kw):
        """place() in logical units."""
        for k in ("x", "y", "width", "height"):
            v = kw.get(k)
            if isinstance(v, (int, float)):
                kw[k] = int(round(v * self.S))
        widget.place(**kw)

    def _toggle_fullscreen(self):
        self._fs = not self._fs
        try:
            self.root.attributes("-fullscreen", self._fs)
        except tk.TclError:
            self._fs = False

    def _exit_fullscreen(self):
        if self._fs:
            self._toggle_fullscreen()

    def _load_logo(self):
        self._logo, self._logo_w = None, 0
        if Image is None or ImageTk is None:
            return
        try:
            p = Path(str(self.brand.get("logo") or ""))
            if not p.is_absolute():
                p = BASE_DIR / p
            if not p.is_file():
                return
            img = Image.open(p).convert("RGBA")
            h = int(round(40 * self.S))
            w = max(1, int(img.width * h / img.height))
            max_w = int(190 * self.S)
            if w > max_w:
                w, h = max_w, max(1, int(img.height * max_w / img.width))
            img = img.resize((w, h), Image.Resampling.LANCZOS)
            self._logo = ImageTk.PhotoImage(img)
            self._logo_w = w / self.S
        except Exception:
            self._logo, self._logo_w = None, 0

    def _on_clear_log(self):
        self._safe_ui(self._clear_log)

    def _on_configure(self, event=None):
        if event is None or event.widget is not self.root:
            return
        W = max(1, int(round(event.width / self.S)))
        H = max(1, int(round(event.height / self.S)))
        if W == self.W and H == self.H:
            return
        self.W, self.H = W, H
        self.bg.configure(width=int(W * self.S), height=int(H * self.S))
        self.FACE_SZ = min(int(self.H * 0.40), 360)
        self.FCX     = self.W // 2
        self.FCY     = int(self.H * 0.11) + self.FACE_SZ // 2
        self._relayout()

    def _on_hist_next(self, event=None):
        if self._hist_idx == -1:
            return "break"
        if self._hist_idx < len(self._cmd_history) - 1:
            self._hist_idx += 1
            self._set_input(self._cmd_history[self._hist_idx])
        else:
            self._hist_idx = -1
            self._set_input(self._draft)
        return "break"

    def _on_hist_prev(self, event=None):
        if not self._cmd_history:
            return "break"
        if self._hist_idx == -1:
            self._draft    = self._get_input()
            self._hist_idx = len(self._cmd_history)
        if self._hist_idx > 0:
            self._hist_idx -= 1
            self._set_input(self._cmd_history[self._hist_idx])
        return "break"

    def _on_input_submit(self, event=None):
        raw_text = self._get_input()
        print(f"[UI INPUT DEBUG] raw={raw_text!r}")
        text = raw_text.strip()
        print(f"[UI INPUT DEBUG] submitted={text!r}")
        if not text:
            return "break"
        self._set_input("")
        self._cmd_history.append(text)
        if len(self._cmd_history) > 50:
            del self._cmd_history[0]
        self._hist_idx = -1
        self._draft    = ""
        self.write_log(f"You: {text}")
        if self.on_text_command:
            threading.Thread(
                target=self.on_text_command,
                args=(text,),
                daemon=True
            ).start()
        return "break"

    def _on_newline(self, event=None):
        self._input_text.insert(tk.INSERT, "\n")
        return "break"

    def _refresh_deck_status(self):
        col = self.col
        active = self.vision_mode != "STANDBY"
        try:
            if hasattr(self, "_vision_status"):
                self._vision_status.configure(
                    text="\u25cf " + self.vision_mode, bg=col["input"],
                    fg=col["green"] if active else col["mid"])
            if hasattr(self, "_vision_signal_label"):
                self._vision_signal_label.configure(text=self.vision_signal,
                                                    bg=col["input"], fg=col["text"])
            for b in getattr(self, "_deck_buttons", []):
                if b.mode:
                    b.set_active(active and b.mode.upper() == self.vision_mode)
        except tk.TclError:
            pass

    def _relayout(self):
        W, H = self.W, self.H
        side_margin = 228 if W >= 980 else 18
        LW = max(360, W - (side_margin * 2)) if W >= 980 else int(W * 0.86)
        LW = min(LW, W - 36)
        LH = max(110, min(170, int(H * 0.19)))
        LOG_Y = H - LH - 112
        self._stage_bottom = LOG_Y - 8
        self._pl(self.log_frame, x=(W - LW) // 2, y=LOG_Y, width=LW, height=LH)

        INPUT_Y = LOG_Y + LH + 8
        x0 = (W - LW) // 2
        BTN_W, CLR_W = 88, 72
        INP_W = max(150, LW - BTN_W - CLR_W - 12)
        self._pl(self._input_shell, x=x0, y=INPUT_Y, width=INP_W, height=48)
        self._pl(self._clear_btn, x=x0 + INP_W + 4, y=INPUT_Y, width=CLR_W, height=48)
        self._pl(self._send_btn, x=x0 + INP_W + CLR_W + 8, y=INPUT_Y,
                             width=BTN_W, height=48)

        footer_y = H - 35
        self._pl(self._mute_canvas, x=18, y=footer_y)
        if getattr(self, "_silent_canvas", None) is not None:
            self._pl(self._silent_canvas, x=140, y=footer_y)
        if W >= 980:
            deck_h = max(300, H - 210)
            self._pl(self._left_deck_shell, x=16, y=96, width=194, height=deck_h)
            self._pl(self._right_deck_shell, x=W - 226, y=96, width=210, height=deck_h)
        else:
            self._left_deck_shell.place_forget()
            self._right_deck_shell.place_forget()

    def _render_arcade_frame(self, frame):
        if self._arcade_label is None:
            return
        try:
            cv2 = import_module("cv2")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            target_w = max(420, self._arcade_label.winfo_width() - 24)
            target_h = max(300, self._arcade_label.winfo_height() - 24)
            image = ImageOps.fit(image, (target_w, target_h), method=Image.Resampling.LANCZOS,
                                 centering=(0.5, 0.5))
            draw = ImageDraw.Draw(image)
            state = self._arcade.state
            hud_h = max(88, image.height // 8)
            title_font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", max(18, image.width // 55))
            msg_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", max(15, image.width // 72))
            draw.rectangle((0, 0, image.width, hud_h), fill="#001520", outline="#00d4ff", width=3)
            draw.text((24, 14), f"{state.game.upper()}   SCORE {state.score}   LIVES {state.lives}",
                      fill="#8ffcff", font=title_font, stroke_width=2, stroke_fill="#001520")
            extra = f"  ROUND {state.rounds}  STREAK {state.streak}" if state.rounds else ""
            draw.text((24, 14 + title_font.size + 8), state.message + extra,
                      fill="#ffcc00", font=msg_font, stroke_width=1, stroke_fill="#001520")
            if state.game == "floor_lava":
                draw.rectangle((0, int(image.height * 0.82), image.width, image.height), fill="#8b1900")
                draw.text((24, int(image.height * 0.86)), "LAVA", fill="#ffcc00", font=title_font)
            elif state.game == "planet_explorer":
                cx, cy = int(image.width * 0.72), int(image.height * 0.55)
                draw.ellipse((cx - 100, cy - 100, cx + 100, cy + 100), outline="#38bdf8", width=5)
                px = cx - 100 + int(state.planet_x * 200)
                draw.line((cx, cy, px, cy - 130), fill="#ffcc00", width=3)
            elif state.game == "laser_defense":
                x = int(state.hand_x * image.width)
                draw.line((x, image.height - 30, x, 80), fill="#ff3366", width=4)
            elif state.game == "arpeggiator":
                for i, note in enumerate(("C", "D", "E", "G", "A")):
                    x = 30 + i * 70
                    bar = 35 if note == state.note else 15
                    draw.rectangle((x, image.height - 50 - bar, x + 42, image.height - 50), fill="#00d4ff")
                    draw.text((x + 12, image.height - 42), note, fill="#001520", font=msg_font)
            elif state.game == "shape_creator":
                cx, cy = int(state.hand_x * image.width), int(image.height * 0.55)
                if state.shape == "circle":
                    draw.ellipse((cx - 45, cy - 45, cx + 45, cy + 45), outline="#00d4ff", width=5)
                elif state.shape == "square":
                    draw.rectangle((cx - 45, cy - 45, cx + 45, cy + 45), outline="#00d4ff", width=5)
                else:
                    draw.polygon((cx, cy - 55, cx - 55, cy + 45, cx + 55, cy + 45), outline="#00d4ff")
            elif state.game == "orb_hunt":
                cx, cy = int(state.target_x * image.width), int(image.height * 0.55)
                radius = max(24, 48 - state.level * 2)
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                             fill="#ff4fd8", outline="#fff3ff", width=4)
                draw.ellipse((cx - radius // 3, cy - radius // 3,
                              cx + radius // 3, cy + radius // 3), fill="#ffe66d")
            self._arcade_image = ImageTk.PhotoImage(image)
            self._arcade_label.configure(image=self._arcade_image, text="")
        except Exception:
            pass

    def _render_vision_frame(self, frame):
        if self._preview_label is None:
            return
        try:
            cv2 = import_module("cv2")
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            target_w = max(320, self._preview_label.winfo_width() - 24)
            target_h = max(240, self._preview_label.winfo_height() - 24)
            image = ImageOps.contain(image, (target_w, target_h), method=Image.Resampling.LANCZOS)
            self._preview_image = ImageTk.PhotoImage(image)
            self._preview_label.configure(image=self._preview_image, text="")
        except Exception:
            pass

    def _set_input(self, text: str):
        self._input_text.delete("1.0", tk.END)
        self._input_text.insert("1.0", text)
        self._input_text.mark_set(tk.INSERT, "end-1c")
        self._update_input_hint()

    def _start_arcade_game(self, game):
        self._arcade.start(game)
        self.write_log("SYS: Vision Arcade → " + game)

    def _toggle_mute(self):
        self.muted = not self.muted
        self._draw_mute_button()
        if self.muted:
            self.set_state("MUTED")
            self.write_log("SYS: Microphone muted.")
        else:
            self.set_state("LISTENING")
            self.write_log("SYS: Microphone active.")

    def _toggle_silent_mode(self):
        self.silent_mode = not self.silent_mode
        self._draw_silent_button()
        self.set_state("TEXT-ONLY" if self.silent_mode else ("MUTED" if self.muted else "LISTENING"))
        self.write_log("SYS: Text-only mode enabled — GHOST will type, not speak." if self.silent_mode
                       else "SYS: Voice output restored.")

    def open_vision_arcade(self):
        if self._arcade_window is not None and self._arcade_window.winfo_exists():
            self._arcade_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("GHOST Vision Arcade · Local CV")
        win.configure(bg=self.col["bg"])
        win.geometry(f"{px(1100)}x{px(760)}")
        win.minsize(px(900), px(620))
        try:
            win.state("zoomed")
        except tk.TclError:
            pass
        toolbar = tk.Frame(win, bg=self.col["panel"])
        toolbar.pack(fill="x", padx=px(10), pady=px(10))
        for label, game in [("FACE FILTER", "face_filter"),
                            ("GESTURE PONG", "gesture_pong"),
                            ("ORB HUNT", "orb_hunt"),
                            ("ROCK PAPER SCISSORS", "rps"),
                            ("SHAPE CREATOR", "shape_creator"),
                            ("FLOOR IS LAVA", "floor_lava"),
                            ("PLANET EXPLORER", "planet_explorer"),
                            ("WHIRLPOOL", "whirlpool"),
                            ("LASER DEFENSE", "laser_defense"),
                            ("ARPEGGIATOR", "arpeggiator")]:
            tk.Button(toolbar, text=label, command=lambda g=game: self._start_arcade_game(g),
                      bg=self.col["input"], fg=self.col["text"], activebackground=self.col["pri"],
                      activeforeground=self.col["bg"], relief="flat", font=("Consolas", 9, "bold"),
                      cursor="hand2").pack(side="left", padx=px(3), ipady=px(7))
        label = tk.Label(win, text="Waiting for camera frames…", bg=self.col["bg"],
                         fg=self.col["text"], font=("Consolas", 11))
        label.pack(fill="both", expand=True, padx=px(12), pady=px((0, 12)))
        self._arcade_window, self._arcade_label = win, label
        self.arcade_open = True
        self._start_arcade_game("face_filter")
        if self.on_text_command:
            threading.Thread(target=self.on_text_command,
                             args=("start vision gesture",), daemon=True).start()

        def close():
            self.arcade_open = False
            self._arcade_window = None
            self._arcade_label = None
            self._arcade.stop()
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)

    def open_vision_preview(self):
        """Open a live preview fed by the existing vision camera thread."""
        if self._preview_window is not None and self._preview_window.winfo_exists():
            self._preview_window.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("GHOST Vision Preview · Privacy Blur")
        win.configure(bg=self.col["bg"])
        win.geometry(f"{px(700)}x{px(560)}")
        win.resizable(True, True)
        label = tk.Label(win, text="Waiting for camera frames…", bg=self.col["bg"],
                         fg=self.col["text"], font=("Consolas", 11))
        label.pack(fill="both", expand=True, padx=px(12), pady=px(12))
        self._preview_window = win
        self._preview_label = label
        self.vision_preview_open = True

        def close():
            self.vision_preview_open = False
            self._preview_window = None
            self._preview_label = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close)

    def set_arcade_frame(self, frame):
        if not self.arcade_open or frame is None:
            return
        self._safe_ui(self._render_arcade_frame, frame)

    def set_arcade_pose(self, arms_raised: bool, lean: float = 0.0):
        if not self.arcade_open:
            return
        self._safe_ui(self._arcade.on_pose, arms_raised, lean)

    def set_arcade_signal(self, gesture: str, x: float = 0.5):
        if not self.arcade_open:
            return
        self._safe_ui(self._apply_arcade_signal, gesture, x)

    def set_connecting(self, on: bool = True):
        self.connecting = bool(on)

    def set_connection(self, ok: bool):
        self.connected  = bool(ok)
        self.connecting = False

    def set_persona(self, mode: str, mood: str, voice: str):
        self.persona_mode  = mode or "normal"
        self.persona_mood  = mood or "calm"
        self.persona_voice = voice or "Aoede"
        self._safe_ui(self._refresh_persona_card)

    def set_vision_detections(self, events):
        """Show a compact object summary from the active detector."""
        counts = {}
        for event in events or []:
            label = getattr(event, "label", "object")
            counts[label] = counts.get(label, 0) + 1
        if counts:
            summary = "OBJECTS: " + ", ".join(
                f"{count}× {label}" for label, count in counts.items()
            )
            self.set_vision_signal(summary)

    def set_vision_frame(self, frame):
        """Receive one privacy-filtered BGR frame from the camera thread."""
        if not self.vision_preview_open or frame is None:
            return
        self._safe_ui(self._render_vision_frame, frame)

    def set_vision_signal(self, text: str):
        """Publish the latest local CV observation to the command deck."""
        self.vision_signal = str(text or "Awaiting camera input")[:120]
        self._safe_ui(self._refresh_deck_status)

    def set_theme(self, name: str):
        if name not in THEMES:
            return
        self._theme = name
        self.col    = dict(THEMES[name])
        _save_theme_name(name)
        self._safe_ui(self._apply_theme_ui)

    def cycle_theme(self):
        names = list(THEMES.keys())
        idx   = names.index(self._theme)
        self.set_theme(names[(idx + 1) % len(names)])
        self.write_log(f"SYS: Theme → {THEMES[self._theme]['name']}.")

    def _apply_theme_ui(self):
        self.root.configure(bg=self.col["bg"])
        self.bg.configure(bg=self.col["bg"])
        for cv in (getattr(self, "_mute_canvas", None), getattr(self, "_silent_canvas", None)):
            if cv is not None:
                cv.configure(bg=self.col["bg"])
        self._style_chat()
        self._draw_mute_button()
        self._draw_silent_button()
        self._refresh_input_style()
        self._apply_deck_theme()

    def _refresh_input_style(self):
        col = self.col
        try:
            self._input_shell.configure(bg=col["input"], highlightbackground=col["inp_border"],
                                        highlightcolor=col["inp_border"])
            self._input_glyph.configure(bg=col["input"], fg=col["mid"])
            self._input_text.configure(fg=col["text"], bg=col["input"],
                                       insertbackground=col["pri"])
            self._input_hint.configure(bg=col["input"],
                                       fg=self._mixc(col["mid"], col["input"], 0.35))
            self._clear_btn.configure(fg=col["mid"], bg=col["panel"],
                                      activebackground=col["acc2"],
                                      highlightbackground=col["inp_border"])
            self._send_btn.configure(fg=col["bg"], bg=col["pri"],
                                     activebackground=col["acc2"],
                                     highlightbackground=col["pri"])
        except Exception:
            pass

    def _build_command_deck(self):
        """Build the live control surface around the central GHOST core."""
        col = self.col
        acc = self._accents()
        self._deck_buttons = []
        (self._left_deck_shell, self._left_deck,
         self._left_deck_canvas) = self._create_scrollable_deck(
            "COMMAND DECK", "SYSTEM CONTROL LINK", col["pri"])
        (self._right_deck_shell, self._right_deck,
         self._right_deck_canvas) = self._create_scrollable_deck(
            "VISION DECK", "LOCAL CV \u00b7 CAMERA SUITE", col["acc2"])
        Ld, Rd = self._left_deck, self._right_deck

        self._deck_label(Ld, "QUICK ACTIONS", col["pri"])
        self._deck_button(Ld, "VISION ARCADE", "__open_arcade__", icon="\u25c8", accent=acc[3])
        self._deck_button(Ld, "AKKHOR SCHOOL", "__open_akkhor__", icon="\u25a3", accent=acc[1])
        for label, command, icon in [
            ("DAILY BRIEFING", "give me my daily briefing", "\u2630"),
            ("SYSTEM STATUS", "show system status", "\u25c9"),
            ("READ SCREEN", "read my screen", "\u25d0"),
            ("FOCUS MODE", "start focus mode", "\u25ce"),
        ]:
            self._deck_button(Ld, label, command, icon=icon, accent=col["pri"])
        self._deck_label(Ld, "PLANT INTELLIGENCE", col["acc"])
        for label, command, icon in [
            ("MACHINE UTILIZATION", "show machine utilization", "\u25a6"),
            ("PRODUCTION REPORT", "show today's production report", "\u2630"),
            ("ASSET STATUS", "show asset status", "\u25a3"),
            ("SM DASHBOARD", "show smart manufacturing summary", "\u25c8"),
        ]:
            self._deck_button(Ld, label, command, icon=icon, accent=col["acc"])
        self._deck_label(Ld, "AI PROFILE", acc[2])
        self._persona_labels = self._deck_info_card(Ld, [
            ("MODE", str(self.persona_mode).upper()),
            ("MOOD", str(self.persona_mood).upper()),
            ("VOICE", str(self.persona_voice)),
        ])

        self._deck_label(Rd, "CAMERA CONTROL", col["acc2"])
        self._deck_button(Rd, "OPEN CAMERA PREVIEW", "__open_preview__",
                          icon="\u25c9", accent=col["acc2"])
        for label, mode, icon in [("GESTURE CONTROL", "gesture", "\u2726"),
                                  ("OBJECT DETECTION", "objects", "\u25a3"),
                                  ("AIR MOUSE", "air_mouse", "\u2316"),
                                  ("VOLUME HAND", "volume", "\u266a"),
                                  ("POSTURE", "posture", "\u25b2"),
                                  ("MOTION WATCH", "motion", "\u25cd")]:
            self._deck_button(Rd, label, f"start vision {mode}", mode, icon=icon, accent=col["pri"])
        self._deck_button(Rd, "START RECORDING", "__record_start__", icon="\u25cf", accent=col["green"])
        self._deck_button(Rd, "STOP RECORDING", "__record_stop__", icon="\u25a0", accent=col["red"])
        self._deck_button(Rd, "STOP VISION", "stop vision", "STANDBY", icon="\u2715", accent=col["red"])

        self._deck_label(Rd, "ONE-SHOT SCANS", col["acc"])
        for label, command, icon in [
                ("SNAPSHOT", "take a camera snapshot", "\u25eb"),
                ("FACE COUNT", "count faces in front of the camera", "\u263a"),
                ("READ QR", "read a QR code with the camera", "\u25a6"),
                ("READ TEXT", "read text with the camera", "T"),
                ("REMOVE BACKGROUND", "remove the background from the camera subject", "\u25cc"),
                ("DESCRIBE SCENE", "describe everything visible to the camera", "\u25cd")]:
            self._deck_button(Rd, label, command, icon=icon, accent=col["acc"])

        self._deck_label(Rd, "STATUS", acc[0])
        card = tk.Frame(Rd, bg=col["inp_border"])
        card.pack(fill="x", padx=px(10), pady=px(4))
        inner = tk.Frame(card, bg=col["input"])
        inner.pack(fill="x", padx=px(1), pady=px(1))
        self._vision_status = tk.Label(inner, text="\u25cf STANDBY", anchor="w",
                                       bg=col["input"], fg=col["mid"],
                                       font=("Consolas", 9, "bold"))
        self._vision_status.pack(fill="x", padx=px(10), pady=px((8, 2)))
        self._vision_signal_label = tk.Label(inner, text=self.vision_signal, anchor="w",
                                             justify="left", wraplength=px(160),
                                             bg=col["input"], fg=col["text"],
                                             font=("Consolas", 8))
        self._vision_signal_label.pack(fill="x", padx=px(10), pady=px((0, 8)))

        self._deck_label(Rd, "LOCAL CV MODULES", acc[3])
        for name in ("HAND LANDMARKS", "POSE ESTIMATION", "QR / FACE SCAN"):
            self._deck_status_row(Rd, name, "READY")
        tk.Frame(Rd, bg=col["panel"], height=px(10)).pack()

        self._bind_deck_mousewheel(self._left_deck, self._left_deck_canvas)
        self._bind_deck_mousewheel(self._right_deck, self._right_deck_canvas)

    def _bind_deck_mousewheel(self, parent, canvas):
        def wheel(event):
            if event.delta:
                canvas.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            return "break"

        def bind_children(widget):
            widget.bind("<MouseWheel>", wheel)
            widget.bind("<Button-4>", wheel)
            widget.bind("<Button-5>", wheel)
            for child in widget.winfo_children():
                bind_children(child)

        bind_children(parent)

    def _create_scrollable_deck(self, title="DECK", subtitle="", color=None):
        """Themed deck: glowing header + vertically scrollable body."""
        col = self.col
        color = color or col["pri"]
        shell = tk.Frame(self.root, bg=col["panel"],
                         highlightbackground=col["inp_border"], highlightthickness=px(1))
        header = _HiDPICanvas(shell, scale=self.S, height=px(54), bg=col["panel"],
                              highlightthickness=0, borderwidth=0)
        header.pack(side="top", fill="x")

        def draw_header(event=None, h=header):
            w = h.winfo_width() / self.S
            if w < 50:
                w = 190
            h.delete("all")
            h.create_polygon(self._hexpts(26, 26, 12, 0), outline=color,
                             fill=self._mixc(col["panel"], color, 0.16), width=2)
            h.create_oval(22, 22, 30, 30, fill=color, outline="")
            h.create_text(48, 20, text=title, anchor="w", fill=color,
                          font=("Consolas", 10, "bold"))
            h.create_text(48, 37, text=subtitle, anchor="w", fill=col["mid"],
                          font=("Consolas", 7))
            h.create_oval(w - 20, 17, w - 13, 24, fill=col["green"], outline="")
            h.create_line(10, 51, w - 10, 51, fill=col["inp_border"])
            h.create_line(10, 51, 10 + (w - 20) * 0.38, 51, fill=color, width=2)
            for x, dx in ((4, 1), (w - 4, -1)):
                h.create_line(x, 4, x + dx * 8, 4, fill=color)
                h.create_line(x, 4, x, 12, fill=color)

        header.bind("<Configure>", draw_header)
        draw_header()

        body = tk.Frame(shell, bg=col["panel"])
        body.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(body, bg=col["panel"], highlightthickness=0,
                           borderwidth=0, yscrollincrement=px(24))
        scrollbar = tk.Scrollbar(
            body, orient="vertical", command=canvas.yview,
            bg=col["panel"], troughcolor=col["hdr"], activebackground=col["mid"],
            relief="flat", borderwidth=0, width=px(7)
        )
        content = tk.Frame(canvas, bg=col["panel"])
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>",
                     lambda event, c=canvas: c.configure(scrollregion=c.bbox("all")))
        canvas.bind("<Configure>",
                    lambda event, c=canvas, item=window_id: c.itemconfigure(item, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True, padx=px((1, 0)), pady=px(1))
        scrollbar.pack(side="right", fill="y", padx=px((0, 2)), pady=px(4))

        def wheel(event, c=canvas):
            if event.delta:
                c.yview_scroll(int(-event.delta / 120), "units")
            elif getattr(event, "num", None) == 4:
                c.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                c.yview_scroll(1, "units")
            return "break"

        for widget in (shell, header, body, canvas, content):
            widget.bind("<MouseWheel>", wheel)
            widget.bind("<Button-4>", wheel)
            widget.bind("<Button-5>", wheel)
        return shell, content, canvas

    def _deck_title(self, parent, text, color):
        """Kept for compatibility: decks now draw their own header."""
        tk.Label(parent, text=text, fg=color, bg=self.col["panel"],
                 font=("Consolas", 10, "bold")).pack(anchor="w", padx=px(12), pady=(px(8), px(4)))

    def _deck_status_row(self, parent, name, state):
        col = self.col
        row = tk.Frame(parent, bg=col["panel"])
        row.pack(fill="x", padx=px(14), pady=px(2))
        tk.Label(row, text=name, anchor="w", bg=col["panel"], fg=col["mid"],
                 font=("Consolas", 8)).pack(side="left")
        tk.Label(row, text="\u25cf " + state, bg=col["panel"], fg=col["green"],
                 font=("Consolas", 8, "bold")).pack(side="right")

    def _deck_info_card(self, parent, rows):
        """Bordered key/value card; returns {key: value_label}."""
        col = self.col
        card = tk.Frame(parent, bg=col["inp_border"])
        card.pack(fill="x", padx=px(10), pady=px(4))
        inner = tk.Frame(card, bg=col["input"])
        inner.pack(fill="x", padx=px(1), pady=px(1))
        labels = {}
        for key, value in rows:
            row = tk.Frame(inner, bg=col["input"])
            row.pack(fill="x", padx=px(10), pady=px(3))
            tk.Label(row, text=key, bg=col["input"], fg=col["mid"],
                     font=("Consolas", 8, "bold")).pack(side="left")
            lbl = tk.Label(row, text=value, bg=col["input"], fg=col["text"],
                           font=("Consolas", 8, "bold"))
            lbl.pack(side="right")
            labels[key] = lbl
        return labels

    def _refresh_persona_card(self):
        labels = getattr(self, "_persona_labels", None)
        if not labels:
            return
        try:
            labels["MODE"].configure(text=str(self.persona_mode).upper())
            labels["MOOD"].configure(text=str(self.persona_mood).upper())
            labels["VOICE"].configure(text=str(self.persona_voice))
        except tk.TclError:
            pass

    # ── Chat panel ───────────────────────────────────────────────────────────

    def _build_chat_panel(self, LW, LH, LOG_Y):
        col = self.col
        self.log_frame = tk.Frame(self.root, bg=col["panel"],
                                  highlightbackground=col["inp_border"], highlightthickness=px(1))
        self._pl(self.log_frame, x=(self.W - LW) // 2, y=LOG_Y, width=LW, height=LH)

        self.log_header = tk.Frame(self.log_frame, bg=col["panel"])
        self.log_header.pack(fill="x", padx=px(12), pady=px((8, 0)))
        self.log_icon = tk.Label(self.log_header, text="\u25c8", bg=col["panel"], fg=col["pri"],
                                 font=("Segoe UI Symbol", 9, "bold"))
        self.log_icon.pack(side="left")
        self.log_heading = tk.Label(self.log_header, text="  COMMUNICATION LINK",
                                    bg=col["panel"], fg=col["pri"], anchor="w",
                                    font=("Consolas", 8, "bold"))
        self.log_heading.pack(side="left")
        self.log_state = tk.Label(self.log_header, text="\u25cf STANDBY", bg=col["panel"],
                                  fg=col["mid"], font=("Consolas", 8, "bold"))
        self.log_state.pack(side="right")
        self.log_rule = tk.Frame(self.log_frame, height=px(1), bg=col["inp_border"])
        self.log_rule.pack(fill="x", padx=px(12), pady=px((7, 0)))

        log_body = tk.Frame(self.log_frame, bg=col["panel"])
        log_body.pack(fill="both", expand=True, padx=px((8, 4)), pady=px((2, 6)))
        self.log_text = tk.Text(
            log_body, fg=col["text"], bg=col["panel"], insertbackground=col["text"],
            borderwidth=0, wrap="word", font=("Segoe UI", 10), padx=px(8), pady=px(4),
            selectbackground=col["mid"], relief="flat", spacing1=px(3), spacing3=px(3),
            tabs=("54p",), cursor="arrow", highlightthickness=0
        )
        self.log_scroll = tk.Scrollbar(
            log_body, orient="vertical", command=self.log_text.yview, width=px(8),
            bg=col["panel"], troughcolor=col["hdr"], activebackground=col["mid"],
            relief="flat", borderwidth=0
        )
        self.log_text.configure(yscrollcommand=self.log_scroll.set)
        self.log_scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        self.log_text.configure(state="disabled")
        self._style_chat()

    def _style_chat(self):
        col = self.col
        try:
            self.log_frame.configure(bg=col["panel"], highlightbackground=col["inp_border"])
            self.log_header.configure(bg=col["panel"])
            self.log_icon.configure(bg=col["panel"], fg=col["pri"])
            self.log_heading.configure(bg=col["panel"], fg=col["pri"])
            self.log_state.configure(bg=col["panel"])
            self.log_rule.configure(bg=col["inp_border"])
            self.log_text.configure(fg=col["text"], bg=col["panel"],
                                    insertbackground=col["text"], selectbackground=col["mid"])
            self.log_scroll.configure(bg=col["panel"], troughcolor=col["hdr"],
                                      activebackground=col["mid"])
        except tk.TclError:
            return
        t = self.log_text
        quiet = self._mixc(col["mid"], col["bg"], 0.35)
        hang = dict(lmargin1=0, lmargin2="54p")
        t.tag_config("ts", foreground=quiet, font=("Consolas", 7), **hang)
        t.tag_config("lbl_you", foreground=col["acc"], font=("Consolas", 8, "bold"), **hang)
        t.tag_config("lbl_ai", foreground=col["pri"], font=("Consolas", 8, "bold"), **hang)
        t.tag_config("lbl_sys", foreground=col["mid"], font=("Consolas", 8, "bold"), **hang)
        t.tag_config("lbl_err", foreground=col["red"], font=("Consolas", 8, "bold"), **hang)
        t.tag_config("you", foreground=col["text"], **hang)
        t.tag_config("ai", foreground=self._mixc(col["pri"], col["text"], 0.45), **hang)
        t.tag_config("sys", foreground=self._mixc(col["acc2"], col["bg"], 0.2), **hang)
        t.tag_config("err", foreground=col["red"], **hang)
        self._update_log_state()

    def _update_log_state(self):
        lbl = getattr(self, "log_state", None)
        if lbl is None:
            return
        col = self.col
        s = str(self.status_text)
        color = {"SPEAKING": col["acc"], "THINKING": col["acc2"], "PROCESSING": col["acc2"],
                 "LISTENING": col["green"], "MUTED": col["mutcol"]}.get(s, col["pri"])
        try:
            lbl.configure(text="\u25cf " + s, fg=color)
        except tk.TclError:
            pass

    def _update_input_hint(self, event=None):
        hint = getattr(self, "_input_hint", None)
        if hint is None:
            return
        if self._input_text.get("1.0", "end-1c"):
            hint.place_forget()
        else:
            self._pl(hint, in_=self._input_text, x=6, rely=0.5, anchor="w")

    def _input_focus(self, on):
        col = self.col
        color = col["pri"] if on else col["inp_border"]
        try:
            self._input_shell.configure(highlightbackground=color, highlightcolor=color)
            self._input_glyph.configure(fg=col["pri"] if on else col["mid"])
        except tk.TclError:
            pass

    def _deck_label(self, parent, text, color=None, compact=False):
        col = self.col
        color = color or col["mid"]
        row = tk.Frame(parent, bg=col["panel"])
        row.pack(fill="x", padx=px(12), pady=(5 if compact else 14, 4))
        tk.Label(row, text="\u25c6", fg=color, bg=col["panel"],
                 font=("Segoe UI Symbol", 6)).pack(side="left")
        tk.Label(row, text=" " + text, fg=self._mixc(color, col["panel"], 0.2),
                 bg=col["panel"], font=("Consolas", 8, "bold")).pack(side="left")
        tk.Frame(row, bg=col["inp_border"], height=px(1)).pack(side="left", fill="x",
                                                           expand=True, padx=px((8, 0)), pady=px((2, 0)))

    def _deck_button(self, parent, text, command, mode=None, icon="\u203a", accent=None):
        btn = _DeckButton(self, parent, text, icon, accent or self.col["pri"],
                          lambda: self._deck_command(command, mode), mode)
        self._deck_buttons.append(btn)
        return btn

    def _deck_command(self, command, mode=None):
        if command == "__open_akkhor__":
            self.open_akkhor_panel()
            return
        if command == "__open_preview__":
            self.open_vision_preview()
            return
        if command == "__open_arcade__":
            self.open_vision_arcade()
            return
        if command in ("__record_start__", "__record_stop__"):
            self.write_log("SYS: " + ("Recording requested." if command == "__record_start__" else "Recording stop requested."))
            if self.on_text_command:
                text = "start recording" if command == "__record_start__" else "stop recording"
                threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()
            return
        self.vision_mode = (mode or self.vision_mode).upper()
        self._safe_ui(self._refresh_deck_status)
        self.write_log("SYS: Command deck → " + command)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(command,), daemon=True).start()

    def set_akkhor_service(self, service):
        """Attach the shared Akkhor API service created by GHOSTLive."""
        self.akkhor_service = service

    def open_akkhor_panel(self):
        """Open or raise the built-in Akkhor school integration panel."""
        if self.akkhor_service is None:
            self.write_log("ERR: Akkhor integration service is not initialised yet.")
            return
        try:
            if self._akkhor_panel is not None and self._akkhor_panel.win.winfo_exists():
                self._akkhor_panel.lift()
                return
        except Exception:
            self._akkhor_panel = None
        try:
            from actions.akkhor.akkhor_panel import AkkhorPanel
            self._akkhor_panel = AkkhorPanel(
                self.root, self.akkhor_service, on_command=self.on_text_command
            )
        except Exception as exc:
            self.write_log(f"ERR: Could not open Akkhor panel — {exc}")


    def _clear_log(self):
        self.typing_queue.clear()
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state="disabled")


    def _safe_ui(self, fn, *args):
        """Run a UI mutation on the Tk main thread only (thread-safe)."""
        if threading.current_thread() is self._main_thread:
            return fn(*args)
        self._ui_deferred.append((fn, args))

    def set_state(self, state: str):
        self._safe_ui(self._set_state, state)

    def _set_state(self, state: str):
        """
        Called from main.py.
        state: LISTENING | SPEAKING | THINKING | MUTED | ONLINE | PROCESSING
        """
        self._state = state
        if state == "MUTED":
            self.status_text = "MUTED"
            self.speaking    = False
        elif state == "SPEAKING":
            self.status_text = "SPEAKING"
            self.speaking    = True
        elif state == "THINKING":
            self.status_text = "THINKING"
            self.speaking    = False
        elif state == "LISTENING":
            self.status_text = "LISTENING"
            self.speaking    = False
        elif state == "PROCESSING":
            self.status_text = "PROCESSING"
            self.speaking    = False
        else:
            self.status_text = "ONLINE"
            self.speaking    = False
        self._update_log_state()

    # ── Face loading ─────────────────────────────────────────────────────────

    def _load_face(self, path):
        FW = self.FACE_SZ
        try:
            if Image is None or ImageDraw is None:
                self._has_face = False
                return
            img  = Image.open(path).convert("RGBA").resize((FW, FW), Image.LANCZOS)
            mask = Image.new("L", (FW, FW), 0)
            ImageDraw.Draw(mask).ellipse((2, 2, FW - 2, FW - 2), fill=255)
            img.putalpha(mask)
            self._face_pil = img
            self._has_face = True
        except Exception:
            self._has_face = False

    @staticmethod
    def _ac(r, g, b, a):
        f = a / 255.0
        return f"#{int(r*f):02x}{int(g*f):02x}{int(b*f):02x}"

    # ── Animation loop ───────────────────────────────────────────────────────

    def _animate(self):
        while self._ui_deferred:
            _fn, _args = self._ui_deferred.popleft()
            try:
                _fn(*_args)
            except Exception:
                pass
        self.tick += 1
        t   = self.tick
        now = time.time()

        if now - self.last_t > (0.14 if self.speaking else 0.55):
            if self.speaking:
                self.target_scale = random.uniform(1.05, 1.11)
                self.target_halo  = random.uniform(138, 182)
            elif self.muted:
                self.target_scale = random.uniform(0.998, 1.001)
                self.target_halo  = random.uniform(20, 32)
            else:
                self.target_scale = random.uniform(1.001, 1.007)
                self.target_halo  = random.uniform(50, 68)
            self.last_t = now

        sp = 0.35 if self.speaking else 0.16
        self.scale  += (self.target_scale - self.scale) * sp
        self.halo_a += (self.target_halo  - self.halo_a) * sp

        for i, spd in enumerate([1.2, -0.8, 1.9] if self.speaking else [0.5, -0.3, 0.82]):
            self.rings_spin[i] = (self.rings_spin[i] + spd) % 360

        self.scan_angle  = (self.scan_angle  + (2.8 if self.speaking else 1.2)) % 360
        self.scan2_angle = (self.scan2_angle + (-1.7 if self.speaking else -0.68)) % 360

        pspd  = 3.8 if self.speaking else 1.8
        limit = self.FACE_SZ * 0.72
        new_p = [r + pspd for r in self.pulse_r if r + pspd < limit]
        if len(new_p) < 3 and random.random() < (0.06 if self.speaking else 0.022):
            new_p.append(0.0)
        self.pulse_r = new_p

        if t % 40 == 0:
            self.status_blink = not self.status_blink

        self._draw()
        self.root.after(16, self._animate)

    # ── Battery (cached, lightweight) ─────────────────────────────────────────

    def _battery_text(self) -> str:
        now = time.time()
        if self._batt_cache is None or now - self._batt_ts > 5:
            self._batt_ts = now
            try:
                import importlib
                psutil = importlib.import_module("psutil")
                batt = psutil.sensors_battery()
                if batt is None:
                    self._batt_cache = None
                else:
                    self._batt_cache = int(batt.percent)
            except Exception:
                self._batt_cache = None
        if self._batt_cache is None:
            return ""
        return f"🔋 {self._batt_cache}%"

    # ── Robotic stage ────────────────────────────────────────────────────────
    # Layout (matches the reference): neural / mesh / subsystem panels on top,
    # status cards left + right wired into a floating robot core on a glowing
    # platform, and an icon dock at the bottom.

    @staticmethod
    def _rgb(c):
        if isinstance(c, (tuple, list)):
            return int(c[0]), int(c[1]), int(c[2])
        c = c.lstrip("#")
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)

    def _mixc(self, a, b, f):
        ra, ga, ba = self._rgb(a)
        rb, gb, bb = self._rgb(b)
        f = max(0.0, min(1.0, f))
        return "#%02x%02x%02x" % (int(ra + (rb - ra) * f),
                                  int(ga + (gb - ga) * f),
                                  int(ba + (bb - ba) * f))

    def _lit(self, color, f):
        """`color` at intensity f over the background (fake alpha)."""
        return self._mixc(self.col["bg"], color, f)

    def _glow_hex(self):
        rgb = self.col["halo_mut"] if self.muted else self.col["halo"]
        return "#%02x%02x%02x" % tuple(int(v) for v in rgb)

    def _accents(self):
        col = self.col
        return [col["pri"], col["acc"], col["acc2"], col.get("blue", col["mid"])]

    def _rr(self, x0, y0, x1, y1, r=10, **kw):
        r = max(1, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
               x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
               x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.bg.create_polygon(pts, smooth=True, **kw)

    @staticmethod
    def _hexpts(cx, cy, r, rot=0.0):
        pts = []
        for k in range(6):
            a = math.radians(60 * k + rot)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        return pts

    def _stage_layout(self):
        W, H = self.W, self.H
        wide = W >= 980
        sx0 = 228 if wide else 18
        sx1 = W - 238 if wide else W - 18
        top = 90
        bottom = max(top + 260, getattr(self, "_stage_bottom", H - 250))
        sw, sh = sx1 - sx0, bottom - top
        L = {"sx0": sx0, "sx1": sx1, "top": top, "bottom": bottom,
             "sw": sw, "sh": sh, "cx": (sx0 + sx1) / 2}
        ph = max(66, min(128, sh * 0.26))
        dh = max(46, min(68, sh * 0.15))
        gap = 10
        wl = (sw - 2 * gap) * 0.28
        wc = (sw - 2 * gap) * 0.44
        L["ph"], L["dh"] = ph, dh
        L["panels"] = [
            (sx0, top, sx0 + wl, top + ph),
            (sx0 + wl + gap, top, sx0 + wl + gap + wc, top + ph),
            (sx1 - wl, top, sx1, top + ph),
        ]
        L["dock_y0"] = bottom - dh
        my0 = top + ph + 10
        my1 = L["dock_y0"] - 8
        mh = my1 - my0
        R = max(26, min(80, (mh - 54) / 2.75, sw * 0.095))
        used = 2.75 * R + 54
        cy = my0 + max(0, (mh - used) / 2) + 1.1 * R + 4
        L.update(R=R, cy=cy, py=cy + 1.2 * R, ym=(my0 + my1) / 2,
                 mw=max(104, min(170, sw * 0.22)),
                 rowh=max(28, min(44, (mh - 10) / 4.6)))
        return L

    def _card_boxes(self, L):
        mw, rowh, ym = L["mw"], L["rowh"], L["ym"]
        gap = rowh * 0.3

        def column(n, x0):
            total = n * rowh + (n - 1) * gap
            y = ym - total / 2
            return [(x0, y + i * (rowh + gap), x0 + mw, y + i * (rowh + gap) + rowh)
                    for i in range(n)]
        return column(3, L["sx0"]), column(4, L["sx1"] - mw)

    def _net_data(self, key, n, thr, seed, ellipse=False):
        cache = self.__dict__.setdefault("_net_cache", {})
        if key not in cache:
            rng = random.Random(seed)
            pts = []
            for _ in range(6000):
                if len(pts) >= n:
                    break
                u, v = rng.random(), rng.random()
                if ellipse and ((u - .5) / .5) ** 2 + ((v - .5) / .5) ** 2 > 1:
                    continue
                if all((u - p[0]) ** 2 + (v - p[1]) ** 2 > 0.016 for p in pts):
                    pts.append((u, v))
            n = len(pts)
            edges = [(i, j) for i in range(n) for j in range(i + 1, n)
                     if (pts[i][0] - pts[j][0]) ** 2 + (pts[i][1] - pts[j][1]) ** 2 < thr ** 2]
            hub = sorted(range(n), key=lambda i: (pts[i][0] - .5) ** 2 + (pts[i][1] - .5) ** 2)[:6]
            cache[key] = (pts, edges, hub)
        return cache[key]

    def _sys_stats(self):
        now = time.time()
        if getattr(self, "_stats", None) is None or now - self._stats_ts > 1.0:
            self._stats_ts = now
            try:
                psutil = import_module("psutil")
                self._stats = {"cpu": psutil.cpu_percent(interval=None),
                               "mem": psutil.virtual_memory().percent}
            except Exception:
                self._stats = {"cpu": None, "mem": None}
        return self._stats

    def _update_telemetry(self, t):
        if t % 24 == 0:
            for i in range(4):
                self._tele_t[i] = max(0.05, min(1.0, random.uniform(0.1, 0.45)
                                                + self._act * random.uniform(0.2, 0.55)))
        for i in range(4):
            self._tele[i] += (self._tele_t[i] - self._tele[i]) * 0.08

    # ── Main draw ─────────────────────────────────────────────────────────────

    def _draw(self):
        c = self.bg
        W, H, t = self.W, self.H, self.tick
        col = self.col
        c.delete("all")

        target = (1.0 if self.speaking else
                  0.7 if self._state in ("THINKING", "PROCESSING") else
                  0.05 if self.muted else 0.3)
        self._act += (target - self._act) * 0.08
        self._update_telemetry(t)

        acc = self._accents()
        L = self._stage_layout()
        self._dock_rects = []

        for x in range(0, W, 52):
            for y in range(0, H, 52):
                c.create_rectangle(x, y, x + 1, y + 1, fill=col["dimmer"], outline="")

        sy = L["top"] + (t * 1.4) % max(1, L["sh"])
        c.create_line(L["sx0"], sy, L["sx1"], sy, fill=self._lit(col["pri"], 0.10), width=1)

        for box, fn in zip(L["panels"], (self._panel_neural, self._panel_mesh,
                                         self._panel_systems)):
            fn(box, t, acc)

        self._draw_wires(L, t, acc)
        self._draw_platform(L, t)
        self._draw_robot(L, t)
        self._draw_cards(L, t, acc)
        self._draw_dock(L, t, acc)
        self._draw_status(L, t)
        self._draw_chrome(t)

    # ── Top panels ────────────────────────────────────────────────────────────

    def _panel_frame(self, box, title):
        x0, y0, x1, y1 = box
        self._rr(x0, y0, x1, y1, 12, fill=self.col["panel"],
                 outline=self.col["dim"], width=1)
        self.bg.create_text(x0 + 12, y0 + 10, text=title, fill=self.col["mid"],
                            font=("Consolas", 7, "bold"), anchor="w")

    def _panel_neural(self, box, t, acc):
        c, col = self.bg, self.col
        x0, y0, x1, y1 = box
        self._panel_frame(box, self.brand["panels"][0])
        w = x1 - x0
        bx0, by0, bx1, by1 = x0 + 12, y0 + 24, x0 + 12 + w * 0.40, y1 - 10
        pts, edges, _ = self._net_data("brain", 15, 0.36, 5, ellipse=True)
        xy = [(bx0 + u * (bx1 - bx0) + math.sin(t * 0.02 + i * 1.3) * 1.5,
               by0 + v * (by1 - by0) + math.cos(t * 0.017 + i) * 1.5)
              for i, (u, v) in enumerate(pts)]
        for i, j in edges:
            c.create_line(*xy[i], *xy[j], fill=self._lit(col["pri"], 0.28 + 0.25 * self._act))
        for i, (px, py_) in enumerate(xy):
            k = 0.55 + 0.45 * math.sin(t * 0.06 + i)
            r = 1.6 + k
            c.create_oval(px - r, py_ - r, px + r, py_ + r,
                          fill=self._lit(acc[i % 4], 0.5 + 0.5 * k), outline="")
        rx0, rx1 = x0 + w * 0.52, x1 - 12
        rh = (y1 - y0 - 34) / 4
        for i in range(4):
            y = y0 + 28 + rh * i + rh / 2
            a = acc[i % 4]
            c.create_oval(rx0 - 3, y - 3, rx0 + 3, y + 3, fill=a, outline="")
            bs, be = rx0 + 10, rx1 - 22
            c.create_line(bs, y, be, y, fill=self._lit(a, 0.18), width=3, capstyle="round")
            c.create_line(bs, y, bs + (be - bs) * self._tele[i], y, fill=a,
                          width=3, capstyle="round")
            for d in range(3):
                c.create_oval(rx1 - 14 + d * 6 - 1, y - 1, rx1 - 14 + d * 6 + 1, y + 1,
                              fill=self._lit(a, 0.6 if d <= int(self._tele[i] * 3) else 0.2),
                              outline="")

    def _panel_mesh(self, box, t, acc):
        c, col = self.bg, self.col
        x0, y0, x1, y1 = box
        self._panel_frame(box, self.brand["panels"][1])
        pts, edges, hub = self._net_data("mesh", 16, 0.34, 11)
        ix0, iy0, ix1, iy1 = x0 + 14, y0 + 24, x1 - 14, y1 - 10
        xy = [(ix0 + u * (ix1 - ix0) + math.sin(t * 0.021 + i * 1.7) * 2,
               iy0 + v * (iy1 - iy0) + math.cos(t * 0.018 + i * 0.9) * 2)
              for i, (u, v) in enumerate(pts)]
        hx, hy = (x0 + x1) / 2, (iy0 + iy1) / 2
        for i, j in edges:
            c.create_line(*xy[i], *xy[j], fill=self._lit(col["mid"], 0.45))
        for k, i in enumerate(hub):
            c.create_line(*xy[i], hx, hy, fill=self._lit(col["pri"], 0.55))
            ph = (t * (0.006 + 0.012 * self._act) + k * 0.19) % 1.0
            px = xy[i][0] + (hx - xy[i][0]) * ph
            py_ = xy[i][1] + (hy - xy[i][1]) * ph
            c.create_oval(px - 2, py_ - 2, px + 2, py_ + 2, fill=col["pri"], outline="")
        for i, (px, py_) in enumerate(xy):
            a = acc[i % 4]
            k = 0.5 + 0.5 * math.sin(t * 0.05 + i * 0.8)
            c.create_oval(px - 4, py_ - 4, px + 4, py_ + 4, fill=self._lit(a, 0.12 + 0.2 * k),
                          outline="")
            c.create_oval(px - 2.2, py_ - 2.2, px + 2.2, py_ + 2.2, fill=a, outline="")
        hr = min(x1 - x0, y1 - y0) * 0.16
        pulse = 0.5 + 0.5 * math.sin(t * 0.08)
        c.create_oval(hx - hr * 1.5, hy - hr * 1.5, hx + hr * 1.5, hy + hr * 1.5,
                      outline=self._lit(col["pri"], 0.2 + 0.3 * pulse), width=1)
        c.create_polygon(self._hexpts(hx, hy, hr, 30), fill=col["panel"],
                         outline=col["pri"], width=2)
        c.create_polygon(self._hexpts(hx, hy, hr * 0.62, 30),
                         fill=self._lit(col["pri"], 0.35 + 0.3 * self._act),
                         outline=col["pri"], width=1)
        c.create_polygon(self._hexpts(hx, hy, hr * 0.25, 30), fill=col["text"], outline="")

    def _panel_systems(self, box, t, acc):
        c, col = self.bg, self.col
        x0, y0, x1, y1 = box
        self._panel_frame(box, self.brand["panels"][2])
        w, h = x1 - x0, y1 - y0
        pad, g = 9, 6
        tw = (w - 2 * pad - 2 * g) / 3
        th = (h - 24 - pad - g) / 2
        for r in range(2):
            for k in range(3):
                idx = r * 3 + k
                tx0 = x0 + pad + k * (tw + g)
                ty0 = y0 + 24 + r * (th + g)
                a = acc[idx % 4]
                self._rr(tx0, ty0, tx0 + tw, ty0 + th, 6, fill=col["hdr"],
                         outline=self._lit(a, 0.35), width=1)
                c.create_line(tx0 + 6, ty0 + 6, tx0 + 6 + tw * 0.42, ty0 + 6,
                              fill=a, width=2, capstyle="round")
                c.create_oval(tx0 + tw - 9, ty0 + 4, tx0 + tw - 5, ty0 + 8,
                              fill=self._lit(a, 0.5 + 0.5 * math.sin(t * 0.08 + idx)), outline="")
                cols, rows = 5, 3
                ax0, ay0 = tx0 + 7, ty0 + 14
                dx = (tw - 14) / cols
                dy = max(4, (th - 20) / rows)
                for jy in range(rows):
                    for jx in range(cols):
                        v = math.sin(t * 0.05 * (1 + idx * 0.13) + jx * 1.3 + jy * 2.1)
                        on = v > (0.55 - self._act * 0.55)
                        px, py_ = ax0 + jx * dx + dx / 2, ay0 + jy * dy + dy / 2
                        c.create_rectangle(px - 1.2, py_ - 1.2, px + 1.2, py_ + 1.2,
                                           fill=a if on else self._lit(a, 0.18), outline="")

    # ── Wires, platform, robot ────────────────────────────────────────────────

    @staticmethod
    def _wire_points(p0, p1, n=28):
        (x0, y0), (x1, y1) = p0, p1
        dx = (x1 - x0) * 0.55
        pts = []
        for i in range(n + 1):
            u = i / n
            v = 1 - u
            pts.append((v ** 3 * x0 + 3 * v * v * u * (x0 + dx) + 3 * v * u * u * (x1 - dx) + u ** 3 * x1,
                        v ** 3 * y0 + 3 * v * v * u * y0 + 3 * v * u * u * y1 + u ** 3 * y1))
        return pts

    def _draw_wires(self, L, t, acc):
        c, col = self.bg, self.col
        cx, cy, R = L["cx"], L["cy"], L["R"]
        left, right = self._card_boxes(L)
        speed = 0.004 + 0.010 * self._act
        wires = []
        for i, b in enumerate(left):
            wires.append(((b[2], (b[1] + b[3]) / 2), (cx - R * 0.95, cy + (i - 1) * R * 0.22), acc[i % 4], 1))
        for i, b in enumerate(right):
            wires.append(((b[0], (b[1] + b[3]) / 2), (cx + R * 0.95, cy + (i - 1.5) * R * 0.22), acc[i % 4], -1))
        for k, (p0, p1, color, direction) in enumerate(wires):
            pts = self._wire_points(p0, p1)
            c.create_line(*[v for p in pts for v in p], fill=self._lit(color, 0.45),
                          width=1, smooth=True)
            for d in range(2):
                ph = (t * speed + k * 0.173 + d * 0.5) % 1.0
                if direction < 0:
                    ph = 1 - ph
                px, py_ = pts[min(len(pts) - 1, int(ph * len(pts)))]
                c.create_oval(px - 5, py_ - 5, px + 5, py_ + 5, fill=self._lit(color, 0.22), outline="")
                c.create_oval(px - 2, py_ - 2, px + 2, py_ + 2, fill=color, outline="")
        # mesh panel -> head
        ytop, ybot = L["panels"][1][3], cy - R * 1.1
        c.create_line(cx, ytop, cx, ybot, fill=self._lit(col["pri"], 0.5), width=1)
        ph = (t * speed * 1.4) % 1.0
        py_ = ytop + (ybot - ytop) * ph
        c.create_oval(cx - 2, py_ - 2, cx + 2, py_ + 2, fill=col["pri"], outline="")

    def _draw_platform(self, L, t):
        c, col = self.bg, self.col
        cx, py, R = L["cx"], L["py"], L["R"]
        rx, ry = R * 1.95, R * 0.44
        glow = self._glow_hex()
        base = self._mixc(col["hdr"], "#000000", 0.45)
        for dy in range(10, 0, -2):
            c.create_oval(cx - rx, py - ry + dy, cx + rx, py + ry + dy, fill=base, outline="")
        c.create_oval(cx - rx, py - ry, cx + rx, py + ry, fill=col["hdr"],
                      outline=self._lit(glow, 0.75), width=2)
        pulse = 0.55 + 0.30 * math.sin(t * 0.07) + 0.3 * self._act
        for f, w in ((0.88, 3), (0.66, 2), (0.44, 2)):
            a = max(0.15, min(1.0, pulse * (1.1 - f * 0.5)))
            c.create_oval(cx - rx * f, py - ry * f, cx + rx * f, py + ry * f,
                          outline=self._lit(glow, a), width=w)
        for k in range(4, 0, -1):
            f = 0.12 * k
            c.create_oval(cx - rx * f, py - ry * f, cx + rx * f, py + ry * f,
                          fill=self._lit(glow, 0.07 * (5 - k) * (0.5 + self._act)), outline="")
        limit = self.FACE_SZ * 0.72
        for pr in self.pulse_r:
            f = min(1.0, pr / limit)
            a = (1 - f) * (0.25 if self.muted else 0.8)
            c.create_oval(cx - rx * f * 1.05, py - ry * f * 1.05, cx + rx * f * 1.05,
                          py + ry * f * 1.05, outline=self._lit(glow, a), width=1)

    def _draw_robot(self, L, t):
        c, col = self.bg, self.col
        cx, R = L["cx"], L["R"]
        cy = L["cy"] + (0 if self.muted else math.sin(t * 0.05) * R * 0.05)
        glow = self._glow_hex()

        for i, k in enumerate((1.75, 1.5, 1.28)):
            a = max(0.05, min(0.6, self.halo_a / 255 * (0.9 - i * 0.2)))
            c.create_oval(cx - R * k, cy - R * k, cx + R * k, cy + R * k,
                          outline=self._lit(glow, a * 0.8), width=1)
        for idx, (k, w, ext) in enumerate(((1.62, 2, 70), (1.40, 1, 50))):
            r_ = R * k
            for s in range(3):
                c.create_arc(cx - r_, cy - r_, cx + r_, cy + r_,
                             start=(self.rings_spin[idx] + s * 120) % 360, extent=ext,
                             outline=self._lit(glow, 0.8 - idx * 0.25), width=w, style="arc")

        pod = self._mixc(col["hdr"], "#ffffff", 0.10)
        for sgn in (-1, 1):
            ex = cx + sgn * R
            self._rr(ex - R * 0.10, cy - R * 0.24, ex + R * 0.10, cy + R * 0.24, 4,
                     fill=pod, outline=self._lit(glow, 0.8), width=1)
            c.create_line(ex, cy - R * 0.14, ex, cy + R * 0.14, fill=glow, width=2)
        c.create_oval(cx - R * 0.55, cy + R * 0.80, cx + R * 0.55, cy + R * 1.12,
                      fill=self._mixc(col["hdr"], "#000000", 0.3),
                      outline=self._lit(glow, 0.45))

        if self._has_face:
            fw = max(8, int(2 * R * self.scale * self.S))
            cache = getattr(self, "_face_cache2", None)
            if cache is None or cache[0] != fw:
                cache = (fw, ImageTk.PhotoImage(self._face_pil.resize((fw, fw), Image.BILINEAR)))
                self._face_cache2 = cache
            c.create_image(cx, cy, image=cache[1])
            c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=self._lit(glow, 0.9), width=2)
            return

        steps = 16
        for i in range(steps):
            f = i / (steps - 1)
            r = R * (1 - 0.78 * f)
            sh = int(105 + 145 * f)
            color = "#%02x%02x%02x" % (sh - 14, sh - 4, min(255, sh + 6))
            c.create_oval(cx - R * 0.30 * f - r, cy - R * 0.34 * f - r,
                          cx - R * 0.30 * f + r, cy - R * 0.34 * f + r,
                          fill=color, outline="")
        c.create_oval(cx - R, cy - R, cx + R, cy + R, outline=self._lit(glow, 0.9), width=2)

        vy = cy + R * 0.06
        c.create_oval(cx - R * 0.70, vy - R * 0.44, cx + R * 0.70, vy + R * 0.44,
                      fill=self._mixc(col["bg"], "#000000", 0.55),
                      outline=self._lit(glow, 0.35), width=2)

        ew, base_h = R * 0.17, R * 0.25
        if self.muted:
            hh = base_h * 0.30
        elif self.speaking:
            hh = base_h * (0.8 + 0.25 * math.sin(t * 0.45))
        else:
            hh = base_h
        if (t % 220) < 7 and not self.muted:
            hh *= 0.12
        if self._state in ("THINKING", "PROCESSING"):
            look = math.sin(t * 0.07) * R * 0.07
        else:
            look = math.sin(t * 0.013) * R * 0.015
        for sgn in (-1, 1):
            ex = cx + sgn * R * 0.28 + look
            for g, a in ((1.55, 0.18), (1.28, 0.38)):
                c.create_oval(ex - ew * g, vy - hh * g, ex + ew * g, vy + hh * g,
                              fill=self._lit(glow, a), outline="")
            c.create_oval(ex - ew, vy - hh, ex + ew, vy + hh, fill=glow, outline="")
            c.create_oval(ex - ew * 0.45, vy - hh * 0.75, ex + ew * 0.1, vy - hh * 0.2,
                          fill=self._mixc(glow, "#ffffff", 0.65), outline="")
        c.create_oval(cx - R * 0.64, cy - R * 0.88, cx - R * 0.10, cy - R * 0.58,
                      fill="#f4fbfd", outline="")

    # ── Status cards ──────────────────────────────────────────────────────────

    def _card_left(self, box, accent, label, valtxt, value, t):
        c, col = self.bg, self.col
        x0, y0, x1, y1 = box
        h = y1 - y0
        self._rr(x0, y0, x1, y1, 10, fill=col["panel"], outline=self._lit(accent, 0.4), width=1)
        hx, hy = x0 + h * 0.55, (y0 + y1) / 2
        c.create_polygon(self._hexpts(hx, hy, h * 0.30, 0), outline=accent,
                         fill=self._lit(accent, 0.14), width=2)
        c.create_oval(hx - 3, hy - 3, hx + 3, hy + 3, fill=accent, outline="")
        tx = x0 + h * 1.05
        c.create_text(tx, y0 + h * 0.28, text=label, fill=col["text"],
                      font=("Consolas", 7, "bold"), anchor="w")
        c.create_text(x1 - 24, y0 + h * 0.28, text=valtxt, fill=accent,
                      font=("Consolas", 7, "bold"), anchor="e")
        bs, be, by = tx, x1 - 26, y0 + h * 0.68
        c.create_line(bs, by, be, by, fill=self._lit(accent, 0.2), width=4, capstyle="round")
        if value > 0.01:
            c.create_line(bs, by, bs + (be - bs) * min(1.0, value), by, fill=accent,
                          width=4, capstyle="round")
        c.create_oval(x1 - 16, hy - 4, x1 - 8, hy + 4, outline=accent, fill=col["panel"], width=1)
        c.create_oval(x1 - 13, hy - 1, x1 - 11, hy + 1, fill=accent, outline="")

    def _card_right(self, box, accent, label, valtxt, active, t, idx):
        c, col = self.bg, self.col
        x0, y0, x1, y1 = box
        h = y1 - y0
        self._rr(x0, y0, x1, y1, 10, fill=col["panel"],
                 outline=self._lit(accent, 0.4 if active else 0.2), width=1)
        cx_, cy_ = x0 + h * 0.5, (y0 + y1) / 2
        r = h * 0.24
        if active:
            k = 0.5 + 0.5 * math.sin(t * 0.1 + idx)
            c.create_oval(cx_ - r * 1.6, cy_ - r * 1.6, cx_ + r * 1.6, cy_ + r * 1.6,
                          fill=self._lit(accent, 0.12 + 0.12 * k), outline="")
        c.create_oval(cx_ - r, cy_ - r, cx_ + r, cy_ + r,
                      fill=accent if active else self._lit(accent, 0.3), outline="")
        tx = x0 + h * 1.0
        c.create_text(tx, y0 + h * 0.28, text=label, fill=col["text"],
                      font=("Consolas", 7, "bold"), anchor="w")
        c.create_text(x1 - 12, y0 + h * 0.28, text=valtxt, fill=accent,
                      font=("Consolas", 7, "bold"), anchor="e")
        lit_i = (t // 6 + idx) % 5
        for d in range(5):
            if active:
                f = 1.0 if d == lit_i else 0.45
            else:
                f = 0.15
            dx = tx + d * 11
            c.create_oval(dx - 2.5, y0 + h * 0.68 - 2.5, dx + 2.5, y0 + h * 0.68 + 2.5,
                          fill=self._lit(accent, f), outline="")
        c.create_oval(x0 - 3, cy_ - 3, x0 + 3, cy_ + 3, fill=accent, outline="")

    def _draw_cards(self, L, t, acc):
        col = self.col
        left, right = self._card_boxes(L)
        st = self._sys_stats()
        link = (1.0 if self.connected else
                0.5 + 0.4 * math.sin(t * 0.15) if self.connecting else 0.0)
        raw = {"cpu": st["cpu"], "mem": st["mem"]}
        for key, val in raw.items():
            if val is not None:
                self._disp[key] += (val / 100.0 - self._disp[key]) * 0.1
        cpu_txt = "N/A" if st["cpu"] is None else f"{self._disp['cpu'] * 100:.0f}%"
        mem_txt = "N/A" if st["mem"] is None else f"{self._disp['mem'] * 100:.0f}%"
        link_txt = ("ONLINE" if self.connected else
                    "CONNECTING" if self.connecting else "OFFLINE")
        defs = [("CPU", cpu_txt, self._disp["cpu"] if st["cpu"] is not None else 0.0),
                ("MEMORY", mem_txt, self._disp["mem"] if st["mem"] is not None else 0.0),
                ("AI LINK", link_txt, link)]
        for i, (box, (label, txt, val)) in enumerate(zip(left, defs)):
            a = acc[i % 4]
            if label == "AI LINK" and not self.connected and not self.connecting:
                a = col["red"]
            self._card_left(box, a, label, txt, val, t)

        mic_on = not self.muted
        voice_on = not self.silent_mode
        vis_on = self.vision_mode != "STANDBY"
        rdefs = [("MIC", "LIVE" if mic_on else "MUTED", mic_on,
                  col["green"] if mic_on else col["mutcol"]),
                 ("VOICE", "ON" if voice_on else "TEXT", voice_on,
                  acc[2] if voice_on else acc[1]),
                 ("VISION", self.vision_mode[:9], vis_on, acc[3]),
                 ("CORE", str(self.status_text)[:9], True, acc[0])]
        for i, (box, (label, txt, active, a)) in enumerate(zip(right, rdefs)):
            self._card_right(box, a, label, txt, active, t, i)

    # ── Dock ──────────────────────────────────────────────────────────────────

    def _draw_dock(self, L, t, acc):
        c, col = self.bg, self.col
        cx, dh = L["cx"], L["dh"]
        y0, y1 = L["dock_y0"], L["bottom"]
        s = dh * 0.62
        gap = s * 0.45
        n = 4
        total = n * s + (n - 1) * gap
        pad = 16
        self._rr(cx - total / 2 - pad, y0, cx + total / 2 + pad, y1, 12,
                 fill=col["panel"], outline=col["dim"], width=1)
        names = ["TERMINAL", "FILES", "THEME", "BRIEFING"]
        actions = ["terminal", "files", "settings", "clock"]
        hover = getattr(self, "_dock_hover", None)
        for i in range(n):
            bx0 = cx - total / 2 + i * (s + gap)
            by0 = y0 + 6
            bx1, by1 = bx0 + s, by0 + s
            a = acc[i % 4]
            hot = hover == i
            self._rr(bx0, by0, bx1, by1, 8,
                     fill=self._lit(a, 0.22 if hot else 0.08),
                     outline=a if hot else col["dim"], width=1)
            ix, iy, ic = (bx0 + bx1) / 2, (by0 + by1) / 2, s * 0.28
            if i == 0:
                c.create_text(ix, iy, text=">_", fill=a,
                              font=("Consolas", max(8, int(s * 0.36)), "bold"))
            elif i == 1:
                c.create_polygon(ix - ic * 1.1, iy - ic * 0.7, ix - ic * 0.2, iy - ic * 0.7,
                                 ix + ic * 0.1, iy - ic * 0.35, ix + ic * 1.1, iy - ic * 0.35,
                                 ix + ic * 1.1, iy + ic * 0.8, ix - ic * 1.1, iy + ic * 0.8,
                                 outline=a, fill="", width=2)
            elif i == 2:
                rot = t * (1.5 if hot else 0.4)
                c.create_oval(ix - ic * 0.55, iy - ic * 0.55, ix + ic * 0.55, iy + ic * 0.55,
                              outline=a, width=2)
                for k in range(8):
                    ang = math.radians(rot + k * 45)
                    c.create_line(ix + ic * 0.8 * math.cos(ang), iy + ic * 0.8 * math.sin(ang),
                                  ix + ic * 1.15 * math.cos(ang), iy + ic * 1.15 * math.sin(ang),
                                  fill=a, width=3)
            else:
                c.create_oval(ix - ic, iy - ic, ix + ic, iy + ic, outline=a, width=2)
                lt = time.localtime()
                ha = math.radians((lt.tm_hour % 12 + lt.tm_min / 60) * 30 - 90)
                ma = math.radians(lt.tm_min * 6 - 90)
                c.create_line(ix, iy, ix + ic * 0.5 * math.cos(ha), iy + ic * 0.5 * math.sin(ha),
                              fill=a, width=2)
                c.create_line(ix, iy, ix + ic * 0.82 * math.cos(ma), iy + ic * 0.82 * math.sin(ma),
                              fill=a, width=1)
            dy = by1 + (y1 - by1) / 2
            c.create_oval(ix - 2, dy - 2, ix + 2, dy + 2,
                          fill=self._lit(a, 1.0 if hot else 0.7), outline="")
            self._dock_rects.append((bx0, by0, bx1, by1, actions[i]))
            if hot:
                c.create_text(cx, y0 - 9, text=names[i], fill=a,
                              font=("Consolas", 8, "bold"))

    def _dock_hit(self, x, y):
        for i, (x0, y0, x1, y1, _a) in enumerate(getattr(self, "_dock_rects", [])):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return i
        return None

    def _on_stage_motion(self, event):
        i = self._dock_hit(event.x / self.S, event.y / self.S)
        if i != self._dock_hover:
            self._dock_hover = i
            self.bg.configure(cursor="hand2" if i is not None else "")

    def _on_stage_leave(self, event=None):
        self._dock_hover = None
        self.bg.configure(cursor="")

    def _on_stage_click(self, event):
        i = self._dock_hit(event.x / self.S, event.y / self.S)
        if i is None:
            return
        action = self._dock_rects[i][4]
        if action == "terminal":
            self._input_text.focus_set()
        elif action == "settings":
            self.cycle_theme()
        elif action == "files":
            self._send_stage_command("open my recent files")
        elif action == "clock":
            self._send_stage_command("give me my daily briefing")

    def _send_stage_command(self, text):
        self.write_log("SYS: Dock → " + text)
        if self.on_text_command:
            threading.Thread(target=self.on_text_command, args=(text,), daemon=True).start()

    # ── Status line + header / footer ─────────────────────────────────────────

    def _draw_status(self, L, t):
        c, col = self.bg, self.col
        cx = L["cx"]
        sy = L["py"] + L["R"] * 0.44 + 24
        if self.muted:
            stat, sc = "⊘ MUTED", col["mutcol"]
        elif self.speaking:
            stat, sc = "● SPEAKING", col["acc"]
        elif self._state == "THINKING":
            stat, sc = ("◈" if self.status_blink else "◇") + " THINKING", col["acc2"]
        elif self._state == "PROCESSING":
            stat, sc = ("▷" if self.status_blink else "▶") + " PROCESSING", col["acc2"]
        elif self._state == "LISTENING":
            stat, sc = ("●" if self.status_blink else "○") + " LISTENING", col["green"]
        else:
            stat, sc = ("●" if self.status_blink else "○") + f" {self.status_text}", col["pri"]
        c.create_text(cx, sy, text=stat, fill=sc, font=("Segoe UI", 11, "bold"))

        N, BH, bw = 24, 12, 6
        wx0, wy = cx - N * bw / 2, sy + 10
        for i in range(N):
            if self.muted:
                hb, wcol = 2, col["mutcol"]
            elif self.speaking:
                hb = random.randint(2, BH)
                wcol = col["pri"] if hb > BH * 0.6 else col["mid"]
            else:
                hb, wcol = int(3 + 2 * math.sin(t * 0.08 + i * 0.55)), col["dim"]
            bx = wx0 + i * bw
            c.create_rectangle(bx, wy + BH - hb, bx + bw - 1, wy + BH, fill=wcol, outline="")

    def _draw_chrome(self, t):
        c, col, B = self.bg, self.col, self.brand
        W, H = self.W, self.H
        HDR = 78
        c.create_rectangle(0, 0, W, HDR, fill=col["hdr"], outline="")
        c.create_line(0, HDR, W, HDR, fill=col["mid"], width=1)
        c.create_rectangle(0, HDR - 2, min(W, 260), HDR, fill=col["pri"], outline="")

        # brand block: logo (or emblem) + company + division + persona
        x = 16
        if self._logo is not None:
            if B.get("logo_plate", True):
                self._rr(x - 5, 7, x + self._logo_w + 5, 55, 8, fill="#F4F4F4", outline="")
            c.create_image(x, 11, image=self._logo, anchor="nw")
            x += self._logo_w + 16
        else:
            c.create_polygon(self._hexpts(x + 18, 31, 18, 0), outline=col["pri"],
                             fill=self._lit(col["pri"], 0.16), width=2)
            c.create_polygon(self._hexpts(x + 18, 31, 9, 0), fill=col["pri"], outline="")
            x += 48
        c.create_text(x, 22, text=B["company"], fill=col["text"],
                      font=("Segoe UI", 13, "bold"), anchor="w")
        if W >= 940:
            c.create_text(x, 41, text=B["division"], fill=col["mid"],
                          font=("Segoe UI", 8), anchor="w")
        badge = (f"\u25c8 {self.persona_mode.upper()} \u00b7 "
                 f"{self.persona_mood.upper()} \u00b7 {self.persona_voice}")
        c.create_text(x, 60, text=badge, fill=col["acc2"],
                      font=("Segoe UI", 8, "bold"), anchor="w")

        # product title
        c.create_text(W // 2, 26, text=B["product"], fill=col["pri"],
                      font=("Segoe UI", 18, "bold"))
        c.create_text(W // 2, 48, text=B["tagline"], fill=col["mid"],
                      font=("Segoe UI", 8))

        c.create_text(W - 16, 20, text=time.strftime("%H:%M:%S"), fill=col["pri"],
                      font=("Segoe UI", 12, "bold"), anchor="e")
        c.create_text(W - 16, 40, text=time.strftime("%a %d %b %Y").upper(), fill=col["mid"],
                      font=("Segoe UI", 8), anchor="e")
        if self.connecting:
            conn_txt, conn_col = "\u25cc CONNECTING", col["acc"]
        elif self.connected:
            conn_txt, conn_col = "\u25cf ONLINE", col["green"]
        else:
            conn_txt, conn_col = "\u25cb OFFLINE", col["red"]
        c.create_text(W - 16, 60, text=conn_txt, fill=conn_col,
                      font=("Segoe UI", 8, "bold"), anchor="e")

        # footer
        c.create_rectangle(0, H - 38, W, H, fill=col["hdr"], outline="")
        c.create_line(0, H - 38, W, H - 38, fill=col["dim"], width=1)
        if self.last_event:
            ev = self.last_event if len(self.last_event) <= 72 else self.last_event[:69] + "..."
            c.create_text(W // 2, H - 26, text=ev, fill=col["mid"],
                          font=("Segoe UI", 8), anchor="center")
        if W >= 860:
            c.create_text(W // 2, H - 11, text=B["footer"], fill=col["dim"],
                          font=("Segoe UI", 7), anchor="center")
        batt = self._battery_text()
        hints = "  ".join(x_ for x_ in [batt, "[F4] MUTE", "[F5] THEME: " + THEMES[self._theme]["name"],
                                        "[F6] TEXT-ONLY", "[F11] FULLSCREEN"] if x_)
        c.create_text(W - 16, H - 14, text=hints, fill=col["dim"],
                      font=("Segoe UI", 8), anchor="e")

    # ── Log ───────────────────────────────────────────────────────────────────

    def write_log(self, text: str):
        self._safe_ui(self._write_log, text)

    def _brand_text(self, text: str) -> str:
        """Show the configured product name wherever main.py says 'Kaizumi'."""
        import re
        name = str(self.brand.get("product") or "GHOST")
        return re.sub(r"kaizumi", name, text, flags=re.I)

    def _write_log(self, text: str):
        text = self._brand_text(text)
        self.typing_queue.append(text)
        stripped = text
        for prefix in ("[Guardian]", "[Monitor]", "[Email]", "⏰", "SYS:"):
            if text.startswith(prefix):
                stripped = text[len(prefix):].strip(" :")
                break
        self.last_event = stripped or self.last_event
        tl = text.lower()
        if tl.startswith("you:"):
            self.set_state("PROCESSING")
        elif tl.startswith("ghost:") or tl.startswith("ai:"):
            self.set_state("SPEAKING")
        if not self.is_typing:
            self._start_typing()

    def _start_typing(self):
        if not self.typing_queue:
            self.is_typing = False
            if not self.speaking and not self.muted:
                self.set_state("LISTENING")
            return
        self.is_typing = True
        text = self.typing_queue.popleft()
        tl   = text.lower()
        if tl.startswith("you:"):
            kind, body = "you", text[4:].strip()
        elif tl.startswith("ghost:"):
            kind, body = "ai", text[6:].strip()
        elif tl.startswith("ai:"):
            kind, body = "ai", text[3:].strip()
        elif tl.startswith("err:"):
            kind, body = "err", text[4:].strip()
        elif "error" in tl or "failed" in tl:
            kind, body = "err", text
        elif tl.startswith("sys:"):
            kind, body = "sys", text[4:].strip()
        else:
            kind, body = "sys", text
        for _pre in ("sys:", "err:"):
            if body.lower().startswith(_pre):
                body = body[len(_pre):].strip()
        label = {"you": "YOU", "ai": str(self.brand.get("product") or "GHOST").upper()[:8],
                 "sys": "SYS", "err": "ERR"}[kind]
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, time.strftime("%H:%M") + "  ", "ts")
        self.log_text.insert(tk.END, label, "lbl_" + kind)
        self.log_text.insert(tk.END, "\t", kind)
        self._type_char(body, 0, kind)

    def _type_char(self, text, i, tag):
        if i < len(text):
            self.log_text.insert(tk.END, text[i], tag)
            self.log_text.see(tk.END)
            self.root.after(8, self._type_char, text, i + 1, tag)
        else:
            self.log_text.insert(tk.END, "\n")
            self.log_text.configure(state="disabled")
            self.root.after(25, self._start_typing)

    # ── Legacy compat methods (main.py may still call them) ──────────────────

    def start_speaking(self):
        self.set_state("SPEAKING")

    def stop_speaking(self):
        if not self.muted and not self.silent_mode:
            self.set_state("LISTENING")

    # ── API key ───────────────────────────────────────────────────────────────

    def _api_keys_exist(self):
        """A usable Gemini key must exist (env or config), not just the file."""
        if os.environ.get("GHOST_GEMINI_API_KEY", "").strip():
            return True
        if os.environ.get("GHOST_GEMINI_API_KEYS", "").strip():
            return True
        try:
            cfg = json.loads(API_FILE.read_text(encoding="utf-8"))
        except Exception:
            return False
        if isinstance(cfg.get("gemini_api_key"), str) and cfg["gemini_api_key"].strip():
            return True
        keys = cfg.get("gemini_api_keys")
        return bool(isinstance(keys, list) and
                    any(isinstance(k, str) and k.strip() for k in keys))

    def wait_for_api_key(self):
        while not self._api_key_ready:
            time.sleep(0.1)

    def _show_setup_ui(self):
        self.setup_frame = tk.Frame(
            self.root, bg=THEMES[self._theme]["hdr"],
            highlightbackground=THEMES[self._theme]["pri"], highlightthickness=px(1)
        )
        self._pl(self.setup_frame, relx=0.5, rely=0.5, anchor="center")

        tk.Label(self.setup_frame, text="◈  INITIALISATION REQUIRED",
                 fg=THEMES[self._theme]["pri"], bg=THEMES[self._theme]["hdr"],
                 font=("Segoe UI", 13, "bold")).pack(pady=px((18, 4)))
        tk.Label(self.setup_frame,
                 text="Enter your Gemini API key to boot GHOST.",
                 fg=THEMES[self._theme]["mid"], bg=THEMES[self._theme]["hdr"],
                 font=("Segoe UI", 9)).pack(pady=px((0, 10)))

        tk.Label(self.setup_frame, text="GEMINI API KEY",
                 fg=THEMES[self._theme]["dim"], bg=THEMES[self._theme]["hdr"],
                 font=("Segoe UI", 9)).pack(pady=px((8, 2)))
        self.gemini_entry = tk.Entry(
            self.setup_frame, width=52, fg=THEMES[self._theme]["text"],
            bg=THEMES[self._theme]["input"],
            insertbackground=THEMES[self._theme]["text"], borderwidth=0,
            font=("Segoe UI", 10), show="*"
        )
        self.gemini_entry.pack(pady=px((0, 4)), ipady=px(7))
        self.gemini_entry.bind("<Return>", lambda event: self._save_api_keys())

        tk.Button(
            self.setup_frame, text="▸  INITIALISE SYSTEMS",
            command=self._save_api_keys, bg=THEMES[self._theme]["bg"],
            fg=THEMES[self._theme]["pri"],
            activebackground=THEMES[self._theme]["mid"], font=("Segoe UI", 10),
            borderwidth=0, pady=px(8), cursor="hand2",
            activeforeground=THEMES[self._theme]["text"]
        ).pack(pady=px((12, 18)), padx=px(18), fill="x")

    def _save_api_keys(self):
        gemini = self.gemini_entry.get().strip()
        if not gemini:
            return
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(API_FILE, "w", encoding="utf-8") as f:
            json.dump({"gemini_api_key": gemini}, f, indent=4)
        self.setup_frame.destroy()
        self._api_key_ready = True
        self.set_state("LISTENING")
        self.write_log("SYS: Systems initialised. GHOST online.")


# main.py imports the UI under this name
KaizumiUI = GHOSTUI
