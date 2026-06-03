import json
import yaml

from pathlib import Path

ROOT = Path(r"d:\MyProject\wb_processor\WB_API")

registry = []

for file in (ROOT / "openapi" / "raw").glob("*.yaml"):

    data = yaml.safe_load(
        file.read_text(
            encoding="utf-8"
        )
    )

    paths = data.get("paths", {})

    for path_name, methods in paths.items():

        for method, spec in methods.items():

            if method.startswith("x-"):
                continue

            registry.append({
                "yaml": file.name,
                "path": path_name,
                "method": method.upper(),
                "summary": spec.get("summary"),
                "tags": spec.get("tags", [])
            })

output = ROOT / "generated" / "wb_api_registry.json"

output.write_text(
    json.dumps(
        registry,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)

print("registry built")