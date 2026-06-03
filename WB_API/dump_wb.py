import json
from pathlib import Path

spec = json.loads(
    Path("wb_products_openapi.json")
    .read_text(encoding="utf-8")
)

print("Title:", spec["info"]["title"])
print("OpenAPI:", spec["openapi"])

print("\nTags:")
for tag in spec["tags"]:
    print("-", tag["name"])

print("\nEndpoints:", len(spec["paths"]))