import json
from pprint import pformat

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head"
}

with open(
    "wb_products_openapi.json",
    encoding="utf-8"
) as f:
    spec = json.load(f)

with open(
    "refs.txt",
    "w",
    encoding="utf-8"
) as out:

    for path, methods in spec["paths"].items():

        # защита
        if not isinstance(methods, dict):
            continue

        for method, op in methods.items():

            # только HTTP методы
            if method.lower() not in HTTP_METHODS:
                continue

            # защита от list
            if not isinstance(op, dict):
                continue

            out.write("=" * 80 + "\n")
            out.write(f"{method.upper()} {path}\n")
            out.write("=" * 80 + "\n\n")

            out.write("SUMMARY\n")
            out.write("-" * 40 + "\n")
            out.write(op.get("summary", "NO SUMMARY"))

            out.write("\n\n")

            out.write("REQUEST BODY\n")
            out.write("-" * 40 + "\n")

            if "requestBody" in op:
                out.write(
                    pformat(
                        op["requestBody"],
                        width=120
                    )
                )
            else:
                out.write("NONE")

            out.write("\n\n")

            out.write("RESPONSES\n")
            out.write("-" * 40 + "\n")

            out.write(
                pformat(
                    op.get("responses", {}),
                    width=120
                )
            )

            out.write("\n\n\n")

print("saved refs.txt")