"""Quick local checks for GHOST-Akkhor wiring (does not call live API)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from actions.akkhor.service import AkkhorService


def main():
    service = AkkhorService(ROOT)
    print("GHOST + AKKHOR LOCAL CHECK")
    print("Base URL:", service.config["base_url"])
    print("Configured resources:", ", ".join(service.config["endpoints"].keys()))
    print("Authenticated:", service.auth.is_authenticated())
    print("[OK] Integration modules imported successfully.")
    print("Next: launch GHOST, open AKKHOR SCHOOL, and sign in through the panel.")


if __name__ == "__main__":
    main()
