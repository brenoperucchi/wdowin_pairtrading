import datetime
import glob
import os
import re
import pandas as pd

def _extract_file_date_key(filepath):
    """
    Extrai a data (YYYY, MM, DD) do nome do arquivo 'Posições em aberto-DD-MM-YYYY.csv'
    para garantir ordenação cronológica real da sessão B3 (e não apenas mtime de disco).
    """
    base = os.path.basename(filepath)
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", base)
    if m:
        d, mo, y = m.groups()
        return (int(y), int(mo), int(d), os.path.getmtime(filepath))
    return (0, 0, 0, os.path.getmtime(filepath))


def _find_latest_oi_file():
    """
    Procura o arquivo de Posições em Aberto mais recente na pasta gex/data ou raiz.
    """
    gex_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(gex_dir, 'data')
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
        
    candidates.sort(key=_extract_file_date_key, reverse=True)
    return candidates[0]

def _get_dol_expiration(year, month):
    """
    Calcula a data de vencimento das opções sobre DOL (Dólar Futuro B3).
    Regra B3: Primeiro dia útil do mês de vencimento.
    """
    d = datetime.date(year, month, 1)
    # 5 = Saturday, 6 = Sunday
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    return datetime.datetime(d.year, d.month, d.day)

def get_b3_dol_options_data(file_path=None):
    """
    Parseia o arquivo de Posições em aberto da B3 e extrai as opções de DOL.
    """
    if file_path is None:
        file_path = _find_latest_oi_file()
        
    if file_path is None or not os.path.exists(file_path):
        print("B3 DOL Parser: ERRO - Nenhum arquivo 'Posicoes em aberto*.csv' encontrado.")
        return pd.DataFrame()
        
    print(f"B3 DOL Parser: Lendo {os.path.basename(file_path)}...")
    
    header_idx = 0
    with open(file_path, 'r', encoding='latin1') as f:
        for i, line in enumerate(f):
            if line.startswith("Instrumento financeiro"):
                header_idx = i
                break
                
    pos = pd.read_csv(file_path, sep=';', encoding='latin1', skiprows=header_idx, low_memory=False)
    
    options = []
    
    # Mapeamento padrão internacional CME/B3 de meses para futuros
    future_months = {
        'F': 1,  # Jan
        'G': 2,  # Feb
        'H': 3,  # Mar
        'J': 4,  # Apr
        'K': 5,  # May
        'M': 6,  # Jun
        'N': 7,  # Jul
        'Q': 8,  # Aug
        'U': 9,  # Sep
        'V': 10, # Oct
        'X': 11, # Nov
        'Z': 12  # Dec
    }
    
    for _, row in pos.iterrows():
        ticker = str(row.iloc[0]).strip()
        segment = str(row.iloc[4]).strip()
        
        # Filtra opções de Dólar
        if not ticker.startswith("DOL"):
            continue
            
        # Formato de opção sobre futuro B3: DOLF27C005300 (13 caracteres)
        match = re.match(r"^DOL([A-Z])(\d{2})([CP])(\d{6})$", ticker)
        if not match:
            continue
            
        month_code = match.group(1)
        year_code = match.group(2)
        type_char = match.group(3)
        strike_code = match.group(4)
        
        try:
            strike = float(strike_code)
            if strike > 20000:
                strike = strike / 100.0
        except ValueError:
            continue
            
        opt_type = "CALL" if type_char == "C" else "PUT"
        month_num = future_months.get(month_code, 1)
        year = int("20" + year_code)
            
        expiry_date = _get_dol_expiration(year, month_num)
        
        oi = 0
        for col_idx in (11, 5):
            if len(row) > col_idx:
                oi_str = str(row.iloc[col_idx]).replace('.', '').replace('-', '0').strip()
                try:
                    val = int(oi_str)
                    if val > oi:
                        oi = val
                except Exception:
                    pass
            
        if oi > 0:
            options.append({
                "ticker": ticker,
                "type": opt_type,
                "strike": strike,
                "expiry": expiry_date.isoformat(),
                "oi": oi
            })
            
    df = pd.DataFrame(options)
    print(f"B3 DOL Parser: {len(df)} opções de DOL extraídas com sucesso.")
    return df
