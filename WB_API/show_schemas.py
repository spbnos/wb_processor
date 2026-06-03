import json

with open(
    "wb_products_openapi.json",
    encoding="utf-8"
) as f:
    spec = json.load(f)

schemas = spec["components"]["schemas"]

print("Schemas:", len(schemas))
print()

for name, schema in schemas.items():

    props = schema.get("properties", {})

    print("=" * 80)
    print(name)

    if props:
        print("Fields:")
        for field in props:
            print("  -", field)
    else:
        print("No properties")

    print()