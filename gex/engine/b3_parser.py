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


def _get_oi_candidates():
    """
    Retorna a lista de arquivos de Posicoes em Aberto ordenados pela data do arquivo (mais recente primeiro).
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
            
    # Elimina duplicatas de caminhos
    candidates = list(set(candidates))
    candidates.sort(key=_extract_file_date_key, reverse=True)
    return candidates


def _find_latest_oi_file():
    candidates = _get_oi_candidates()
    return candidates[0] if candidates else None


def _get_ibov_expiration(year, month):
    """
    Calcula a data de vencimento de opcoes sobre IBOVESPA.
    Regra: Quarta-feira mais proxima do dia 15 do mes de vencimento.
    """
    d_15 = datetime.date(year, month, 15)
    days_to_wed = 2 - d_15.weekday()  # Wednesday is 2 (0=Monday, 6=Sunday)
    wed_current = d_15 + datetime.timedelta(days=days_to_wed)
    
    wed_prev = wed_current - datetime.timedelta(weeks=1)
    wed_next = wed_current + datetime.timedelta(weeks=1)
    
    candidates = [wed_prev, wed_current, wed_next]
    closest = min(candidates, key=lambda d: abs((d - d_15).days))
    return datetime.datetime(closest.year, closest.month, closest.day)


def _parse_single_csv(file_path):
    if not os.path.exists(file_path):
        return pd.DataFrame()
        
    print(f"B3 Parser: Lendo {os.path.basename(file_path)}...")
    
    header_idx = 0
    with open(file_path, 'r', encoding='latin1') as f:
        for i, line in enumerate(f):
            if line.startswith("Instrumento financeiro"):
                header_idx = i
                break
                
    try:
        pos = pd.read_csv(file_path, sep=';', encoding='latin1', skiprows=header_idx, low_memory=False)
    except Exception as e:
        print(f"B3 Parser: Erro ao ler CSV {file_path}: {e}")
        return pd.DataFrame()
    
    options = []
    month_codes = {
        'A': (1, 'CALL'), 'B': (2, 'CALL'), 'C': (3, 'CALL'), 'D': (4, 'CALL'),
        'E': (5, 'CALL'), 'F': (6, 'CALL'), 'G': (7, 'CALL'), 'H': (8, 'CALL'),
        'I': (9, 'CALL'), 'J': (10, 'CALL'), 'K': (11, 'CALL'), 'L': (12, 'CALL'),
        'M': (1, 'PUT'), 'N': (2, 'PUT'), 'O': (3, 'PUT'), 'P': (4, 'PUT'),
        'Q': (5, 'PUT'), 'R': (6, 'PUT'), 'S': (7, 'PUT'), 'T': (8, 'PUT'),
        'U': (9, 'PUT'), 'V': (10, 'PUT'), 'W': (11, 'PUT'), 'X': (12, 'PUT')
    }
    
    # Extrai o ano e mes de referencia do proprio arquivo se disponivel no nome
    ref_year = datetime.datetime.now().year
    ref_month = datetime.datetime.now().month
    match_file_date = re.search(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(file_path))
    if match_file_date:
        _, m_str, y_str = match_file_date.groups()
        ref_year = int(y_str)
        ref_month = int(m_str)

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
        year = ref_year
        if month_num < ref_month:
            year += 1
            
        expiry_date = _get_ibov_expiration(year, month_num)
        
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
    return df


def get_b3_options_data(current_ibov=186000, file_path=None):
    """
    Parseia o arquivo de Posicoes em aberto da B3.
    Se o arquivo especificado/mais recente estiver incompleto (0 opcoes), ativa fallback automatico para arquivos anteriores.
    """
    if file_path is not None:
        df = _parse_single_csv(file_path)
        print(f"B3 Parser: {len(df)} opcoes IBOV extraidas de {os.path.basename(file_path)}.")
        return df
        
    candidates = _get_oi_candidates()
    if not candidates:
        print("B3 Parser: ERRO - Nenhum arquivo 'Posicoes em aberto*.csv' encontrado.")
        return pd.DataFrame()
        
    for cand in candidates:
        df = _parse_single_csv(cand)
        if len(df) > 0:
            print(f"B3 Parser: {len(df)} opcoes IBOV extraidas com sucesso ({os.path.basename(cand)}).")
            return df
        else:
            print(f"B3 Parser: [Aviso] {os.path.basename(cand)} contem 0 opcoes IBOV (arquivo incompleto). Tentando proximo arquivo...")
            
    print("B3 Parser: ERRO - Nenhum arquivo de Posicoes em Aberto contem opcoes IBOV validas.")
    return pd.DataFrame()
