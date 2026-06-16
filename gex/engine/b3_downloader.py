import os
from datetime import datetime
from playwright.sync_api import sync_playwright

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
    print("  B3 DOWNLOADER - PLAYWRIGHT AUTOMATION")
    print("=" * 50)
    print(f"URL: {url}")
    if target_date:
        print(f"Data Alvo Solicitada: {target_date}")
    print()
    
    try:
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
            
            # Se o arquivo já existe e tem tamanho considerável (geralmente > 1MB), pula o download
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000000:
                print(f"Arquivo já existe e é válido: {filename} ({os.path.getsize(dest_path) / 1024 / 1024:.2f} MB)")
                print("Pulando download para economizar recursos.")
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
        print(f"ERRO CRÍTICO no B3 Downloader: {e}")
        print("=" * 50)
        return None

if __name__ == "__main__":
    download_b3_positions()
