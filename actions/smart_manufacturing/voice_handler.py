
import re


class SmartManufacturingVoiceHandler:

    def __init__(self, client, lookup, report_service):
        self.client = client
        self.lookup = lookup
        self.report_service = report_service

        # Structured data for the Ghost dashboard.
        self.last_visualization_data = None
        self.dashboard_filter_options = {
            "companies": [],
            "business_units": [],
            "locations": []
        }

    def set_visualization_data(
        self,
        kind,
        title,
        summary=None,
        items=None,
        details=None,
        filters=None
    ):
        self.last_visualization_data = {
            "kind": kind,
            "title": title,
            "summary": summary or {},
            "items": items or [],
            "details": details or [],
            "filters": filters or {},
            "filter_options": self.dashboard_filter_options
        }

    @staticmethod
    def normalize(text):
        if not text:
            return ""

        return " ".join(str(text).lower().strip().split())

    @staticmethod
    def contains_entity(text, name):
        normalized_name = SmartManufacturingVoiceHandler.normalize(name)

        if not normalized_name:
            return False

        pattern = (
            r"(?<![a-z0-9])"
            + re.escape(normalized_name)
            + r"(?![a-z0-9])"
        )

        return re.search(pattern, text) is not None

    @staticmethod
    def get_value(record, field, default=None):
        if not isinstance(record, dict):
            return default

        for key, value in record.items():
            if key.casefold() == field.casefold():
                return value

        return default

    def detect_entity(self, text, records, fields):
        candidates = []

        for record in records:
            is_active = self.get_value(record, "isActive", True)
            is_deleted = self.get_value(record, "isDelete", False)

            if is_active is False or str(is_active).lower() == "false":
                continue

            if is_deleted is True or str(is_deleted).lower() == "true":
                continue

            for field in fields:
                value = self.get_value(record, field)

                if value:
                    value = str(value).strip()

                    if value:
                        candidates.append(value)

        candidates = sorted(set(candidates), key=len, reverse=True)

        for name in candidates:
            if self.contains_entity(text, name):
                return name

        return None

    def parse_filters(self, command):
        text = self.normalize(command)

        companies = self.client.get_mother_companies()
        business_units = self.client.get_business_units()
        locations = self.client.get_locations()
        sections = self.client.get_sections()

        def active_options(records):
            options = []

            for record in records:
                is_active = self.get_value(record, "isActive", True)
                is_deleted = self.get_value(record, "isDelete", False)

                if str(is_active).lower() == "false":
                    continue

                if str(is_deleted).lower() == "true":
                    continue

                record_id = self.get_value(record, "id")
                name = (
                    self.get_value(record, "name")
                    or self.get_value(record, "fullName")
                )

                if record_id is None or not name:
                    continue

                options.append({
                    "id": record_id,
                    "name": str(name).strip()
                })

            return sorted(options, key=lambda item: item["name"].casefold())

        self.dashboard_filter_options = {
            "companies": active_options(companies),
            "business_units": active_options(business_units),
            "locations": active_options(locations)
        }

        # Preserve the company relationship for dependent business-unit filters.
        for option in self.dashboard_filter_options["business_units"]:
            matching = next(
                (
                    record for record in business_units
                    if str(self.get_value(record, "id")) == str(option["id"])
                ),
                {}
            )
            option["motherCompanyId"] = self.get_value(
                matching, "motherCompanyId"
            )

        company = self.detect_entity(
            text,
            companies,
            ["motherCompanyName", "name", "fullName", "code"]
        )

        business_unit = self.detect_entity(
            text,
            business_units,
            ["businessUnitName", "name", "fullName", "code"]
        )

        location = self.detect_entity(
            text,
            locations,
            ["locationName", "name", "fullName", "code"]
        )

        section = self.detect_entity(
            text,
            sections,
            ["sectionName", "name", "fullName", "code"]
        )

        if company:
            company_name = self.normalize(company)

            if business_unit and self.normalize(business_unit) == company_name:
                business_unit = None

            if location and self.normalize(location) == company_name:
                location = None

            if section and self.normalize(section) == company_name:
                section = None

        if section and self.normalize(section) == "audit":
            if "section" not in text:
                section = None

        return {
            "company": company,
            "business_unit": business_unit,
            "location": location,
            "section": section
        }

    def get_limit(self, text, default=5):
        match = re.search(
            r"\b(?:top|bottom|first|last)\s+(\d+)\b",
            text
        )

        if match:
            return max(1, int(match.group(1)))

        return default

    def get_filter_description(self, filters):
        values = [value for value in filters.values() if value]

        if not values:
            return ""

        return " for " + ", ".join(values)

    def format_section_names(self, sections, metric_label):
        if not sections:
            return f"No sections with zero {metric_label} were found."

        names = []

        for section in sections:
            name = (
                section.get("name")
                or section.get("section")
                or "Unknown section"
            )

            if name not in names:
                names.append(name)

        if len(names) == 1:
            return f"{names[0]} has zero {metric_label}."

        if len(names) == 2:
            return (
                f"{names[0]} and {names[1]} "
                f"have zero {metric_label}."
            )

        return (
            ", ".join(names[:-1])
            + f", and {names[-1]} have zero {metric_label}."
        )

    def refresh_dashboard(self, selected_filters, current_data):
        """Refresh the current dashboard view using the selected filters."""
        filters = {}

        for key in ("company", "business_unit", "location"):
            value = selected_filters.get(key)
            if value and not str(value).lower().startswith("all "):
                filters[key] = value
            else:
                filters[key] = None

        records = self.report_service.get_report(
            **filters,
            grid_type="detail"
        )

        if not records:
            raise ValueError("No machine audit records found for these filters.")

        summary = self.report_service.calculate_summary(records)

        kind = current_data.get("kind", "summary")
        title = current_data.get("title", "Smart Manufacturing ? Machine Audit")
        items = []
        details = []

        if kind == "zero_sections":
            title_lower = title.lower()

            if "zero smart" in title_lower:
                items = self.report_service.get_zero_smart_sections(records)
            elif "zero oee" in title_lower:
                items = self.report_service.get_zero_oee_sections(records)
            elif "zero runtime" in title_lower:
                items = self.report_service.get_zero_runtime_sections(records)

        elif kind == "details":
            details = self.report_service.get_section_details(records)

        elif kind == "ranking":
            limit = max(1, len(current_data.get("items") or []) or 10)
            title_lower = title.lower()

            if "automation priority" in title_lower:
                items = self.report_service.get_automation_priority(
                    records, limit
                )
            elif "bottom" in title_lower:
                items = self.report_service.get_bottom_sections(
                    records, limit
                )
            else:
                items = self.report_service.get_top_sections(
                    records, limit
                )

        self.set_visualization_data(
            kind=kind,
            title=title,
            summary=summary,
            items=items,
            details=details,
            filters=filters
        )

        return self.last_visualization_data

    def handle(self, command):
        text = self.normalize(command)

        # Clear old dashboard data before processing a new command.
        self.last_visualization_data = None

        try:
            filters = self.parse_filters(text)

            records = self.report_service.get_report(
                **filters,
                grid_type="detail"
            )

            if not records:
                return "No machine audit records were found."

            summary = self.report_service.calculate_summary(records)
            filter_text = self.get_filter_description(filters)

            # Default dashboard: KPI summary.
            self.set_visualization_data(
                kind="summary",
                title="Smart Manufacturing — Machine Audit",
                summary=summary,
                filters=filters
            )

            # -----------------------------------------
            # ZERO SMART / OEE / RUNTIME SECTIONS
            # -----------------------------------------

            if (
                (
                    "zero smart" in text
                    or "no smart machines" in text
                    or "zero smart machines" in text
                )
                and "section" in text
            ):
                sections = self.report_service.get_zero_smart_sections(
                    records
                )

                self.set_visualization_data(
                    kind="zero_sections",
                    title="Sections With Zero Smart Machines",
                    summary=summary,
                    items=sections,
                    filters=filters
                )

                return self.format_section_names(
                    sections,
                    "smart machines"
                )

            if (
                ("zero oee" in text or "no oee" in text)
                and "section" in text
            ):
                sections = self.report_service.get_zero_oee_sections(
                    records
                )

                self.set_visualization_data(
                    kind="zero_sections",
                    title="Sections With Zero OEE",
                    summary=summary,
                    items=sections,
                    filters=filters
                )

                return self.format_section_names(
                    sections,
                    "OEE-enabled machines"
                )

            if (
                (
                    "zero runtime" in text
                    or "zero run time" in text
                    or "no runtime" in text
                    or "no run time" in text
                )
                and "section" in text
            ):
                sections = self.report_service.get_zero_runtime_sections(
                    records
                )

                self.set_visualization_data(
                    kind="zero_sections",
                    title="Sections With Zero Runtime",
                    summary=summary,
                    items=sections,
                    filters=filters
                )

                return self.format_section_names(
                    sections,
                    "runtime-enabled machines"
                )

            # -----------------------------------------
            # SECTION DETAILS
            # -----------------------------------------

            if (
                "section details" in text
                or "details of section" in text
            ):
                details = self.report_service.get_section_details(records)

                if not details:
                    return "No section details were found."

                self.set_visualization_data(
                    kind="details",
                    title="Machine Audit — Section Details",
                    summary=summary,
                    details=details,
                    filters=filters
                )

                if len(details) == 1:
                    return self.report_service.format_section_details(
                        details[0]
                    )

                return (
                    f"I found {len(details)} section records{filter_text}. "
                    "Please specify a location or business unit "
                    "to narrow down the section."
                )

            # -----------------------------------------
            # AUTOMATION PRIORITIES
            # -----------------------------------------

            if (
                "automation gap" in text
                or "automation priority" in text
                or "automation the most" in text
                or "need automation" in text
                or "require automation" in text
                or "automation attention" in text
                or "sections need automation" in text
            ):
                priorities = self.report_service.get_automation_priority(
                    records
                )

                if not priorities:
                    return "No automation priority records were found."

                self.set_visualization_data(
                    kind="ranking",
                    title="Automation Priority — Top Sections",
                    summary=summary,
                    items=priorities,
                    filters=filters
                )

                return self.report_service.format_rankings(priorities)

            # -----------------------------------------
            # TOP SECTION RANKING
            # -----------------------------------------

            if (
                (
                    "which section" in text
                    or "which sections" in text
                    or "highest section" in text
                    or "most machines" in text
                    or "top section" in text
                )
                and "automation" not in text
            ):
                limit = self.get_limit(text)

                rankings = self.report_service.get_top_sections(
                    records,
                    limit
                )

                if not rankings:
                    return "I could not find any section information."

                self.set_visualization_data(
                    kind="ranking",
                    title="Top Sections by Machine Count",
                    summary=summary,
                    items=rankings,
                    filters=filters
                )

                return self.report_service.format_rankings(rankings)

            # -----------------------------------------
            # BOTTOM SECTION RANKING
            # -----------------------------------------

            if (
                "bottom section" in text
                or "least machines" in text
            ):
                limit = self.get_limit(text)

                rankings = self.report_service.get_bottom_sections(
                    records,
                    limit
                )

                if not rankings:
                    return "I could not find any section information."

                self.set_visualization_data(
                    kind="ranking",
                    title="Bottom Sections by Machine Count",
                    summary=summary,
                    items=rankings,
                    filters=filters
                )

                return self.report_service.format_rankings(rankings)

            # -----------------------------------------
            # PERCENTAGE REQUESTS
            # -----------------------------------------

            if "smartable" in text and "percentage" in text:
                value = summary["smartable_machine_percentage"]

                return (
                    f"The smartable machine percentage{filter_text} "
                    f"is {value:.2f} percent."
                )

            if "smart" in text and "percentage" in text:
                value = summary["smart_machine_percentage"]

                return (
                    f"The smart machine percentage{filter_text} "
                    f"is {value:.2f} percent."
                )

            if "manual" in text and "percentage" in text:
                value = summary["manual_machine_percentage"]

                return (
                    f"The manual machine percentage{filter_text} "
                    f"is {value:.2f} percent."
                )

            if "non smartable" in text or "non-smartable" in text:
                value = summary["non_smartable_percentage"]

                return (
                    f"The non-smartable machine percentage{filter_text} "
                    f"is {value:.2f} percent."
                )

            if "oee" in text and "percentage" in text:
                value = summary["oee_percentage"]

                return (
                    f"The OEE enablement percentage{filter_text} "
                    f"is {value:.2f} percent."
                )

            if (
                ("runtime" in text or "run time" in text)
                and "percentage" in text
            ):
                value = summary["runtime_percentage"]

                return (
                    f"The runtime enablement percentage{filter_text} "
                    f"is {value:.2f} percent."
                )

            # -----------------------------------------
            # MACHINES WITHOUT OEE / RUNTIME
            # -----------------------------------------

            if "without oee" in text or "no oee" in text:
                value = summary["machines_without_oee"]

                return (
                    f"There are {value:.0f} machines without OEE "
                    f"enablement{filter_text}."
                )

            if (
                "without runtime" in text
                or "without run time" in text
                or "no runtime" in text
                or "no run time" in text
            ):
                value = summary["machines_without_runtime"]

                return (
                    f"There are {value:.0f} machines without runtime "
                    f"enablement{filter_text}."
                )

            # -----------------------------------------
            # MACHINE COUNT REQUESTS
            # -----------------------------------------

            if "non smartable" in text or "non-smartable" in text:
                metric = "non_smartable_machines"
                label = "non-smartable machines"

            elif "smartable" in text:
                metric = "smartable_machines"
                label = "smartable machines"

            elif "smart" in text:
                metric = "smart_machines"
                label = "smart machines"

            elif "manual" in text:
                metric = "manual_machines"
                label = "manual machines"

            elif "oee" in text:
                metric = "oee_enabled_machines"
                label = "OEE-enabled machines"

            elif "runtime" in text or "run time" in text:
                metric = "runtime_enabled_machines"
                label = "runtime-enabled machines"

            else:
                metric = "total_machines"
                label = "machines"

            # -----------------------------------------
            # FULL REPORT SUMMARY
            # -----------------------------------------

            if (
                "show" in text
                or "report" in text
                or "summary" in text
                or "all metrics" in text
            ):
                return (
                    f"Machine audit report{filter_text}. "
                    + self.report_service.format_summary(summary)
                )

            # -----------------------------------------
            # RETURN MACHINE COUNT
            # -----------------------------------------

            value = summary[metric]

            return (
                f"There are {value:.0f} {label}{filter_text}."
            )

        except ValueError as ex:
            self.last_visualization_data = None
            return f"Invalid machine audit request: {str(ex)}"

        except Exception as ex:
            self.last_visualization_data = None
            print("Smart Manufacturing Voice Handler Error:", str(ex))

            return (
                "Sorry, I could not retrieve the machine audit report "
                "right now. Please try again."
            )
