import json
import yaml

from pathlib import Path

ROOT = Path(r"d:\MyProject\wb_processor\WB_API")

service_map = {}

for file in (ROOT / "openapi" / "raw").glob("*.yaml"):

    data = yaml.safe_load(
        file.read_text(
            encoding="utf-8"
        )
    )

    service = data["info"]["title"]

    service_map[service] = {
        "version": data["info"].get("version"),
        "file": file.name,
        "tags": [
            tag["name"]
            for tag in data.get("tags", [])
        ]
    }

(ROOT / "generated" / "wb_service_map.json").write_text(
    json.dumps(
        service_map,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)