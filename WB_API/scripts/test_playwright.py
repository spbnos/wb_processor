# scripts/test_playwright.py

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        slow_mo=500
    )

    page = browser.new_page()

    page.goto(
        "https://dev.wildberries.ru/swagger/products",
        wait_until="domcontentloaded",
        timeout=120000
    )

    print("TITLE:", page.title())
    print("URL:", page.url)

    input("Press Enter to close browser...")

    browser.close()
