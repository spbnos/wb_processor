import requests

url = "https://dev.wildberries.ru/api/swagger/yaml/ru/02-products.yaml"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/137.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Referer": "https://dev.wildberries.ru/swagger/products"
}

r = requests.get(
    url,
    headers=headers,
    timeout=60
)

print(r.status_code)
print(r.text[:500])