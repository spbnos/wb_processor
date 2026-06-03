from playwright.sync_api import sync_playwright

PROFILE = r"D:\MyProject\wb_processor\WB_API\chrome_profile"

with sync_playwright() as p:

    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE,
        channel="chrome",
        headless=False
    )

    page = context.new_page()

    page.goto(
        "https://dev.wildberries.ru/openapi/work-with-products",
        wait_until="networkidle"
    )

    input("После прохождения антибота нажми Enter...")

    yaml_text = page.evaluate("""
    async () => {
        const href = document.querySelector('a[href$=".yaml"]').href;
        const r = await fetch(href);
        return await r.text();
    }
    """)

    print(yaml_text[:1000])

    input("ENTER...")
    context.close()