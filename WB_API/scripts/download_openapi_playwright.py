from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(r"d:\MyProject\wb_processor\WB_API")

FILES = [
    "01-general",
    "02-products",
    "03-orders-fbs",
    "04-orders-dbw",
    "05-orders-dbs",
    "06-orders-fbw",
    "07-promotion",
    "08-communications",
    "09-tariffs",
    "10-analytics",
    "11-reports",
    "12-finances",
]

OUT_DIR = ROOT / "openapi" / "raw"
OUT_DIR.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:

    browser = p.chromium.launch(
        headless=False
    )

    page = browser.new_page()

    for name in FILES:

        url = f"https://dev.wildberries.ru/api/swagger/yaml/ru/{name}.yaml"

        print(f"\nDownloading {name}")

        try:

            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=120000
            )

            text = page.locator("body").inner_text()

            if "openapi:" not in text.lower():
                print("BLOCKED")
                continue

            file_path = OUT_DIR / f"{name}.yaml"

            file_path.write_text(
                text,
                encoding="utf-8"
            )

            print("OK")

        except Exception as e:

            print("ERROR:", e)

    browser.close()