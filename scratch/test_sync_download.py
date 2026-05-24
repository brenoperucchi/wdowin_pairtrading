import os
import time
from playwright.sync_api import sync_playwright

def download_b3_positions():
    """
    Automates the download of the "Posições em aberto" CSV file from B3.
    Saves it directly to gex/data/ with the correct date format.
    """
    gex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(gex_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    
    url = "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/boletim-diario-do-mercado/"
    print(f"Iniciando download da B3 via Playwright...")
    
    with sync_playwright() as p:
        print("Abrindo navegador...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        
        print(f"Navegando para {url}...")
        page.goto(url, wait_until="networkidle", timeout=45000)
        
        frame = page.frame(name="bvmf_iframe")
        if frame is None:
            raise RuntimeError("Frame 'bvmf_iframe' não encontrado no portal da B3.")
            
        print("Clicando na aba 'Derivativos'...")
        nav_derivativos = frame.locator('.nav-link:has-text("Derivativos")')
        nav_derivativos.click()
        page.wait_for_timeout(2000)
        
        print("Selecionando 'Derivativos de bolsa'...")
        bolsa_item = frame.locator('a.dropdown-item:has-text("Derivativos de bolsa")')
        bolsa_item.click()
        page.wait_for_timeout(4000)
        
        print("Selecionando a tabela 'Posições em aberto'...")
        frame.select_option('#selectTabelas', 'OpenPositionsEquities@false')
        page.wait_for_timeout(6000)
        
        # Obtém a data selecionada do picker para nomear o arquivo
        date_val = frame.evaluate("() => document.querySelector('duet-date-picker') ? document.querySelector('duet-date-picker').value : ''")
        print(f"Data selecionada detectada: {date_val}")
        
        if not date_val:
            from datetime import datetime
            date_val = datetime.now().strftime("%Y-%m-%d")
            print(f"Aviso: Não foi possível ler a data do picker. Usando hoje como fallback: {date_val}")
            
        parts = date_val.split('-')
        if len(parts) == 3:
            date_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
        else:
            date_str = date_val
            
        filename = f"Posições em aberto-{date_str}.csv"
        dest_path = os.path.join(data_dir, filename)
        
        print(f"Caminho final de destino: {dest_path}")
        
        # Inicia a captura do download e clica no botão do CSV com force=True e timeout maior
        print("Clicando no botão de Exportar CSV...")
        try:
            with page.expect_download(timeout=60000) as download_info:
                frame.locator('button[title="Exportar CSV"]').click(force=True)
                print("Botão clicado. Aguardando a B3 gerar e iniciar o download...")
            
            download = download_info.value
            temp_path = download.path()
            download.save_as(dest_path)
            print(f"Download concluído com sucesso! Salvo em: {dest_path}")
        except Exception as e:
            print(f"Erro durante o download: {e}")
            # Vamos tirar um screenshot do erro para depuração
            page.screenshot(path="scratch/download_error.png")
            print("Screenshot de erro salvo em scratch/download_error.png")
            raise e
        
        browser.close()
        return dest_path

if __name__ == "__main__":
    download_b3_positions()
