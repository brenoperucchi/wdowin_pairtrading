import datetime
import glob
import os
import re
import pandas as pd


def _find_latest_oi_file():
    """
    Procura o arquivo de Posicoes em Aberto mais recente.
    Busca em duas pastas (prioridade):
      1. gex/data/  (pasta preferida)
      2. raiz do projeto (fallback, caso o usuario jogue la)
    
    Aceita qualquer variacao de nome como:
      - Posições em aberto-07-05-2026.csv
      - posicoes em aberto-08-05-2026.csv
    """
    # gex/data/ folder
    gex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(gex_dir, 'data')
    
    # project root (one level above gex/)
    project_root = os.path.dirname(gex_dir)
    
    search_dirs = [data_dir, project_root]
    
    candidates = []
    for d in search_dirs:
        for p in [
            os.path.join(d, "Posi*em aberto*.csv"),
            os.path.join(d, "posi*em aberto*.csv"),
        ]:
            candidates.extend(glob.glob(p))
    
    if not candidates:
        return None
    
    # Mais recente pelo mtime
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def get_b3_options_data(current_ibov=186000, file_path=None):
    """
    Parseia o arquivo de Posicoes em aberto da B3.
    
    Parametros:
        current_ibov: Preco spot atual do IBOVESPA
        file_path: Caminho explicito para o CSV. Se None, busca automaticamente.
    """
    if file_path is None:
        file_path = _find_latest_oi_file()
    
    if file_path is None or not os.path.exists(file_path):
        print("B3 Parser: ERRO - Nenhum arquivo 'Posicoes em aberto*.csv' encontrado.")
        print("  Coloque o CSV baixado da B3 em:  gex/data/")
        return pd.DataFrame()
        
    print(f"B3 Parser: Lendo {os.path.basename(file_path)}...")
    
    # Encontra a linha correta do cabecalho (que comeca com Instrumento financeiro)
    header_idx = 0
    with open(file_path, 'r', encoding='latin1') as f:
        for i, line in enumerate(f):
            if line.startswith("Instrumento financeiro"):
                header_idx = i
                break
                
    pos = pd.read_csv(file_path, sep=';', encoding='latin1', skiprows=header_idx, low_memory=False)
    
    options = []
    month_codes = {
        'A': (1, 'CALL'), 'B': (2, 'CALL'), 'C': (3, 'CALL'), 'D': (4, 'CALL'),
        'E': (5, 'CALL'), 'F': (6, 'CALL'), 'G': (7, 'CALL'), 'H': (8, 'CALL'),
        'I': (9, 'CALL'), 'J': (10, 'CALL'), 'K': (11, 'CALL'), 'L': (12, 'CALL'),
        'M': (1, 'PUT'), 'N': (2, 'PUT'), 'O': (3, 'PUT'), 'P': (4, 'PUT'),
        'Q': (5, 'PUT'), 'R': (6, 'PUT'), 'S': (7, 'PUT'), 'T': (8, 'PUT'),
        'U': (9, 'PUT'), 'V': (10, 'PUT'), 'W': (11, 'PUT'), 'X': (12, 'PUT')
    }
    
    for _, row in pos.iterrows():
        ticker = str(row.iloc[0]).strip()
        segment = str(row.iloc[4]).strip()
        
        if not ticker.startswith("IBOV"):
            continue
        if "EQUITY CALL" not in segment and "EQUITY PUT" not in segment:
            continue
            
        match = re.match(r"^IBOV([A-X])(\d+)$", ticker)
        if not match:
            continue
            
        month_code = match.group(1)
        strike_code = match.group(2)
        
        strike = int(strike_code) * 1000
        if len(strike_code) == 2 and strike < 30000:
            strike = int(strike_code) * 10000
            
        month_num, opt_type = month_codes[month_code]
        year = datetime.datetime.now().year
        if month_num < datetime.datetime.now().month:
            year += 1
            
        expiry_date = datetime.datetime(year, month_num, 15)
        
        oi_str = str(row.iloc[11]).replace('.', '').replace('-', '0').strip()
        try:
            oi = int(oi_str)
        except:
            oi = 0
            
        if oi > 0:
            options.append({
                "ticker": ticker,
                "type": opt_type,
                "strike": float(strike),
                "expiry": expiry_date.isoformat(),
                "oi": oi
            })
            
    df = pd.DataFrame(options)
    print(f"B3 Parser: {len(df)} opcoes IBOV extraidas com sucesso.")
    return df
