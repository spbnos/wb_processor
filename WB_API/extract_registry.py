import json

with open(
    "wb_products_openapi.json",
    encoding="utf-8"
) as f:
    spec = json.load(f)

registry = []

for path, methods in spec["paths"].items():

    if not isinstance(methods, dict):
        continue

    for method, meta in methods.items():

        if not isinstance(meta, dict):
            continue

        registry.append({
            "path": path,
            "method": method.upper(),
            "operationId": meta.get("operationId"),
            "summary": meta.get("summary"),
            "tags": meta.get("tags", []),
        })

print("Operations:", len(registry))

for row in registry:
    print(
        row["method"],
        row["path"],
        "|",
        row["summary"]
    )