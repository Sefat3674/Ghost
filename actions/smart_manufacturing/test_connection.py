import os
import requests
import urllib3
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("SM_BASE_URL", "").rstrip("/")
VERIFY_SSL = os.getenv("SM_VERIFY_SSL", "false").lower() == "true"

if not BASE_URL:
    raise ValueError("SM_BASE_URL is missing from .env")

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

session = requests.Session()
session.verify = VERIFY_SSL

url = f"{BASE_URL}/mothercompany/getall"

print("Testing Smart Manufacturing connection...")
print("Server:", BASE_URL)

try:
    response = session.get(url, timeout=15, allow_redirects=True)

    print("HTTP Status:", response.status_code)
    print("Final URL:", response.url)

    if response.status_code == 200:
        try:
            result = response.json()
            print("JSON response received.")

            companies = result.get("data", [])
            print("Mother companies returned:", len(companies))

            for company in companies[:5]:
                print("-", company.get("name"))

        except ValueError:
            print("Server responded, but the response was not JSON.")
            print(response.text[:300])

    elif response.status_code in (401, 403):
        print("Server is reachable, but authentication is required.")

    elif response.status_code in (301, 302):
        print("Server redirected the request. Login may be required.")

    else:
        print("Unexpected response:")
        print(response.text[:300])

except requests.exceptions.SSLError:
    print("SSL certificate error. Check SM_VERIFY_SSL in .env.")

except requests.exceptions.ConnectionError:
    print("Could not connect. Check whether Smart Manufacturing is running.")

except requests.exceptions.Timeout:
    print("Connection timed out.")

except requests.exceptions.RequestException as error:
    print("Request error:", error)