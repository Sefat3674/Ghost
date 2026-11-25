"""Theme and branding data loading for the desktop UI."""

import json
from pathlib import Path


THEMES = {
    "pran": {
        "name": "PRAN-RFL",
        "bg": "#0A0708", "pri": "#FF4D45", "mid": "#B8504A",
        "dim": "#4A2E32", "dimmer": "#1B1213",
        "acc": "#FFB020", "acc2": "#4ADE80", "blue": "#4DA3FF",
        "text": "#FFEDEA", "panel": "#150F11",
        "green": "#4ADE80", "red": "#FF4D45", "mutcol": "#8A8F98",
        "hdr": "#100B0C", "input": "#1B1315", "inp_border": "#3A2629",
        "halo": (255, 86, 72), "halo_mut": (138, 143, 152),
        "orb": (140, 40, 34), "scan2": (255, 176, 32),
    },
    "robo": {
        "name": "ROBO",
        "bg": "#07090C", "pri": "#2EE6D0", "mid": "#1B8F86",
        "dim": "#2B3A40", "dimmer": "#10171B",
        "acc": "#F2C94C", "acc2": "#7ED957", "blue": "#3FA9F5",
        "text": "#D6F5F0", "panel": "#0F1519",
        "green": "#7ED957", "red": "#FF5C6C", "mutcol": "#FF5C6C",
        "hdr": "#0A0E11", "input": "#121B20", "inp_border": "#2B3A40",
        "halo": (46, 230, 208), "halo_mut": (255, 92, 108),
        "orb": (20, 120, 110), "scan2": (242, 201, 76),
    },
    "cyber": {
        "name": "CYBER",
        "bg": "#050B14", "pri": "#35D6E8", "mid": "#167D91",
        "dim": "#24485A", "dimmer": "#102334",
        "acc": "#FF8A4C", "acc2": "#F7C96B",
        "text": "#D7F7FA", "panel": "#0A1725",
        "green": "#55D6A5", "red": "#FF657A", "mutcol": "#FF648A",
        "hdr": "#081321", "input": "#0D1E2D", "inp_border": "#24485A",
        "halo": (53, 214, 232), "halo_mut": (255, 100, 138),
        "orb": (12, 100, 132), "scan2": (255, 138, 76),
    },
    "ocean": {
        "name": "OCEAN",
        "bg": "#06111C", "pri": "#66C9F2", "mid": "#287FA0",
        "dim": "#254A62", "dimmer": "#10283A",
        "acc": "#F6A66D", "acc2": "#F4D27C",
        "text": "#D8F1FC", "panel": "#0B1C2B",
        "green": "#6AD6A4", "red": "#FF7D86", "mutcol": "#F77D9C",
        "hdr": "#091827", "input": "#102538", "inp_border": "#28516A",
        "halo": (102, 201, 242), "halo_mut": (247, 125, 156),
        "orb": (12, 92, 145), "scan2": (246, 166, 109),
    },
    "aurora": {
        "name": "AURORA",
        "bg": "#06130F", "pri": "#65DDA0", "mid": "#27845A",
        "dim": "#285B43", "dimmer": "#102B20",
        "acc": "#EBCB72", "acc2": "#F3D98A",
        "text": "#DDF7E8", "panel": "#0B1E16",
        "green": "#65DDA0", "red": "#FF7D86", "mutcol": "#F77D9C",
        "hdr": "#091A13", "input": "#10271C", "inp_border": "#285B43",
        "halo": (101, 221, 160), "halo_mut": (247, 125, 156),
        "orb": (10, 100, 60), "scan2": (235, 203, 114),
    },
    "sunset": {
        "name": "SUNSET",
        "bg": "#160D12", "pri": "#FFB16F", "mid": "#A65D43",
        "dim": "#654033", "dimmer": "#2D1C20",
        "acc": "#F18DB4", "acc2": "#F4D58A",
        "text": "#FFE7D6", "panel": "#21131A",
        "green": "#77D6A5", "red": "#FF7D86", "mutcol": "#F77D9C",
        "hdr": "#1B1017", "input": "#2A1820", "inp_border": "#654033",
        "halo": (255, 177, 111), "halo_mut": (247, 125, 156),
        "orb": (140, 68, 38), "scan2": (244, 213, 138),
    },
}

DEFAULT_BRAND = {
    "company": "PRAN-RFL GROUP",
    "division": "Smart Manufacturing & Factory Automation",
    "product": "GHOST",
    "tagline": "Industrial Intelligence Assistant",
    "footer": "PRAN-RFL Group  \u00b7  Smart Manufacturing & IBS ERP",
    "logo": "assets/pran_rfl_logo.png",
    "logo_plate": True,
    "panels": ["AI CORE", "PLANT NETWORK", "FACTORY UNITS"],
}


def load_theme_name(theme_file: Path, themes=None) -> str:
    theme_options = THEMES if themes is None else themes
    try:
        if theme_file.exists():
            data = json.loads(theme_file.read_text(encoding="utf-8"))
            name = str(data.get("theme", "pran")).strip()
            if name in theme_options:
                return name
    except Exception:
        pass
    return "pran"


def save_theme_name(name: str, config_dir: Path, theme_file: Path) -> None:
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        theme_file.write_text(
            json.dumps({"theme": name}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def load_brand(brand_file: Path, defaults=None) -> dict:
    default_brand = DEFAULT_BRAND if defaults is None else defaults
    brand = dict(default_brand)
    try:
        if brand_file.exists():
            data = json.loads(brand_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in brand:
                    if key in data and data[key] not in (None, ""):
                        brand[key] = data[key]
    except Exception:
        pass
    if not (isinstance(brand["panels"], list) and len(brand["panels"]) >= 3):
        brand["panels"] = list(default_brand["panels"])
    return brand
