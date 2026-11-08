import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SmartManufacturingConfig:
    base_url: str = os.getenv(
        "SM_BASE_URL",
        "https://localhost:7115"
    )

    staff_id: str = os.getenv("SM_STAFF_ID", "")
    password: str = os.getenv("SM_PASSWORD", "")

    login_page: str = os.getenv("SM_LOGIN_PAGE", "/")
    login_endpoint: str = os.getenv(
        "SM_LOGIN_ENDPOINT",
        "/Login/SignIn"
    )

    report_endpoint: str = (
        "/MachineAuditReport/getMachineAuditReport"
    )

    timeout: int = 30

    verify_ssl: bool = (
        os.getenv("SM_VERIFY_SSL", "false").lower() == "true"
    )