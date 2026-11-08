
from actions.smart_manufacturing.config import SmartManufacturingConfig
from actions.smart_manufacturing.authentication import SmartManufacturingAuth
from actions.smart_manufacturing.client import SmartManufacturingClient


def get_value(record, *keys, default=""):
    """Read dictionary values without depending on key casing."""
    if not isinstance(record, dict):
        return default

    for key in keys:
        for actual_key, value in record.items():
            if actual_key.lower() == key.lower():
                return value

    return default


def main():
    print("=" * 60)
    print("SMART MANUFACTURING LOOKUP API TEST")
    print("=" * 60)

    config = SmartManufacturingConfig()
    auth = SmartManufacturingAuth(config)

    try:
        # Step 1: Authenticate
        print("\nStep 1: Authenticating...")

        auth.login()

        print("Login successful!")
        print("Authenticated session established.")

        # Step 2: Create client using authenticated session
        client = SmartManufacturingClient(config, auth)

        # Step 3: Test lookup APIs
        endpoints = [
            ("Mother Companies", client.get_mother_companies),
            ("Business Units", client.get_business_units),
            ("Locations", client.get_locations),
            ("Sections", client.get_sections),
        ]

        print("\nStep 2: Testing Lookup APIs")
        print("=" * 60)

        for title, api_method in endpoints:
            print(f"\nTesting: {title}")
            print("-" * 45)

            try:
                records = api_method()

                print("HTTP Status: 200")
                print("Total records:", len(records))

                for item in records[:5]:
                    record_id = get_value(item, "id", "Id")
                    name = get_value(item, "name", "Name")
                    full_name = get_value(
                        item, "fullName", "FullName"
                    )

                    print(
                        f"ID: {record_id} | "
                        f"Name: {name} | "
                        f"Full Name: {full_name}"
                    )

                if len(records) > 5:
                    print(
                        f"... and {len(records) - 5} more records"
                    )

            except Exception as error:
                print("API request failed:", str(error))

        print("\n" + "=" * 60)
        print("LOOKUP API TESTING COMPLETED")
        print("=" * 60)

    except Exception as error:
        print("\nAuthentication or setup failed:")
        print(str(error))

    finally:
        auth.close()
        print("\nSession closed.")


if __name__ == "__main__":
    main()
