import requests
import re

url = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/boletim-diario-do-mercado/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
try:
    response = requests.get(url, headers=headers, timeout=10)
    html = response.text
    print("Searching for 'arquivos.b3.com.br':")
    matches = re.findall(r'https://[a-zA-Z0-9.-]*b3\.com\.br[^\s"\']*', html)
    for m in set(matches):
        print("Found link:", m)
    
    print("\nSearching for 'Derivativos':")
    for i, line in enumerate(html.split('\n')):
        if 'Derivativos' in line or 'Posições em aberto' in line or 'boletim' in line:
            if len(line.strip()) < 150:
                print(f"Line {i}: {line.strip()}")
except Exception as e:
    print("Error:", e)
