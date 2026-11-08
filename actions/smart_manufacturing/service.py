
from typing import Any, Optional


class MachineAuditService:
    """
    Machine Audit Service for Ghost AI.

    Fetches machine audit information from the existing
    Smart Manufacturing application and calculates summaries.

    No Smart Manufacturing source-code modifications required.
    """

    def __init__(self, client):
        self.client = client

    # --------------------------------------------------
    # 1. Fetch and normalize API response
    # --------------------------------------------------

    def _get_records(self) -> list[dict[str, Any]]:

        response = self.client.get_machine_audit_report()

        if response is None:
            raise ValueError("Machine Audit API returned an empty response.")

        # Handle direct JSON array
        if isinstance(response, list):
            data = response

        # Handle wrapped JSON responses
        elif isinstance(response, dict):

            if response.get("success") is False:
                raise RuntimeError(
                    response.get("message", "Machine Audit API failed.")
                )

            data = None

            for key in ("data", "result", "records", "items"):
                if isinstance(response.get(key), list):
                    data = response[key]
                    break

            # Handle a single record
            if data is None and "totalMachine" in response:
                data = [response]

            if data is None:
                raise ValueError(
                    "Could not find machine records in API response."
                )

        else:
            raise TypeError(
                "Unexpected Machine Audit API response type."
            )

        # Validate records
        records = []

        for item in data:
            if not isinstance(item, dict):
                continue

            records.append(item)

        return records

    # --------------------------------------------------
    # 2. Safe number conversion
    # --------------------------------------------------

    @staticmethod
    def _number(value: Any) -> int:

        try:
            return int(float(value or 0))
        except (ValueError, TypeError):
            return 0

    # --------------------------------------------------
    # 3. Filter machine records
    # --------------------------------------------------

    def _filter_records(
        self,
        records: list[dict[str, Any]],
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        location: Optional[str] = None,
        section: Optional[str] = None,
        machine_type: Optional[str] = None
    ) -> list[dict[str, Any]]:

        filtered = records

        filters = {
            "motherCompanyName": company,
            "businessUnitName": business_unit,
            "locationName": location,
            "sectionName": section,
            "machineTypeName": machine_type
        }

        for field, expected in filters.items():

            if not expected:
                continue

            expected = expected.strip().casefold()

            filtered = [
                record
                for record in filtered
                if str(record.get(field) or "").strip().casefold()
                == expected
            ]

        return filtered

    # --------------------------------------------------
    # 4. Calculate machine summary
    # --------------------------------------------------

    def get_machine_summary(
        self,
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        location: Optional[str] = None,
        section: Optional[str] = None,
        machine_type: Optional[str] = None
    ) -> dict[str, Any]:

        records = self._get_records()

        filtered = self._filter_records(
            records=records,
            company=company,
            business_unit=business_unit,
            location=location,
            section=section,
            machine_type=machine_type
        )

        total = sum(
            self._number(x.get("totalMachine"))
            for x in filtered
        )

        smart = sum(
            self._number(x.get("smartMachineCount"))
            for x in filtered
        )

        manual = sum(
            self._number(x.get("manualMachineCount"))
            for x in filtered
        )

        smartable = sum(
            self._number(x.get("smartableMachineCount"))
            for x in filtered
        )

        non_smartable = sum(
            self._number(x.get("nonSmartableMachineCount"))
            for x in filtered
        )

        oee = sum(
            self._number(x.get("oeeEnableCount"))
            for x in filtered
        )

        runtime = sum(
            self._number(x.get("runtimeEnableCount"))
            for x in filtered
        )

        return {
            "success": True,
            "filters": {
                "company": company or "All",
                "businessUnit": business_unit or "All",
                "location": location or "All",
                "section": section or "All",
                "machineType": machine_type or "All"
            },
            "recordCount": len(filtered),
            "totalMachines": total,
            "smartMachines": smart,
            "manualMachines": manual,
            "smartableMachines": smartable,
            "nonSmartableMachines": non_smartable,
            "oeeEnabledMachines": oee,
            "runtimeEnabledMachines": runtime,
            "smartPercentage": round(
                smart / total * 100, 2
            ) if total else 0,
            "manualPercentage": round(
                manual / total * 100, 2
            ) if total else 0
        }

    # --------------------------------------------------
    # 5. Get a specific machine count
    # --------------------------------------------------

    def get_machine_count(
        self,
        category: str = "total",
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        location: Optional[str] = None,
        section: Optional[str] = None
    ) -> dict[str, Any]:

        summary = self.get_machine_summary(
            company=company,
            business_unit=business_unit,
            location=location,
            section=section
        )

        categories = {
            "total": "totalMachines",
            "smart": "smartMachines",
            "manual": "manualMachines",
            "smartable": "smartableMachines",
            "non_smartable": "nonSmartableMachines",
            "oee": "oeeEnabledMachines",
            "runtime": "runtimeEnabledMachines"
        }

        category = category.strip().lower()

        if category not in categories:
            raise ValueError(
                f"Unsupported machine category: {category}"
            )

        field = categories[category]

        return {
            "success": True,
            "category": category,
            "count": summary[field],
            "filters": summary["filters"],
            "totalMachines": summary["totalMachines"],
            "smartMachines": summary["smartMachines"],
            "manualMachines": summary["manualMachines"]
        }

    # --------------------------------------------------
    # 6. Generate voice-friendly response
    # --------------------------------------------------

    def get_voice_response(
        self,
        category: str = "total",
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        location: Optional[str] = None
    ) -> str:

        result = self.get_machine_count(
            category=category,
            company=company,
            business_unit=business_unit,
            location=location
        )

        count = result["count"]
        total = result["totalMachines"]

        scope_parts = [
            value for value in (
                company,
                business_unit,
                location
            ) if value
        ]

        scope = " ".join(scope_parts) if scope_parts else "the company"

        messages = {
            "total": f"There are {count} machines in {scope}.",
            "smart": (
                f"There are {count} smart machines in {scope}, "
                f"out of {total} total machines."
            ),
            "manual": (
                f"There are {count} manual machines in {scope}, "
                f"out of {total} total machines."
            ),
            "smartable": (
                f"There are {count} smart-enabled machines in {scope}."
            ),
            "non_smartable": (
                f"There are {count} non-smartable machines in {scope}."
            ),
            "oee": (
                f"There are {count} OEE-enabled machines in {scope}."
            ),
            "runtime": (
                f"There are {count} runtime-enabled machines in {scope}."
            )
        }

        return messages[result["category"]]

    # --------------------------------------------------
    # 7. Complete machine report
    # --------------------------------------------------

    def get_full_report(
        self,
        company: Optional[str] = None,
        business_unit: Optional[str] = None,
        location: Optional[str] = None
    ) -> dict[str, Any]:

        summary = self.get_machine_summary(
            company=company,
            business_unit=business_unit,
            location=location
        )

        records = self._get_records()

        filtered = self._filter_records(
            records,
            company=company,
            business_unit=business_unit,
            location=location
        )

        summary["records"] = filtered

        return summary
