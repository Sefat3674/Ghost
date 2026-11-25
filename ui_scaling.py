"""DPI-aware coordinate helpers and canvas for the desktop UI."""

import os
import tkinter as tk


_S = 1.0


def set_ui_scale(scale: float) -> None:
    global _S
    _S = float(scale)


def px(value):
    """Convert logical units to pixels, recursively accepting tuples/lists."""
    if isinstance(value, (tuple, list)):
        return tuple(px(item) for item in value)
    return int(round(value * _S)) if value else 0


def pick_scale(sw, sh, dpi):
    env = os.environ.get("GHOST_UI_SCALE")
    if env:
        try:
            return max(0.75, min(float(env), 4.0))
        except ValueError:
            pass
    scale = max(min(sw / 1920.0, sh / 1080.0), dpi / 96.0, 1.0)
    scale = min(scale, 3.0)
    while scale > 1.0 and sh / scale < 720:
        scale -= 0.25
    return round(scale * 4) / 4.0


class HiDPICanvas(tk.Canvas):
    """Canvas that scales coordinates and line widths from logical units."""

    def __init__(self, master, scale=1.0, **kwargs):
        self._k = float(scale)
        super().__init__(master, **kwargs)

    def _scaled(self, args):
        scale, output = self._k, []
        for value in args:
            if isinstance(value, (int, float)):
                output.append(value * scale)
            elif isinstance(value, (list, tuple)):
                output.extend(item * scale for item in value)
            else:
                output.append(value)
        return output


def _wrap_create(kind):
    base = getattr(tk.Canvas, "create_" + kind)

    def create(self, *args, **kwargs):
        if self._k != 1.0:
            args = self._scaled(args)
            width = kwargs.get("width")
            if isinstance(width, (int, float)) and width:
                kwargs["width"] = (
                    width * self._k if kind == "text"
                    else max(1, int(round(width * self._k)))
                )
        return base(self, *args, **kwargs)

    return create


for _kind in ("line", "oval", "rectangle", "polygon", "arc", "text", "image"):
    setattr(HiDPICanvas, "create_" + _kind, _wrap_create(_kind))
