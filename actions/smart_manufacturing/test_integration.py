
from actions.smart_manufacturing import GhostSmartManufacturing


def main():

    ghost_sm = GhostSmartManufacturing()

    try:

        print("=" * 50)
        print("GHOST SMART MANUFACTURING TEST")
        print("=" * 50)

        # 1. Authentication
        print("\n[1] Connecting...")

        ghost_sm.connect()

        print("Login successful!")

        # 2. Lookup API tests
        print("\n[2] Testing lookup APIs...")

        companies = ghost_sm.client.get_mother_companies()
        business_units = ghost_sm.client.get_business_units()
        locations = ghost_sm.client.get_locations()
        sections = ghost_sm.client.get_sections()

        print("Mother Companies:", len(companies))
        print("Business Units:", len(business_units))
        print("Locations:", len(locations))
        print("Sections:", len(sections))

        # 3. Test company resolution
        print("\n[3] Resolving PRAN...")

        pran = ghost_sm.lookup.mother_company("PRAN")

        print("PRAN ID:", pran["id"])

        # 4. Test report API
        print("\n[4] Fetching Machine Audit Report...")

        records = ghost_sm.reports.get_report(
            company="PRAN",
            grid_type="detail"
        )

        print("Total records:", len(records))

        # Inspect the first returned record.
        if records:
            print("\nFirst record:")
            print(records[0])

        # 5. Test calculations
        print("\n[5] Machine summary...")

        summary = ghost_sm.reports.calculate_summary(
            records
        )

        print(
            ghost_sm.reports.format_summary(summary)
        )

        # 6. Test voice commands
        print("\n[6] Testing voice commands...")

        commands = [
            "How many machines in PRAN?",
            "How many smart machines in PRAN?",
            "How many manual machines in PRAN?",
            "Give me the machine summary of PRAN."
        ]

        for command in commands:

            print("\nGhost heard:", command)

            answer = ghost_sm.ask(command)

            print("Ghost:", answer)

    except Exception as error:

        print("\nINTEGRATION ERROR:")
        print(type(error).__name__, str(error))

    finally:

        ghost_sm.close()


if __name__ == "__main__":
    main()
