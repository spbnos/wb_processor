# count_schemas.py

import json

with open(
    "wb_products_openapi.json",
    encoding="utf-8"
) as f:
    spec = json.load(f)

schemas = spec["components"]["schemas"]

print(
    "Schemas:",
    len(schemas)
)

for name in list(schemas)[:50]:
    print(name)