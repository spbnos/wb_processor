import json

with open(
    "wb_products_openapi.json",
    encoding="utf-8"
) as f:
    spec = json.load(f)

registry = []

for path, methods in spec["paths"].items():

    for method, meta in methods.items():

        if not isinstance(meta, dict):
            continue

        registry.append(
            {
                "path": path,
                "method": method.upper(),
                "summary": meta.get("summary"),
                "tags": meta.get("tags", []),
                "operationId": meta.get("operationId"),
                "parameters": len(
                    meta.get("parameters", [])
                ),
                "has_request_body":
                    "requestBody" in meta,
            }
        )

with open(
    "wb_registry.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        registry,
        f,
        ensure_ascii=False,
        indent=2
    )

print(
    f"Extracted {len(registry)} endpoints"
)