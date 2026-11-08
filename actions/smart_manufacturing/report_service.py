
class MachineAuditReportService:

    METRICS = {
        "total_machines": "totalMachine",
        "smartable_machines": "smartableMachineCount",
        "smart_machines": "smartMachineCount",
        "manual_machines": "manualMachineCount",
        "non_smartable_machines": "nonSmartableMachineCount",
        "oee_enabled_machines": "oeeEnableCount",
        "runtime_enabled_machines": "runtimeEnableCount"
    }

    GROUP_FIELDS = {
        "section": "sectionName",
        "location": "locationName",
        "business_unit": "businessUnitName",
        "company": "motherCompanyName"
    }

    def __init__(self, client, lookup):
        self.client = client
        self.lookup = lookup

    # -----------------------------------------
    # BASIC HELPERS
    # -----------------------------------------

    @staticmethod
    def get_field(record, field, default=None):
        if not isinstance(record, dict):
            return default

        for key, value in record.items():
            if key.casefold() == field.casefold():
                return value

        return default

    @staticmethod
    def number(value):
        try:
            return float(value) if value not in (None, "") else 0.0
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def percentage(value, total):
        return (value / total * 100) if total else 0.0

    @staticmethod
    def clean_name(value):
        return str(value or "Unknown").strip() or "Unknown"

    # -----------------------------------------
    # REPORT API
    # -----------------------------------------

    def get_report(
        self,
        company=None,
        business_unit=None,
        location=None,
        section=None,
        grid_type="detail"
    ):
        filters = self.lookup.resolve_filters(
            company=company,
            business_unit=business_unit,
            location=location,
            section=section
        )

        return self.client.get_machine_audit_report(
            mother_company_id=filters.get("mother_company_id"),
            business_unit_id=filters.get("business_unit_id"),
            location_id=filters.get("location_id"),
            section_id=filters.get("section_id"),
            grid_type=grid_type
        )

    # -----------------------------------------
    # SUMMARY CALCULATION
    # -----------------------------------------

    def calculate_summary(self, records):

        summary = {
            "record_count": len(records)
        }

        for label, field in self.METRICS.items():
            summary[label] = sum(
                self.number(
                    self.get_field(record, field, 0)
                )
                for record in records
            )

        total = summary["total_machines"]
        smartable = summary["smartable_machines"]
        smart = summary["smart_machines"]

        summary["smartable_machine_percentage"] = (
            self.percentage(smartable, total)
        )

        # Smart machines among smartable machines.
        summary["smart_machine_percentage"] = (
            self.percentage(smart, smartable)
        )

        summary["manual_machine_percentage"] = (
            self.percentage(
                summary["manual_machines"], total
            )
        )

        summary["non_smartable_percentage"] = (
            self.percentage(
                summary["non_smartable_machines"], total
            )
        )

        summary["oee_percentage"] = (
            self.percentage(
                summary["oee_enabled_machines"], total
            )
        )

        summary["runtime_percentage"] = (
            self.percentage(
                summary["runtime_enabled_machines"], total
            )
        )

        summary["machines_without_oee"] = max(
            0,
            total - summary["oee_enabled_machines"]
        )

        summary["machines_without_runtime"] = max(
            0,
            total - summary["runtime_enabled_machines"]
        )

        summary["automation_gap"] = (
            summary["non_smartable_machines"]
        )

        return summary

    def machine_summary(
        self,
        company=None,
        business_unit=None,
        location=None,
        section=None
    ):
        records = self.get_report(
            company=company,
            business_unit=business_unit,
            location=location,
            section=section,
            grid_type="detail"
        )

        return self.calculate_summary(records)

    # -----------------------------------------
    # GROUP REPORT RECORDS
    # -----------------------------------------

    def group_records(self, records, group_by):

        if group_by not in self.GROUP_FIELDS:
            raise ValueError(
                f"Unsupported grouping: {group_by}"
            )

        field = self.GROUP_FIELDS[group_by]
        groups = {}

        for record in records:

            name = self.clean_name(
                self.get_field(record, field)
            )

            key = name.casefold()

            if key not in groups:
                groups[key] = {
                    "name": name,
                    "records": []
                }

            groups[key]["records"].append(record)

        results = []

        for group in groups.values():

            summary = self.calculate_summary(
                group["records"]
            )

            results.append({
                "name": group["name"],
                **summary
            })

        return results

    # -----------------------------------------
    # TOP / BOTTOM SECTIONS
    # -----------------------------------------

    def get_ranked_sections(
        self,
        records,
        limit=5,
        ascending=False
    ):

        sections = self.group_records(
            records,
            "section"
        )

        sections.sort(
            key=lambda x: x["total_machines"],
            reverse=not ascending
        )

        return sections[:max(0, limit)]

    def get_top_sections(self, records, limit=5):
        return self.get_ranked_sections(
            records,
            limit=limit,
            ascending=False
        )

    def get_bottom_sections(self, records, limit=5):
        return self.get_ranked_sections(
            records,
            limit=limit,
            ascending=True
        )

    # Backward compatibility with existing voice_handler.py.
    def get_top_section(self, records):

        sections = self.get_top_sections(
            records,
            limit=1
        )

        if not sections:
            return None, 0

        return (
            sections[0]["name"],
            sections[0]["total_machines"]
        )

    # -----------------------------------------
    # AUTOMATION PRIORITY
    # -----------------------------------------

    def get_automation_priority(
        self,
        records,
        limit=10
    ):

        sections = self.group_records(
            records,
            "section"
        )

        sections.sort(
            key=lambda x: (
                x["non_smartable_machines"],
                x["total_machines"]
            ),
            reverse=True
        )

        return sections[:max(0, limit)]

    def get_zero_smart_sections(self, records):

        sections = self.group_records(
            records,
            "section"
        )

        return [
            item for item in sections
            if item["smart_machines"] == 0
        ]

    def get_zero_oee_sections(self, records):

        sections = self.group_records(
            records,
            "section"
        )

        return [
            item for item in sections
            if item["oee_enabled_machines"] == 0
        ]

    def get_zero_runtime_sections(self, records):

        sections = self.group_records(
            records,
            "section"
        )

        return [
            item for item in sections
            if item["runtime_enabled_machines"] == 0
        ]

    # -----------------------------------------
    # LOCATION / BUSINESS UNIT REPORTS
    # -----------------------------------------

    def get_location_summary(self, records):
        return self.group_records(
            records,
            "location"
        )

    def get_business_unit_summary(self, records):
        return self.group_records(
            records,
            "business_unit"
        )

    def get_company_summary(self, records):
        return self.group_records(
            records,
            "company"
        )

    def get_top_locations(self, records, limit=5):
        results = self.get_location_summary(records)

        results.sort(
            key=lambda x: x["total_machines"],
            reverse=True
        )

        return results[:max(0, limit)]

    def get_top_business_units(self, records, limit=5):
        results = self.get_business_unit_summary(records)

        results.sort(
            key=lambda x: x["total_machines"],
            reverse=True
        )

        return results[:max(0, limit)]

    # -----------------------------------------
    # COMPARE TWO GROUPS
    # -----------------------------------------

    def compare_groups(
        self,
        records,
        group_by,
        first_name,
        second_name
    ):

        if group_by not in self.GROUP_FIELDS:
            raise ValueError(
                f"Unsupported comparison: {group_by}"
            )

        groups = self.group_records(
            records,
            group_by
        )

        first = next(
            (
                x for x in groups
                if x["name"].casefold()
                == first_name.strip().casefold()
            ),
            None
        )

        second = next(
            (
                x for x in groups
                if x["name"].casefold()
                == second_name.strip().casefold()
            ),
            None
        )

        if first is None:
            raise ValueError(
                f"Cannot find {group_by}: {first_name}"
            )

        if second is None:
            raise ValueError(
                f"Cannot find {group_by}: {second_name}"
            )

        return {
            "group_type": group_by,
            "first": first,
            "second": second,
            "machine_difference": (
                first["total_machines"]
                - second["total_machines"]
            ),
            "smartability_difference": (
                first["smartable_machine_percentage"]
                - second["smartable_machine_percentage"]
            )
        }

    # -----------------------------------------
    # ENGINEER-WISE SUMMARY
    # -----------------------------------------

    def get_engineer_summary(self, records):

        engineers = {}

        for record in records:

            name = self.clean_name(
                self.get_field(
                    record,
                    "automationEngineer"
                )
            )

            key = name.casefold()

            if key not in engineers:
                engineers[key] = {
                    "name": name,
                    "records": []
                }

            engineers[key]["records"].append(record)

        results = []

        for engineer in engineers.values():

            summary = self.calculate_summary(
                engineer["records"]
            )

            results.append({
                "name": engineer["name"],
                **summary
            })

        results.sort(
            key=lambda x: x["total_machines"],
            reverse=True
        )

        return results

    # -----------------------------------------
    # SECTION DETAILS
    # -----------------------------------------

    def get_section_details(self, records):

        details = []

        for record in records:

            details.append({
                "mother_company": self.get_field(
                    record, "motherCompanyName", ""
                ),
                "section": self.get_field(
                    record, "sectionName", ""
                ),
                "business_unit": self.get_field(
                    record, "businessUnitName", ""
                ),
                "location": self.get_field(
                    record, "locationName", ""
                ),
                "machine_type": self.get_field(
                    record, "machineTypeName", ""
                ),
                "total_machines": self.number(
                    self.get_field(record, "totalMachine")
                ),
                "smartable_machines": self.number(
                    self.get_field(
                        record, "smartableMachineCount"
                    )
                ),
                "smartable_percentage": self.number(
                    self.get_field(
                        record,
                        "smartableMachineCountPercentage"
                    )
                ),
                "smart_machines": self.number(
                    self.get_field(
                        record, "smartMachineCount"
                    )
                ),
                "smart_percentage": self.number(
                    self.get_field(
                        record, "smartMachineCountPercentage"
                    )
                ),
                "non_smartable_machines": self.number(
                    self.get_field(
                        record, "nonSmartableMachineCount"
                    )
                ),
                "manual_machines": self.number(
                    self.get_field(
                        record, "manualMachineCount"
                    )
                ),
                "manual_percentage": self.number(
                    self.get_field(
                        record, "manualMachineCountPercentage"
                    )
                ),
                "oee_enabled": self.number(
                    self.get_field(record, "oeeEnableCount")
                ),
                "runtime_enabled": self.number(
                    self.get_field(record, "runtimeEnableCount")
                ),
                "misbp": self.get_field(
                    record, "misbp", ""
                ),
                "automation_engineer": self.get_field(
                    record, "automationEngineer", ""
                ),
                "business_coordinator": self.get_field(
                    record, "businessCoordinator", ""
                )
            })

        return details

    # -----------------------------------------
    # FORMAT SUMMARY FOR GHOST VOICE
    # -----------------------------------------

    def format_summary(self, summary):

        return (
            f"Total machines: "
            f"{summary['total_machines']:.0f}. "

            f"Smartable machines: "
            f"{summary['smartable_machines']:.0f}. "

            f"Smart machines: "
            f"{summary['smart_machines']:.0f}. "

            f"Smart machine percentage: "
            f"{summary['smart_machine_percentage']:.2f} percent. "

            f"Smartable machine percentage: "
            f"{summary['smartable_machine_percentage']:.2f} percent. "

            f"Manual machines: "
            f"{summary['manual_machines']:.0f}. "

            f"Non-smartable machines: "
            f"{summary['non_smartable_machines']:.0f}. "

            f"OEE enabled machines: "
            f"{summary['oee_enabled_machines']:.0f}. "

            f"OEE enablement percentage: "
            f"{summary['oee_percentage']:.2f} percent. "

            f"Machines without OEE: "
            f"{summary['machines_without_oee']:.0f}. "

            f"Runtime enabled machines: "
            f"{summary['runtime_enabled_machines']:.0f}. "

            f"Runtime enablement percentage: "
            f"{summary['runtime_percentage']:.2f} percent. "

            f"Machines without runtime: "
            f"{summary['machines_without_runtime']:.0f}. "

            f"Report records: "
            f"{summary['record_count']}."
        )

    # -----------------------------------------
    # FORMAT RANKINGS
    # -----------------------------------------

    def format_rankings(self, items):

        if not items:
            return "No matching records were found."

        lines = []

        for index, item in enumerate(items, start=1):

            lines.append(
                f"Number {index}: {item['name']}. "
                f"Total machines: "
                f"{item['total_machines']:.0f}. "
                f"Smartable: "
                f"{item['smartable_machines']:.0f}. "
                f"Non-smartable: "
                f"{item['non_smartable_machines']:.0f}. "
                f"Smartability: "
                f"{item['smartable_machine_percentage']:.2f} percent."
            )

        return " ".join(lines)

    # -----------------------------------------
    # FORMAT COMPARISON
    # -----------------------------------------

    def format_comparison(self, comparison):

        first = comparison["first"]
        second = comparison["second"]

        return (
            f"Comparison between "
            f"{first['name']} and {second['name']}. "

            f"{first['name']} has "
            f"{first['total_machines']:.0f} machines. "

            f"{second['name']} has "
            f"{second['total_machines']:.0f} machines. "

            f"Machine count difference: "
            f"{abs(comparison['machine_difference']):.0f}. "

            f"Smartability difference: "
            f"{abs(comparison['smartability_difference']):.2f} percentage points."
        )

    # -----------------------------------------
    # FORMAT SECTION DETAILS
    # -----------------------------------------

    def format_section_details(self, record):

        return (
            f"Section: {record['section']}. "
            f"Company: {record['mother_company']}. "
            f"Business unit: {record['business_unit']}. "
            f"Location: {record['location']}. "

            f"Total machines: "
            f"{record['total_machines']:.0f}. "

            f"Smartable machines: "
            f"{record['smartable_machines']:.0f}. "

            f"Smartable percentage: "
            f"{record['smartable_percentage']:.2f} percent. "

            f"Smart machines: "
            f"{record['smart_machines']:.0f}. "

            f"Smart machine percentage: "
            f"{record['smart_percentage']:.2f} percent. "

            f"Non-smartable machines: "
            f"{record['non_smartable_machines']:.0f}. "

            f"Manual machines: "
            f"{record['manual_machines']:.0f}. "

            f"OEE enabled: "
            f"{record['oee_enabled']:.0f}. "

            f"Runtime enabled: "
            f"{record['runtime_enabled']:.0f}. "

            f"MISBP: {record['misbp']}. "

            f"Automation engineer: "
            f"{record['automation_engineer']}. "

            f"Business coordinator: "
            f"{record['business_coordinator']}."
        )
