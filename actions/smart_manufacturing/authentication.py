import requests
import urllib3

from bs4 import BeautifulSoup
from urllib.parse import urljoin


class SmartManufacturingAuth:

    def __init__(self, config):

        self.config = config

        self.session = requests.Session()

        self.session.verify = config.verify_ssl

        self.session.headers.update({
            "User-Agent": "Ghost Smart Manufacturing Integration",
            "Accept": "text/html,application/json,*/*"
        })

        if not config.verify_ssl:
            urllib3.disable_warnings(
                urllib3.exceptions.InsecureRequestWarning
            )

    def get_antiforgery_token(self):

        url = urljoin(
            self.config.base_url.rstrip("/") + "/",
            self.config.login_page.lstrip("/")
        )

        response = self.session.get(
            url,
            timeout=self.config.timeout
        )

        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        token = soup.find(
            "input",
            {"name": "__RequestVerificationToken"}
        )

        if token is None or not token.get("value"):
            raise Exception(
                "Antiforgery token not found on login page."
            )

        return token["value"]

    def login(self):

        if not self.config.staff_id or not self.config.password:
            raise ValueError(
                "Staff ID or password is missing from .env"
            )

        print("Opening Smart Manufacturing login page...")

        token = self.get_antiforgery_token()

        login_url = urljoin(
            self.config.base_url.rstrip("/") + "/",
            self.config.login_endpoint.lstrip("/")
        )

        payload = {
            "StaffId": self.config.staff_id,
            "Password": self.config.password,
            "__RequestVerificationToken": token
        }

        headers = {
            "Referer": urljoin(
                self.config.base_url.rstrip("/") + "/",
                self.config.login_page.lstrip("/")
            ),
            "Origin": self.config.base_url.rstrip("/")
        }

        print("Submitting login request...")

        response = self.session.post(
            login_url,
            data=payload,
            headers=headers,
            timeout=self.config.timeout,
            allow_redirects=True
        )

        print("Login HTTP Status:", response.status_code)
        print("Login final URL:", response.url)

        if response.status_code != 200:
            raise Exception(
                f"Login failed with HTTP {response.status_code}"
            )

        if "/Login/SignIn" in response.url:
            raise Exception(
                "Login may have failed. Check credentials or validation."
            )

        cookie_names = [
            cookie.name for cookie in self.session.cookies
        ]

        print("Session cookie names:", cookie_names)

        if not cookie_names:
            raise Exception(
                "No session cookies received after login."
            )

        print("Login request completed.")

        return True

    def close(self):
        self.session.close()