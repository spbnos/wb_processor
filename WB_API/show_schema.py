# show_schema.py

import json
from pprint import pprint

with open(
    "wb_products_openapi.json",
    encoding="utf-8"
) as f:
    spec = json.load(f)

schemas = spec["components"]["schemas"]

for name in [
    "Good",
    "Goods",
    "Warehouse",
    "SizeGood",
    "GoodsList"
]:
    print("\n" + "=" * 80)
    print(name)
    print("=" * 80)

    pprint(
        schemas.get(name)
    )