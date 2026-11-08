
class SmartManufacturingClient:

    def __init__(self, config, auth):
        self.config = config
        self.auth = auth
        self.session = auth.session

    def _url(self, endpoint):
        return (
            f"{self.config.base_url.rstrip('/')}/"
            f"{endpoint.lstrip('/')}"
        )

    def get(self, endpoint, params=None):
        response = self.session.get(
            self._url(endpoint),
            params=params,
            timeout=self.config.timeout,
            verify=self.config.verify_ssl
        )

        response.raise_for_status()
        return response.json()

    def post(self, endpoint, params=None, data=None):
        response = self.session.post(
            self._url(endpoint),
            params=params,
            data=data,
            timeout=self.config.timeout,
            verify=self.config.verify_ssl
        )

        response.raise_for_status()
        return response.json()

    @staticmethod
    def get_field(data, field, default=None):
        if not isinstance(data, dict):
            return default

        for key, value in data.items():
            if key.casefold() == field.casefold():
                return value

        return default

    def get_lookup(self, endpoint):
        result = self.get(endpoint)

        if isinstance(result, list):
            return result

        if not isinstance(result, dict):
            raise ValueError(
                f"Invalid API response: {endpoint}"
            )

        records = self.get_field(result, "data")

        if records is None:
            records = []

        if not isinstance(records, list):
            raise ValueError(
                f"Invalid data array: {endpoint}"
            )

        return records

    # --------------------------------
    # Lookup APIs
    # --------------------------------

    def get_mother_companies(self):
        return self.get_lookup(
            "/mothercompany/getall"
        )

    def get_business_units(self):
        return self.get_lookup(
            "/businessunit/getall"
        )

    def get_locations(self):
        return self.get_lookup(
            "/location/getall"
        )

    def get_sections(self):
        return self.get_lookup(
            "/section/getall"
        )

    # --------------------------------
    # Machine Audit Report API
    # --------------------------------

    def get_machine_audit_report(
        self,
        mother_company_id=None,
        business_unit_id=None,
        location_id=None,
        section_id=None,
        grid_type="detail"
    ):

        params = {
            "gridType": grid_type
        }

        if mother_company_id is not None:
            params["MotherCompanyId"] = mother_company_id

        if business_unit_id is not None:
            params["BusinessUnitId"] = business_unit_id

        if location_id is not None:
            params["LocationId"] = location_id

        if section_id is not None:
            params["SectionId"] = section_id

        result = self.post(
            self.config.report_endpoint,
            params=params
        )

        if not isinstance(result, dict):
            raise ValueError(
                "Invalid Machine Audit Report response"
            )

        success = self.get_field(result, "success", False)

        if not success:
            raise RuntimeError(
                "Machine Audit Report returned success=false"
            )

        records = self.get_field(result, "data", [])

        if not isinstance(records, list):
            raise ValueError(
                "Machine Audit Report data must be a list"
            )

        return records
