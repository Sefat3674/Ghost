
import traceback
import base64
import json

from outlook.auth.microsoft_auth import MicrosoftAuth
from outlook.services.graph_client import GraphClient
from outlook.services.email_service import EmailService


def inspect_token(token):
    """Display selected JWT claims without revealing the token."""

    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)

        claims = json.loads(
            base64.urlsafe_b64decode(payload)
        )

        print("\n========== TOKEN DIAGNOSTICS ==========")
        print("Audience:", claims.get("aud"))
        print("Granted scopes:", claims.get("scp"))
        print("Tenant:", claims.get("tid"))
        print("Issuer:", claims.get("iss"))
        print("=======================================\n")

    except Exception as error:
        print("Could not inspect token claims:", repr(error))


def main():

    print("\n====================================")
    print("       GHOST OUTLOOK AGENT")
    print("====================================\n")

    try:
        # Step 1: Initialize authentication
        print("[1] Initializing Microsoft authentication...")

        auth = MicrosoftAuth()

        # Step 2: Check existing authentication
        print("[2] Checking authentication...")

        token = auth.get_access_token()

        # Step 3: Microsoft login if required
        if not token:

            print("[3] Opening Microsoft login...")

            result = auth.login()

            if not result or "access_token" not in result:
                raise Exception(
                    "Microsoft login did not return an access token."
                )

            token = result["access_token"]

        print("\n[SUCCESS] Microsoft authentication completed!")

        # Step 4: Inspect token claims
        print("\n[4] Inspecting token permissions...")

        inspect_token(token)

        # Step 5: Connect Microsoft Graph
        print("[5] Connecting to Microsoft Graph...")

        graph = GraphClient(token)

        # Step 6: Get Microsoft profile
        print("\n[6] Loading Outlook profile...")

        profile = graph.get_profile()

        print("\nAccount Information")
        print("-------------------")

        print("Name:", profile.get("displayName"))

        print(
            "Email:",
            profile.get("mail") or profile.get("userPrincipalName")
        )

        # Step 7: Get latest emails
        email_service = EmailService(graph)

        print("\n[7] Fetching latest 10 emails...")

        emails = email_service.get_latest_emails(10)

        print("\nLatest Outlook Messages")
        print("=======================\n")

        if not emails:
            print("No emails found in this mailbox.")

        for index, email in enumerate(emails, start=1):

            print(f"Email #{index}")
            print("-" * 50)

            print("Subject:", email.get("subject"))
            print("From:", email.get("sender_name"))
            print("Email:", email.get("sender_email"))
            print("Received:", email.get("received_at"))
            print("Read:", email.get("is_read"))

            print("\nPreview:")
            print(email.get("preview") or "No preview available.")

            print("\n")

        print("====================================")
        print("[SUCCESS] Ghost Outlook is connected!")
        print("====================================")

    except Exception as error:

        print("\n====================================")
        print("[ERROR] Ghost Outlook failed!")
        print("====================================")

        print("Error Type:", type(error).__name__)
        print("Error Details:", repr(error))

        print("\nFull Error Traceback:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
