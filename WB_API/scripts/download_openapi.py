import requests
from pathlib import Path

ROOT = Path(r"d:\MyProject\wb_processor\WB_API")

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/138.0.0.0 Safari/537.36"
    )
}

for name in [
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
]:

    url = f"https://dev.wildberries.ru/api/swagger/yaml/ru/{name}.yaml"

    r = requests.get(
        url,
        headers=headers,
        timeout=60
    )

    print(name, r.status_code)

    if r.status_code == 200 and "openapi:" in r.text.lower():

        (ROOT / "openapi" / "raw" / f"{name}.yaml").write_text(
            r.text,
            encoding="utf-8"
        )