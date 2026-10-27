import os
from datetime import datetime
import requests
import pandas as pd

def _download_via_b3_api(target_date, dest_path):
    """
    Baixa posições em aberto diretamente da API REST pública da B3.
    Mais rápido e estável que automação por navegador.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR",
    }
    page_size = 1000
    page = 1
    all_rows = []
    
    csv_header = [
        "Instrumento financeiro", "Código ISIN", "Ativo", "Código de expiração",
        "Segmento", "Contratos em aberto", "Variação de contratos em aberto",
        "Identificador da distribuição", "Quantidade coberta", "Total de posições bloqueadas",
        "Quantidade descoberta", "Total de posições", "Quantidade de tomadores",
        "Quantidade de doadores", "Quantidade atual", "Contratos travados",
        "Contratos baixados por transferência", "Preço a termo"
    ]
    
    print(f"Tentando download direto via REST API da B3 para {target_date}...")
    session = requests.Session()
    session.headers.update(headers)
    
    while True:
        url = f"https://arquivos.b3.com.br/bdi/table/OpenPositionsEquities/{target_date}/{target_date}/{page}/{page_size}"
        
        # Tentativas com retry por página para evitar abortar por oscilações temporárias
        resp_json = None
        for attempt_page in range(1, 4):
            try:
                r = session.post(url, json={}, timeout=45)
                if r.status_code == 200:
                    resp_json = r.json()
                    break
                elif r.status_code != 200 and page == 1:
                    return False
            except Exception as req_err:
                if attempt_page == 3:
                    print(f"  [Aviso] Falha na página {page} após 3 tentativas: {req_err}")
                    raise
                import time as _t
                _t.sleep(2)
                
        if not resp_json:
            break
            
        data = resp_json
        table_data = data.get("table", {})
        values = table_data.get("values", [])
        if not values:
            break
            
        all_rows.extend(values)
        total_pages = table_data.get("pageCount", 1)
        if page % 10 == 0 or page >= total_pages or len(values) < page_size:
            print(f"  Página {page}/{total_pages} carregada ({len(all_rows)} registros)...")
        if page >= total_pages or len(values) < page_size:
            break
        page += 1
        
    if len(all_rows) > 500:
        df = pd.DataFrame(all_rows)
        while df.shape[1] < len(csv_header):
            df[df.shape[1]] = None
        df = df.iloc[:, :len(csv_header)]
        df.columns = csv_header
        df = df.fillna("-")
        
        with open(dest_path, "w", encoding="latin1") as f:
            f.write("Apresenta o volume e valor das posições em aberto em derivativos de renda variável, indicando o interesse do mercado.\n\n")
            df.to_csv(f, sep=";", index=False, lineterminator="\n")
            
        print(f"Download direto via API concluído com sucesso!")
        print(f"Salvo em: {dest_path} ({os.path.getsize(dest_path) / 1024 / 1024:.2f} MB)")
        return True
    return False

def download_b3_positions(target_date=None):
    """
    Automates the download of the "Posições em aberto" CSV file from B3.
    Saves it directly to gex/data/ with the correct date format.
    
    Args:
        target_date (str or datetime.date): Optional date (YYYY-MM-DD) to fetch.
        
    Returns:
        str: Absolute path to the downloaded CSV file, or None if failed.
    """
    if target_date and not isinstance(target_date, str):
        target_date = target_date.isoformat()
        
    engine_dir = os.path.dirname(os.path.abspath(__file__))
    gex_dir = os.path.dirname(engine_dir)
    data_dir = os.path.join(gex_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    url = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/boletim-diario-do-mercado/"
    print("=" * 50)
    print("  B3 DOWNLOADER - OPEN INTEREST")
    print("=" * 50)
    if target_date:
        print(f"Data Alvo Solicitada: {target_date}")
    print()
    
    # Se a data não foi especificada, obtém a data de pregão mais recente publicada pela B3
    calc_date = target_date
    if not calc_date:
        try:
            r_wd = requests.get("https://arquivos.b3.com.br/bdi/table/workday?", timeout=10)
            if r_wd.status_code == 200:
                raw_wd = r_wd.json().strip('"')
                calc_date = raw_wd.split("T")[0]
        except Exception:
            pass
            
    if not calc_date:
        calc_date = datetime.now().strftime("%Y-%m-%d")
        
    parts = calc_date.split('-')
    if len(parts) == 3:
        date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
    else:
        date_str = calc_date
        
    filename = f"Posições em aberto-{date_str}.csv"
    dest_path = os.path.join(data_dir, filename)
    
    # Se o arquivo já existe e tem tamanho considerável (> 1MB), pula o download
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000000:
        print(f"Arquivo já existe e é válido: {filename} ({os.path.getsize(dest_path) / 1024 / 1024:.2f} MB)")
        print("Pulando download para economizar recursos.")
        print("=" * 50)
        return dest_path
        
    # Método 1: Download direto via REST API (rápido e resiliente)
    try:
        if _download_via_b3_api(calc_date, dest_path):
            print("=" * 50)
            return dest_path
    except Exception as e:
        print(f"Aviso na tentativa REST API: {e}. Tentando via Playwright...")

    # Método 2: Automação por Playwright Browser (Fallback)
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            print("Abrindo navegador headless (Chromium)...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()
            
            print(f"Navegando para o portal da B3...")
            page.goto(url, wait_until="networkidle", timeout=45000)
            
            frame = page.frame(name="bvmf_iframe")
            if frame is None:
                raise RuntimeError("Frame 'bvmf_iframe' não encontrado na página da B3.")
                
            print("Clicando no menu 'Derivativos'...")
            nav_derivativos = frame.locator('.nav-link:has-text("Derivativos")')
            nav_derivativos.click()
            page.wait_for_timeout(2000)
            
            print("Selecionando 'Derivativos de bolsa'...")
            bolsa_item = frame.locator('a.dropdown-item:has-text("Derivativos de bolsa")')
            bolsa_item.click()
            page.wait_for_timeout(4000)
            
            frame.select_option('#selectTabelas', 'OpenPositionsEquities@false')
            page.wait_for_timeout(4000)
            
            if target_date:
                print(f"Alterando a data do picker para: {target_date}...")
                frame.evaluate(f"""() => {{
                    const picker = document.querySelector('duet-date-picker');
                    if (picker) {{
                        picker.value = '{target_date}';
                        picker.dispatchEvent(new Event('change'));
                    }}
                }}""")
                page.wait_for_timeout(6000)
            
            # Obtém a data selecionada do picker para nomear o arquivo
            date_val = frame.evaluate("() => document.querySelector('duet-date-picker') ? document.querySelector('duet-date-picker').value : ''")
            print(f"Data selecionada no portal B3: {date_val}")
            
            if not date_val:
                date_val = datetime.now().strftime("%Y-%m-%d")
                print(f"Aviso: Não foi possível ler a data do picker. Usando hoje como fallback: {date_val}")
                
            parts = date_val.split('-')
            if len(parts) == 3:
                date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                date_str = date_val
                
            filename = f"Posições em aberto-{date_str}.csv"
            dest_path = os.path.join(data_dir, filename)
            
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000000:
                print(f"Arquivo já existe e é válido: {filename} ({os.path.getsize(dest_path) / 1024 / 1024:.2f} MB)")
                browser.close()
                print("=" * 50)
                return dest_path
                
            print("Iniciando download do arquivo CSV...")
            with page.expect_download(timeout=180000) as download_info:
                frame.locator('button[title="Exportar CSV"]').click(force=True)
                print("Botão clicado. Aguardando processamento da B3...")
                
            download = download_info.value
            download.save_as(dest_path)
            
            print(f"Download concluído com sucesso!")
            print(f"Salvo em: {dest_path} ({os.path.getsize(dest_path) / 1024 / 1024:.2f} MB)")
            
            browser.close()
            print("=" * 50)
            return dest_path
            
    except Exception as e:
        print(f"ERRO no B3 Downloader: {e}")
        print("=" * 50)
        return None

if __name__ == "__main__":
    download_b3_positions()
