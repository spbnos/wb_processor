from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent.parent

folders = [
    "openapi/raw",
    "openapi/normalized",
    "registry",
    "generated",
    "docs",
    "prompts",
]

for f in folders:
    (ROOT / f).mkdir(parents=True, exist_ok=True)

SERVICES = [
    "general",
    "products",
    "orders-fbs",
    "orders-dbw",
    "orders-dbs",
    "orders-fbw",
    "promotion",
    "communications",
    "tariffs",
    "analytics",
    "reports",
    "finances",
]

swagger_urls = [
    f"https://dev.wildberries.ru/swagger/{x}"
    for x in SERVICES
]

(ROOT / "generated" / "services.json").write_text(
    json.dumps(swagger_urls, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print("Project initialized")
print("Swagger services discovered:", len(swagger_urls))