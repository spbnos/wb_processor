import json

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options"
}

with open("wb_products_openapi.json", encoding="utf-8") as f:
    spec = json.load(f)

count = 0

for path, node in spec["paths"].items():

    for method, info in node.items():

        if method.lower() not in HTTP_METHODS:
            continue

        count += 1

        summary = info.get("summary", "")

        print(
            f"{count:02d}. "
            f"{method.upper():6} "
            f"{path}"
        )

        if summary:
            print(f"     {summary}")

print()
print("TOTAL:", count)