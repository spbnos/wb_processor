from playwright.sync_api import sync_playwright
from pathlib import Path
import json

OUT = Path("generated/discovered_specs.json")

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

found = {}

with sync_playwright() as p:

    browser = p.chromium.launch(headless=False)

    page = browser.new_page()

    for service in SERVICES:

        url = f"https://dev.wildberries.ru/swagger/{service}"

        print("OPEN", url)

        page.goto(url, wait_until="networkidle")

        try:
            cfg = page.evaluate("""
            () => {
                if (!window.ui) return null;
                return window.ui.getConfigs();
            }
            """)

            found[service] = cfg

        except Exception as e:
            found[service] = {"error": str(e)}

    browser.close()

OUT.write_text(
    json.dumps(found, ensure_ascii=False, indent=2),
    encoding="utf-8"
)

print("Saved:", OUT)
