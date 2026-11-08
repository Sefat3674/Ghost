
class SmartManufacturingLookup:

    def __init__(self, client):
        self.client = client

    @staticmethod
    def normalize(value):
        return str(value or "").strip().casefold()

    @staticmethod
    def get_field(record, field, default=None):

        if not isinstance(record, dict):
            return default

        for key, value in record.items():

            if key.casefold() == field.casefold():
                return value

        return default

    def find_record(
        self,
        records,
        name,
        fields=("name", "fullName", "code"),
        filters=None
    ):

        search = self.normalize(name)
        filters = filters or {}

        matches = []

        for record in records:

            if not self.get_field(
                record, "isActive", True
            ):
                continue

            if self.get_field(
                record, "isDelete", False
            ):
                continue

            # Validate parent IDs.
            valid_parent = True

            for key, expected_value in filters.items():

                actual_value = self.get_field(
                    record, key
                )

                if actual_value != expected_value:
                    valid_parent = False
                    break

            if not valid_parent:
                continue

            # Compare names without case sensitivity.
            values = [
                self.normalize(
                    self.get_field(record, field)
                )
                for field in fields
            ]

            if search in values:
                matches.append(record)

        if not matches:
            raise ValueError(
                f"Cannot find: {name}"
            )

        if len(matches) > 1:
            raise ValueError(
                f"Multiple matches found: {name}"
            )

        return matches[0]

    # --------------------------------
    # Mother Company
    # --------------------------------

    def mother_company(self, name):

        return self.find_record(
            self.client.get_mother_companies(),
            name
        )

    # --------------------------------
    # Business Unit
    # --------------------------------

    def business_unit(
        self,
        name,
        mother_company_id=None
    ):

        filters = {}

        if mother_company_id is not None:
            filters["motherCompanyId"] = mother_company_id

        return self.find_record(
            self.client.get_business_units(),
            name,
            filters=filters
        )

    # --------------------------------
    # Location
    # --------------------------------

    def location(self, name):

        return self.find_record(
            self.client.get_locations(),
            name
        )

    # --------------------------------
    # Section
    # --------------------------------

    def section(
        self,
        name,
        business_unit_id=None,
        location_id=None
    ):

        filters = {}

        if business_unit_id is not None:
            filters["businessUnitId"] = business_unit_id

        if location_id is not None:
            filters["locationId"] = location_id

        return self.find_record(
            self.client.get_sections(),
            name,
            filters=filters
        )

    # --------------------------------
    # Resolve All Filters
    # --------------------------------

    def resolve_filters(
        self,
        company=None,
        business_unit=None,
        location=None,
        section=None
    ):

        result = {}

        company_record = None
        bu_record = None
        location_record = None
        section_record = None

        if company:

            company_record = self.mother_company(company)

            result["mother_company_id"] = (
                self.get_field(company_record, "id")
            )

        if business_unit:

            bu_record = self.business_unit(
                business_unit,
                mother_company_id=(
                    self.get_field(company_record, "id")
                    if company_record else None
                )
            )

            result["business_unit_id"] = (
                self.get_field(bu_record, "id")
            )

        if location:

            location_record = self.location(location)

            result["location_id"] = (
                self.get_field(location_record, "id")
            )

        if section:

            section_record = self.section(
                section,
                business_unit_id=(
                    self.get_field(bu_record, "id")
                    if bu_record else None
                ),
                location_id=(
                    self.get_field(location_record, "id")
                    if location_record else None
                )
            )

            result["section_id"] = (
                self.get_field(section_record, "id")
            )

        return result
