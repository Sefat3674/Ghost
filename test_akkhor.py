import requests
import urllib3
from getpass import getpass

urllib3.disable_warnings()

BASE_URL = "https://localhost:50268"

email = input("Akkhor Email: ")
password = getpass("Akkhor Password: ")

session = requests.Session()
session.verify = False

try:
    response = session.post(
        f"{BASE_URL}/api/Auth/login",
        json={"email": email, "password": password},
        timeout=30
    )

    print("\nLogin status:", response.status_code)

    if not response.ok:
        print("Login failed:", response.text)
        raise SystemExit(1)

    data = response.json()
    token = data.get("token") or data.get("accessToken")

    if not token:
        print("Login response fields:", list(data.keys()))
        raise SystemExit("Token not found in login response")

    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    })

    result = session.get(
        f"{BASE_URL}/api/student-enrollments/classes",
        timeout=30
    )

    print("Classes API status:", result.status_code)

    if result.ok:
        print("\nSUCCESS: GHOST connected to AKKHOR!")
        print(result.text[:3000])
    else:
        print("API error:", result.text)

except requests.RequestException as error:
    print("Connection error:", error)
