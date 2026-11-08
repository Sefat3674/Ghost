from actions.smart_manufacturing.config import SmartManufacturingConfig
from actions.smart_manufacturing.authentication import SmartManufacturingAuth


def main():

    config = SmartManufacturingConfig()
    auth = SmartManufacturingAuth(config)

    try:
        print("=" * 55)
        print("MACHINE AUDIT REPORT TEST")
        print("=" * 55)

        # 1. Login
        auth.login()

        # 2. Prepare report request
        url = (
            f"{config.base_url.rstrip('/')}"
            "/MachineAuditReport/getMachineAuditReport"
        )

        params = {
            "MotherCompanyId": 1,
            "gridType": "detail"
        }

        print("\nRequesting Machine Audit Report...")
        print("Mother Company ID: 1 (PRAN)")
        print("Report Type: Detail")

        # 3. POST using authenticated session
        response = auth.session.post(
            url,
            params=params,
            timeout=60
        )

        print("HTTP Status:", response.status_code)

        response.raise_for_status()

        result = response.json()

        if not result.get("success"):
            print("Report API returned success=false")
            print(result)
            return

        records = result.get("data", [])

        if not isinstance(records, list):
            print("Unexpected report data format.")
            return

        print("\nReport request successful!")
        print("Total report records:", len(records))

        if records:
            print("\nFirst report record fields:")

            for key, value in records[0].items():
                print(f"{key}: {value}")

        else:
            print("No report records found for this filter.")

    except Exception as error:
        print("\nREPORT TEST FAILED:", str(error))

    finally:
        auth.close()


if __name__ == "__main__":
    main()