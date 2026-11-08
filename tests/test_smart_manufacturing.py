
companies = client.get_mother_companies()
business_units = client.get_business_units()
locations = client.get_locations()
sections = client.get_sections()

print("Mother Companies:", len(companies))
print("Business Units:", len(business_units))
print("Locations:", len(locations))
print("Sections:", len(sections))

pran_id = client.resolve_id(companies, "PRAN")

print("PRAN ID:", pran_id)
