import requests

url = "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
try:
    response = requests.get(url, headers=headers, timeout=10)
    print("Status:", response.status_code)
    print("Content length:", len(response.text))
    print(response.text[:2000])
except Exception as e:
    print("Error:", e)
