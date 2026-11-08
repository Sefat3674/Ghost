from actions.smart_manufacturing.config import (
    SmartManufacturingConfig
)

from actions.smart_manufacturing.authentication import (
    SmartManufacturingAuth
)


def main():

    config = SmartManufacturingConfig()

    auth = SmartManufacturingAuth(config)

    try:

        print("=" * 55)
        print("GHOST SMART MANUFACTURING AUTHENTICATION TEST")
        print("=" * 55)

        auth.login()

        print("\nTesting protected Location API...")

        response = auth.session.get(
            f"{config.base_url.rstrip('/')}/location/getall",
            timeout=config.timeout
        )

        print("Location HTTP Status:", response.status_code)

        if response.status_code == 200:

            result = response.json()

            locations = result.get(
                "Data",
                result.get("data", [])
            )

            print("Location API accessible.")
            print("Locations returned:", len(locations))

            for location in locations[:5]:
                print(
                    location.get("Id", location.get("id")),
                    "-",
                    location.get("Name", location.get("name"))
                )

        else:

            print("Location API response:")
            print(response.text[:1000])

    except Exception as error:

        print("\nTEST FAILED:", str(error))

    finally:

        auth.close()


if __name__ == "__main__":
    main()