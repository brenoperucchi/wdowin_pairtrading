"""
download_b3_history.py - Download em lote de dados históricos de Posições em Aberto da B3 (2026 YTD).
Usa a API oficial de bulk download:
https://arquivos.b3.com.br/api/download/requestname?fileName=DerivativesOpenPosition&date=YYYY-MM-DD
"""

import os
import io
import time
import re
import datetime
import requests
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "gex", "data")
os.makedirs(DATA_DIR, exist_ok=True)

CSV_HEADER = [
    "Instrumento financeiro", "Código ISIN", "Ativo", "Código de expiração",
    "Segmento", "Contratos em aberto", "Variação de contratos em aberto",
    "Identificador da distribuição", "Quantidade coberta", "Total de posições bloqueadas",
    "Quantidade descoberta", "Total de posições", "Quantidade de tomadores",
    "Quantidade de doadores", "Quantidade atual", "Contratos travados",
    "Contratos baixados por transferência", "Preço a termo"
]

COL_MAP = {
    "TckrSymb": "Instrumento financeiro",
    "ISIN": "Código ISIN",
    "Asst": "Ativo",
    "XprtnCd": "Código de expiração",
    "SgmtNm": "Segmento",
    "OpnIntrst": "Contratos em aberto",
    "VartnOpnIntrst": "Variação de contratos em aberto",
    "DstrbtnId": "Identificador da distribuição",
    "CvrdQty": "Quantidade coberta",
    "TtlBlckdPos": "Total de posições bloqueadas",
    "UcvrdQty": "Quantidade descoberta",
    "TtlPos": "Total de posições",
    "BrrwrQty": "Quantidade de tomadores",
    "LndrQty": "Quantidade de doadores",
    "CurQty": "Quantidade atual",
    "FwdPric": "Preço a termo"
}

BR_HOLIDAYS_2026 = {
    (1, 1),   # Confraternização Universal
    (2, 16),  # Carnaval
    (2, 17),  # Carnaval
    (4, 3),   # Sexta-feira Santa
    (4, 21),  # Tiradentes
    (5, 1),   # Dia do Trabalho
    (6, 4),   # Corpus Christi
    (9, 7),   # Independência
    (10, 12), # N. Sra Aparecida
    (11, 2),  # Finados
    (11, 15), # Proclamação da República
    (11, 20), # Consciência Negra
    (12, 25), # Natal
}


def is_b3_trading_day(d: datetime.date) -> bool:
    if d.weekday() >= 5:
        return False
    if (d.month, d.day) in BR_HOLIDAYS_2026:
        return False
    return True


def get_existing_dates():
    import glob
    existing = set()
    for f in glob.glob(os.path.join(DATA_DIR, "Posições em aberto-*.csv")):
        m = re.search(r"Posições em aberto-(\d{2})-(\d{2})-(\d{4})\.csv", f)
        if m:
            d, mo, y = m.groups()
            existing.add(f"{y}-{mo}-{d}")
    return existing


def download_single_day(date_str: str, session: requests.Session) -> bool:
    parts = date_str.split("-")
    out_filename = f"Posições em aberto-{parts[2]}-{parts[1]}-{parts[0]}.csv"
    dest_path = os.path.join(DATA_DIR, out_filename)

    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000000:
        return True

    token_url = f"https://arquivos.b3.com.br/api/download/requestname?fileName=DerivativesOpenPosition&date={date_str}&recaptchaToken="
    
    for attempt in range(1, 4):
        try:
            r = session.get(token_url, timeout=15)
            if r.status_code != 200:
                if attempt == 3:
                    print(f"  [Skip] {date_str}: B3 retornou status {r.status_code}")
                time.sleep(1)
                continue
                
            token_data = r.json()
            redirect_url = token_data.get("redirectUrl", "")
            if "?token=" not in redirect_url:
                time.sleep(1)
                continue
                
            token = redirect_url.split("?token=")[-1]
            dl_url = f"https://arquivos.b3.com.br/api/download/?token={token}"
            
            res = session.get(dl_url, timeout=35)
            if res.status_code != 200 or len(res.content) < 50000:
                time.sleep(1)
                continue
                
            df = pd.read_csv(io.BytesIO(res.content), sep=";", encoding="latin1", low_memory=False)
            df_mapped = df.rename(columns=COL_MAP)
            for col in CSV_HEADER:
                if col not in df_mapped.columns:
                    df_mapped[col] = "-"
            df_mapped = df_mapped[CSV_HEADER].fillna("-")
            
            tmp_path = dest_path + ".tmp"
            with open(tmp_path, "w", encoding="latin1") as f:
                f.write("Apresenta o volume e valor das posições em aberto em derivativos de renda variável...\n\n")
                df_mapped.to_csv(f, sep=";", index=False, lineterminator="\n")
            os.replace(tmp_path, dest_path)
            
            size_mb = os.path.getsize(dest_path) / 1024 / 1024
            print(f"  [OK] {date_str} -> {out_filename} ({len(df_mapped):,} linhas, {size_mb:.2f} MB)")
            return True
        except Exception as e:
            if attempt == 3:
                print(f"  [ERRO] {date_str} falhou após 3 tentativas: {e}")
            time.sleep(1.5)
            
    return False


def run_ytd_download(start_date="2026-01-01", end_date="2026-11-06"):
    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    
    existing = get_existing_dates()
    
    all_trading_days = []
    curr = start
    while curr <= end:
        if is_b3_trading_day(curr):
            all_trading_days.append(curr.strftime("%Y-%m-%d"))
        curr += datetime.timedelta(days=1)
        
    missing = [d for d in all_trading_days if d not in existing]
    
    print("=" * 60)
    print("  DOWNLOADER HISTÓRICO B3 (DERIVATIVES OPEN POSITION)")
    print("=" * 60)
    print(f"Período: {start_date} até {end_date}")
    print(f"Total de pregões identificados: {len(all_trading_days)}")
    print(f"Pregões já presentes localmente: {len(existing)}")
    print(f"Pregões pendentes para baixar:  {len(missing)}")
    print("=" * 60 + "\n")
    
    if not missing:
        print("Todos os pregões já estão baixados e disponíveis em gex/data/!")
        return len(all_trading_days)
        
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR"
    })
    
    downloaded = 0
    for idx, d in enumerate(missing, 1):
        print(f"[{idx}/{len(missing)}] Baixando {d}...")
        ok = download_single_day(d, session)
        if ok:
            downloaded += 1
        time.sleep(0.3)  # Intervalo amigável para não sobrecarregar a API da B3
        
    print("\n" + "=" * 60)
    print(f"  Download concluído! {downloaded}/{len(missing)} arquivos salvos.")
    print("=" * 60)
    return len(existing) + downloaded


if __name__ == "__main__":
    run_ytd_download()

