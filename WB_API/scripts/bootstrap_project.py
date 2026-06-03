from pathlib import Path

ROOT = Path(r"d:\MyProject\wb_processor\WB_API")

folders = [
    "openapi/raw",
    "openapi/normalized",
    "registry",
    "generated",
    "docs",
    "prompts",
    "scripts"
]

for folder in folders:
    (ROOT / folder).mkdir(parents=True, exist_ok=True)

print("WB_API structure created")