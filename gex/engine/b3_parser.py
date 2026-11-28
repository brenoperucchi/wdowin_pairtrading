import csv
import datetime
import glob
import io
import json
import os
import re
import pandas as pd

from .b3_dol_parser import parse_b3_oi

_GEX_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INSTRUMENTS_CACHE_PATH = os.path.join(_GEX_DIR, "data", "b3_ibov_instruments_cache.json")


def _load_ibov_catalog_cache() -> dict:
    if not os.path.exists(_INSTRUMENTS_CACHE_PATH):
        return {}
    try:
        with open(_INSTRUMENTS_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_ibov_catalog_cache(catalog: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_INSTRUMENTS_CACHE_PATH), exist_ok=True)
        with open(_INSTRUMENTS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=1, sort_keys=True)
    except Exception:
        pass


def _fetch_b3_instruments_for_date(date_iso: str) -> dict:
    """Baixa InstrumentsConsolidatedFile da B3 para `date_iso` e indexa opções IBOV por ISIN."""
    if not date_iso:
        return {}
    try:
        import requests

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://arquivos.b3.com.br/bdi/tabelas?lang=pt-BR",
        }
        r1 = requests.get(
            f"https://arquivos.b3.com.br/api/download/requestname?fileName=InstrumentsConsolidatedFile&date={date_iso}",
            headers=headers,
            timeout=15,
        )
        if r1.status_code != 200:
            return {}
        tok = (r1.json() or {}).get("token")
        if not tok:
            return {}
        r2 = requests.get(
            f"https://arquivos.b3.com.br/api/download/?token={tok}",
            headers=headers,
            timeout=45,
        )
        if r2.status_code != 200 or len(r2.content) < 10000:
            return {}

        lines = r2.content.decode("latin1", errors="ignore").splitlines()
        hdr_idx = None
        for i, ln in enumerate(lines[:10]):
            if "TckrSymb" in ln and "ISIN" in ln and "ExrcPric" in ln:
                hdr_idx = i
                break
        if hdr_idx is None:
            return {}

        out = {}
        reader = csv.DictReader(io.StringIO("\n".join(lines[hdr_idx:])), delimiter=";")
        for rec in reader:
            tk = (rec.get("TckrSymb") or "").strip()
            cat = (rec.get("SctyCtgyNm") or "").strip()
            if not tk.startswith("IBOV") or cat != "OPTION ON INDEX":
                continue
            isin = (rec.get("ISIN") or "").strip()
            if not isin:
                continue
            opt_tp = (rec.get("OptnTp") or "").strip().upper()
            if opt_tp not in ("CALL", "PUT"):
                sg = (rec.get("SgmtNm") or "").upper()
                opt_tp = "PUT" if "PUT" in sg else ("CALL" if "CALL" in sg else "")
            if not opt_tp:
                continue
            exrc_raw = (rec.get("ExrcPric") or "").strip().replace(",", ".")
            exp_dt = (rec.get("XprtnDt") or "").strip()[:10]
            if not exrc_raw or not exp_dt:
                continue
            try:
                strike = float(exrc_raw)
            except ValueError:
                continue
            out[isin] = {
                "ticker": tk,
                "type": opt_tp,
                "strike": strike,
                "expiry": exp_dt,
            }
        return out
    except Exception:
        return {}


def _fetch_mt5_ibov_metadata() -> dict:
    """Fallback secundário via MT5: mapeia ticker IBOV -> {strike, expiry}."""
    out = {}
    try:
        import MetaTrader5 as mt5
        from .mt5_prices import init_mt5_robust

        opened_here = False
        if mt5.terminal_info() is None:
            if not init_mt5_robust():
                return out
            opened_here = True
        try:
            syms = mt5.symbols_get("IBOV*") or []
            for s in syms:
                if s.option_strike > 0 and s.expiration_time:
                    exp_dt = datetime.datetime.fromtimestamp(
                        s.expiration_time, datetime.timezone.utc
                    ).strftime("%Y-%m-%d")
                    out[s.name] = {
                        "strike": float(s.option_strike),
                        "expiry": exp_dt,
                    }
        finally:
            if opened_here:
                mt5.shutdown()
    except Exception:
        pass
    return out


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
        pos = pd.read_csv(file_path, sep=';', encoding='latin1', skiprows=header_idx, dtype=str, low_memory=False)
    except Exception as e:
        print(f"B3 Parser: Erro ao ler CSV {file_path}: {e}")
        return pd.DataFrame()
    
    month_codes = {
        'A': (1, 'CALL'), 'B': (2, 'CALL'), 'C': (3, 'CALL'), 'D': (4, 'CALL'),
        'E': (5, 'CALL'), 'F': (6, 'CALL'), 'G': (7, 'CALL'), 'H': (8, 'CALL'),
        'I': (9, 'CALL'), 'J': (10, 'CALL'), 'K': (11, 'CALL'), 'L': (12, 'CALL'),
        'M': (1, 'PUT'), 'N': (2, 'PUT'), 'O': (3, 'PUT'), 'P': (4, 'PUT'),
        'Q': (5, 'PUT'), 'R': (6, 'PUT'), 'S': (7, 'PUT'), 'T': (8, 'PUT'),
        'U': (9, 'PUT'), 'V': (10, 'PUT'), 'W': (11, 'PUT'), 'X': (12, 'PUT')
    }
    
    # Extrai a data de referencia do proprio arquivo se disponivel no nome
    ref_year = datetime.datetime.now().year
    ref_month = datetime.datetime.now().month
    csv_date_iso = None
    match_file_date = re.search(r"(\d{2})-(\d{2})-(\d{4})", os.path.basename(file_path))
    if match_file_date:
        d_str, m_str, y_str = match_file_date.groups()
        ref_year = int(y_str)
        ref_month = int(m_str)
        csv_date_iso = f"{y_str}-{m_str}-{d_str}"

    candidates = []
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
            
        oi = parse_b3_oi(row.iloc[11]) if len(row) > 11 else 0
        if oi <= 0:
            continue

        isin = str(row.iloc[1]).strip() if len(row) > 1 else ""
        month_code, strike_code = match.groups()
        candidates.append((ticker, isin, month_code, strike_code, oi))

    catalog = _load_ibov_catalog_cache()
    if candidates and csv_date_iso and any(isin not in catalog for _, isin, _, _, _ in candidates):
        fetched = _fetch_b3_instruments_for_date(csv_date_iso)
        if fetched:
            catalog.update(fetched)
            _save_ibov_catalog_cache(catalog)

    mt5_meta = {}
    if candidates and any(isin not in catalog for _, isin, _, _, _ in candidates):
        mt5_meta = _fetch_mt5_ibov_metadata()

    options = []
    n_isin = n_mt5 = n_leg = 0
    learned = {}
    for ticker, isin, month_code, strike_code, oi in candidates:
        month_num, opt_type = month_codes[month_code]
        cat_hit = catalog.get(isin)
        if cat_hit is not None:
            strike = float(cat_hit["strike"])
            expiry_iso = cat_hit["expiry"][:10] + "T00:00:00"
            opt_type = cat_hit["type"]
            n_isin += 1
        elif ticker in mt5_meta:
            strike = float(mt5_meta[ticker]["strike"])
            expiry_iso = mt5_meta[ticker]["expiry"] + "T00:00:00"
            n_mt5 += 1
            if isin:
                # Contingência para a B3 sem publicar o InstrumentsConsolidatedFile (parou em 12/11/2026):
                # guarda o que o MT5 resolveu, por ISIN, para os próximos dias e replays não dependerem dele.
                learned[isin] = {
                    "ticker": ticker,
                    "type": opt_type,
                    "strike": strike,
                    "expiry": mt5_meta[ticker]["expiry"],
                }
        else:
            strike_val = int(strike_code) * 1000
            if len(strike_code) == 2 and strike_val < 30000:
                strike_val = int(strike_code) * 10000
            if strike_val < 100000:
                continue
            strike = float(strike_val)
            yr = ref_year + (1 if month_num < ref_month else 0)
            expiry_iso = _get_ibov_expiration(yr, month_num).isoformat()
            n_leg += 1

        options.append({
            "ticker": ticker,
            "type": opt_type,
            "strike": strike,
            "expiry": expiry_iso,
            "oi": oi
        })

    if learned:
        catalog.update(learned)
        _save_ibov_catalog_cache(catalog)

    if options:
        print(f"B3 Parser: Resolucao IBOV -> {n_isin} via B3/ISIN, {n_mt5} via MT5, {n_leg} fallback legado.")
        if n_leg:
            print(
                f"B3 Parser: ATENCAO: {n_leg} de {len(options)} opcoes IBOV foram resolvidas pelo fallback legado "
                "(strike/vencimento deduzidos do ticker, semanais descartadas). As Walls podem divergir. "
                "Causa provavel: catalogo da B3 indisponivel e MT5 sem os simbolos."
            )

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
