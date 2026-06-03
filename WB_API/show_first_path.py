import json

with open("wb_products_openapi.json", encoding="utf-8") as f:
    spec = json.load(f)

for p in spec["paths"]:
    print("FIRST PATH:", p)
    break
    