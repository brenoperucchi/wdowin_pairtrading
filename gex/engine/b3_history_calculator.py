"""
b3_history_calculator.py - Motor de Cálculo Histórico de GEX da B3 (WIN / IBOV e WDO / DOL) para 2026 YTD.

Garante:
1. Preservação integral (100% bit-a-bit) dos pregões já calculados e validados na base existente
   (2026-05-07 a 2026-11-05), mantendo total alinhamento com os backtests do MT5 e a carteira de EAs.
2. Backfill dos pregões anteriores (2026-01-02 a 2026-05-06) e posteriores (2026-11-06) usando
   EXATAMENTE a mesma metodologia oficial de produção (`main.py`, `walls_calculator.py` e `main_dol.py`):
   - Preços M5 sincronizados às 16:55 das séries nominais sem ajuste de rolagem (`IBOV`, `WIN$N`, `WDO$N`).
   - Alinhamento temporal sem look-ahead: Posições em Aberto + Fechamento 16:55 de `D-1` (`ref_oi_date`)
     projetam as MagicWalls para o pregão `D` (`session_date`).
   - Ciclo Selic histórico correto por vencimento (14.50% até 17/06/2026, 14.25% até 12/08/2026, 14.00% após).
   - Agrupamento `strike_base_10`, `carry_ratio` na rolagem do WDO e seleção do GammaFlip mais próximo do preço.
"""

import os
import sys
import re
import io
import json
import glob
import subprocess
import datetime
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from gex.engine.b3_parser import _get_ibov_expiration
from gex.engine.b3_dol_parser import _get_dol_expiration
from gex.engine.walls_calculator import calculate_gex_profile
from gex.engine.black76 import black76_gamma
from gex.engine.mt5_prices import (
    init_mt5_robust,
    get_b3_expected_win_contract,
    get_b3_expected_wdo_contract,
)
from gex.engine.mt5_exporter import get_mt5_common_files_dir, _norm_wall_type

DATA_DIR = os.path.join(PROJECT_ROOT, "gex", "data")
MT5_FILES_DIR = os.path.join(PROJECT_ROOT, "mt5", "Files")

WDO_MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"
}


def _wdo_symbol_for_expiry(expiry_str: str) -> str:
    d = datetime.date.fromisoformat(expiry_str[:10])
    code = WDO_MONTH_CODES[d.month]
    return f"WDO{code}{str(d.year)[2:]}"


def get_selic_for_date(d_str: str) -> float:
    """Mesma regra oficial de ciclos Selic de 2026."""
    if d_str < "2026-06-18":
        return 0.1450
    elif d_str < "2026-08-13":
        return 0.1425
    return 0.1400


def load_mt5_synced_m5_prices():
    """
    Carrega os preços M5 sincronizados às 16:55 (com fallback para o fechamento D1 do próprio dia)
    das séries NOMINAIS sem ajuste (`IBOV`, `WIN$N` / `WIN@N`, `WDO$N` / `WDO@N`).
    """
    prices_ibov = {}
    prices_win = {}
    prices_wdo = {}

    print("[MT5] Conectando ao terminal para carregar preços nominais sincronizados às 16:55 (M5)...")
    if not init_mt5_robust():
        print("[MT5] Aviso: Não foi possível inicializar o MT5.")
        return prices_ibov, prices_win, prices_wdo

    utc_from = datetime.datetime(2025, 12, 15, tzinfo=datetime.timezone.utc)
    utc_to = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)

    def _extract_m5_1655_and_d1(symbols):
        out = {}
        for sym in symbols:
            mt5.symbol_select(sym, True)
            r_m5 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_M5, utc_from, utc_to)
            if r_m5 is not None and len(r_m5) > 0:
                last_bar_per_day = {}
                for b in r_m5:
                    dt = datetime.datetime.fromtimestamp(b[0], datetime.timezone.utc)
                    d_str = dt.strftime("%Y-%m-%d")
                    last_bar_per_day[d_str] = float(b[4])
                    if dt.hour == 16 and dt.minute == 55:
                        out[d_str] = float(b[4])
                for d_str, val in last_bar_per_day.items():
                    if d_str not in out:
                        out[d_str] = val
            r_d1 = mt5.copy_rates_range(sym, mt5.TIMEFRAME_D1, utc_from, utc_to)
            if r_d1 is not None and len(r_d1) > 0:
                for b in r_d1:
                    d_str = datetime.datetime.fromtimestamp(b[0], datetime.timezone.utc).strftime("%Y-%m-%d")
                    if d_str not in out:
                        out[d_str] = float(b[4])
            if len(out) >= 150:
                break
        return out

    prices_ibov = _extract_m5_1655_and_d1(["IBOV"])
    # Prioridade estrita para WIN$N / WIN@N (série nominal sem ajuste de rolagem)
    prices_win = _extract_m5_1655_and_d1(["WIN$N", "WIN@N"])
    # Prioridade estrita para WDO$N / WDO@N (série nominal sem ajuste de rolagem)
    prices_wdo = _extract_m5_1655_and_d1(["WDO$N", "WDO@N"])

    mt5.shutdown()
    print(f"[MT5] Preços 16:55 carregados: {len(prices_ibov)} IBOV, {len(prices_win)} WIN$N, {len(prices_wdo)} WDO$N")
    return prices_ibov, prices_win, prices_wdo


def load_existing_validated_history():
    """
    Carrega os níveis históricos já calculados e validados no repositório (HEAD)
    para preservar 100% dos pregões já existentes (2026-05-07 a 2026-11-05).
    """
    existing_win = {}
    existing_wdo = {}

    try:
        old_win_str = subprocess.check_output(
            ["git", "show", "HEAD:mt5/Files/jumba_gex_win_history.csv"],
            cwd=PROJECT_ROOT, text=True, encoding="utf-8", errors="ignore"
        )
        for line in old_win_str.splitlines():
            if "session_date" in line or len(line.strip()) < 5:
                continue
            parts = line.strip().split(";")
            if len(parts) >= 4:
                d = parts[0]
                existing_win.setdefault(d, []).append({
                    "type": _norm_wall_type(parts[1]),
                    "price": float(parts[2]),
                    "width": int(parts[3]),
                    "gex": 0.0,
                })
    except Exception as e:
        print(f"[Aviso] Não foi possível ler HEAD:mt5/Files/jumba_gex_win_history.csv: {e}")

    try:
        old_wdo_str = subprocess.check_output(
            ["git", "show", "HEAD:mt5/Files/jumba_gex_wdo_history.csv"],
            cwd=PROJECT_ROOT, text=True, encoding="utf-8", errors="ignore"
        )
        for line in old_wdo_str.splitlines():
            if "session_date" in line or len(line.strip()) < 5:
                continue
            parts = line.strip().split(";")
            if len(parts) >= 4:
                d = parts[0]
                existing_wdo.setdefault(d, []).append({
                    "type": _norm_wall_type(parts[1]),
                    "price": float(parts[2]),
                    "width": int(parts[3]),
                    "gex": 0.0,
                })
    except Exception as e:
        print(f"[Aviso] Não foi possível ler HEAD:mt5/Files/jumba_gex_wdo_history.csv: {e}")

    return existing_win, existing_wdo


def parse_b3_file_fast(file_path: str, ref_date: datetime.date):
    """
    Parser rápido (1 leitura com pré-filtragem booleana) idêntico a `b3_parser.py` e `b3_dol_parser.py`.
    """
    header_idx = 0
    with open(file_path, "r", encoding="latin1") as f:
        for i, line in enumerate(f):
            if "Instrumento financeiro" in line:
                header_idx = i
                break

    pos = pd.read_csv(file_path, sep=";", encoding="latin1", skiprows=header_idx, low_memory=False)
    tickers = pos.iloc[:, 0].astype(str).str.strip()
    segments = pos.iloc[:, 4].astype(str).str.strip()

    # 1. Opções IBOV
    ibov_mask = tickers.str.startswith("IBOV") & (
        segments.str.contains("EQUITY CALL") | segments.str.contains("EQUITY PUT")
    )
    df_ib = pos[ibov_mask]

    month_codes = {
        "A": (1, "CALL"), "B": (2, "CALL"), "C": (3, "CALL"), "D": (4, "CALL"),
        "E": (5, "CALL"), "F": (6, "CALL"), "G": (7, "CALL"), "H": (8, "CALL"),
        "I": (9, "CALL"), "J": (10, "CALL"), "K": (11, "CALL"), "L": (12, "CALL"),
        "M": (1, "PUT"), "N": (2, "PUT"), "O": (3, "PUT"), "P": (4, "PUT"),
        "Q": (5, "PUT"), "R": (6, "PUT"), "S": (7, "PUT"), "T": (8, "PUT"),
        "U": (9, "PUT"), "V": (10, "PUT"), "W": (11, "PUT"), "X": (12, "PUT")
    }

    ref_year = ref_date.year
    ref_month = ref_date.month

    ibov_opts = []
    for _, row in df_ib.iterrows():
        t = str(row.iloc[0]).strip()
        m = re.match(r"^IBOV([A-X])(\d+)$", t)
        if not m:
            continue
        m_code, s_code = m.groups()
        strike = int(s_code) * 1000
        if len(s_code) == 2 and strike < 30000:
            strike *= 10
        if strike < 100000:
            continue
        m_num, o_type = month_codes[m_code]
        yr = ref_year + (1 if m_num < ref_month else 0)
        exp_dt = _get_ibov_expiration(yr, m_num).isoformat()
        oi_str = str(row.iloc[11]).replace(".", "").replace("-", "0").strip()
        try:
            oi = int(oi_str)
        except Exception:
            oi = 0
        if oi > 0:
            ibov_opts.append({
                "ticker": t,
                "type": o_type,
                "strike": float(strike),
                "expiry": exp_dt,
                "oi": oi,
            })

    df_ibov_opts = pd.DataFrame(ibov_opts)

    # 2. Opções DOL
    dol_mask = tickers.str.startswith("DOL")
    df_dl = pos[dol_mask]
    future_months = {
        "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
        "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12
    }

    dol_opts = []
    for _, row in df_dl.iterrows():
        t = str(row.iloc[0]).strip()
        m = re.match(r"^DOL([A-Z])(\d{2})([CP])(\d{6})$", t)
        if not m:
            continue
        m_code, y_code, t_char, s_code = m.groups()
        try:
            strike = float(s_code)
            if strike > 20000:
                strike /= 100.0
        except Exception:
            continue
        o_type = "CALL" if t_char == "C" else "PUT"
        m_num = future_months.get(m_code, 1)
        yr = int("20" + y_code)
        exp_dt = _get_dol_expiration(yr, m_num).isoformat()
        oi = 0
        for c_idx in (11, 5):
            if len(row) > c_idx:
                try:
                    val = int(str(row.iloc[c_idx]).replace(".", "").replace("-", "0").strip())
                    if val > oi:
                        oi = val
                except Exception:
                    pass
        if oi > 0:
            dol_opts.append({
                "ticker": t,
                "type": o_type,
                "strike": float(strike),
                "expiry": exp_dt,
                "oi": oi,
            })

    df_dol_opts = pd.DataFrame(dol_opts)
    return df_ibov_opts, df_dol_opts


def calculate_dol_walls_official(df_dol: pd.DataFrame, current_wdo: float, ref_date: datetime.date):
    """
    Replica exatamente a metodologia oficial do `main_dol.py`:
    - Filtra vencimentos `> ref_date` (ou `>= ref_date` em contingência)
    - Detecta o contrato WDO esperado pelo calendário oficial da B3 (`get_b3_expected_wdo_contract`)
      e aplica `carry_ratio` na rolagem de último dia útil do mês
    - Agrupa strikes de 10 em 10 pontos (`strike_base_10 = (strike / 10).round() * 10`)
    - Seleciona 16 strikes ao redor do ATM
    - Calcula a Market Gamma Curve com `black76_gamma` oficial e seleciona o `GammaFlip` mais próximo
      de `current_wdo` (`dist < best_flip_dist`).
    """
    if df_dol.empty or current_wdo <= 0:
        return []

    ref_date_str = ref_date.isoformat()
    df_future = df_dol[df_dol["expiry"].str[:10] > ref_date_str].copy()
    df_valid = df_future if not df_future.empty else df_dol[df_dol["expiry"].str[:10] >= ref_date_str].copy()
    if df_valid.empty:
        return []

    r = get_selic_for_date(ref_date_str)
    iv = 0.12
    multiplier = 50

    active_contract, _ = get_b3_expected_wdo_contract(ref_date)
    all_expiries = sorted(df_valid["expiry"].unique())
    front_month = all_expiries[0]
    front_wdo_sym = _wdo_symbol_for_expiry(front_month)

    selected_expiries = [front_month]
    if front_wdo_sym != active_contract and len(all_expiries) > 1:
        for exp_cand in all_expiries[1:]:
            if _wdo_symbol_for_expiry(exp_cand) == active_contract:
                selected_expiries.append(exp_cand)
                break

    df_front = df_valid[df_valid["expiry"].isin(selected_expiries)].copy()

    expiry_meta = {}
    for exp_val in selected_expiries:
        opt_wdo_sym = _wdo_symbol_for_expiry(exp_val)
        exp_dt = datetime.date.fromisoformat(exp_val[:10])
        b_days = max(1, int(np.busday_count(ref_date_str, exp_dt.isoformat())))
        t_val = max(1 / 252, b_days / 252)
        if opt_wdo_sym == active_contract:
            carry_ratio = 1.0
        else:
            carry_ratio = (1 + r) ** (21 / 252)
        expiry_meta[exp_val] = {"T": t_val, "carry_ratio": carry_ratio}

    df_front["carry_ratio"] = df_front["expiry"].map(lambda e: expiry_meta[e]["carry_ratio"])
    df_front["T_opt"] = df_front["expiry"].map(lambda e: expiry_meta[e]["T"])
    df_front["strike_wdo"] = df_front["strike"] * df_front["carry_ratio"]
    df_front["strike_base_10"] = (df_front["strike"] / 10).round() * 10
    df_front["strike_round"] = ((df_front["strike_base_10"] * df_front["carry_ratio"]) * 2).round() / 2

    gex_per_strike = {}
    for strike_round, group in df_front.groupby("strike_round"):
        gex_net = 0.0
        base_strike_rep = int(group["strike_base_10"].iloc[0])
        for _, row in group.iterrows():
            gamma = black76_gamma(F=current_wdo, K=float(row["strike_wdo"]), T=float(row["T_opt"]), sigma=iv)
            gex_contrib = row["oi"] * gamma * (current_wdo ** 2) * 0.01 * multiplier
            if row["type"] == "PUT":
                gex_contrib = -gex_contrib
            gex_net += gex_contrib

        gex_per_strike[strike_round] = {
            "gex_net": gex_net,
            "abs_gex": abs(gex_net),
            "base_strike": base_strike_rep,
        }

    if not gex_per_strike:
        return []

    all_strikes = sorted(gex_per_strike.keys())
    atm_strike = min(all_strikes, key=lambda s: abs(s - current_wdo))
    atm_idx = all_strikes.index(atm_strike)

    num_walls = 16
    start_idx = max(0, atm_idx - num_walls // 2)
    end_idx = min(len(all_strikes), start_idx + num_walls)
    start_idx = max(0, end_idx - num_walls)
    selected_strikes = all_strikes[start_idx:end_idx]

    strike_gex_list = [(s, gex_per_strike[s]) for s in selected_strikes]
    sorted_by_gex = sorted(strike_gex_list, key=lambda x: x[1]["abs_gex"], reverse=True)

    width_map = {}
    for rank, (s, _) in enumerate(sorted_by_gex):
        width_map[s] = 3 if rank == 0 else (2 if rank <= 2 else 1)

    walls_basic = []
    for strike_round in selected_strikes:
        info = gex_per_strike[strike_round]
        walls_basic.append({
            "price": round(float(strike_round), 2),
            "type": "Wall",
            "width": width_map.get(strike_round, 1),
            "strike_spy": int(info["base_strike"]),
            "gex": info["gex_net"],
        })

    walls_basic_sorted = sorted(walls_basic, key=lambda x: x["price"])
    walls = []
    for i in range(len(walls_basic_sorted)):
        walls.append(walls_basic_sorted[i])
        if i < len(walls_basic_sorted) - 1:
            mid = (walls_basic_sorted[i]["price"] + walls_basic_sorted[i + 1]["price"]) / 2
            walls.append({
                "price": round(mid, 2),
                "type": "MidWall",
                "width": 1,
                "gex": 0.0,
            })

    # Market Gamma Curve na janela operacional (idêntico a main_dol.py)
    df_local = df_front[df_front["strike_round"].isin(selected_strikes)].copy()
    if df_local.empty:
        df_local = df_front

    min_wall_wdo = float(min(selected_strikes))
    max_wall_wdo = float(max(selected_strikes))
    f_low = max(current_wdo * 0.96, min_wall_wdo)
    f_high = min(current_wdo * 1.04, max_wall_wdo)
    if f_low >= f_high:
        f_low = current_wdo * 0.97
        f_high = current_wdo * 1.03

    sweep_prices = np.linspace(f_low, f_high, 200)
    F_sweep = sweep_prices[:, None]

    k_arr = df_local["strike_wdo"].to_numpy(dtype=float)[None, :]
    t_arr = df_local["T_opt"].to_numpy(dtype=float)[None, :]
    oi_arr = df_local["oi"].to_numpy(dtype=float)
    type_sign = np.where(df_local["type"].to_numpy() == "PUT", -1.0, 1.0)
    signed_oi = (oi_arr * type_sign)[None, :]

    # Mesma fórmula exata de black76_gamma (gex/engine/black76.py)
    d1 = (np.log(F_sweep / k_arr) + 0.5 * (iv ** 2) * t_arr) / (iv * np.sqrt(t_arr))
    n_prime_d1 = (1.0 / np.sqrt(2 * np.pi)) * np.exp(-0.5 * (d1 ** 2))
    gamma_mat = np.exp(-0.1425 * t_arr) * n_prime_d1 / (F_sweep * iv * np.sqrt(t_arr))
    contrib_mat = signed_oi * gamma_mat * (F_sweep ** 2) * 0.01 * multiplier
    gex_values = np.sum(contrib_mat, axis=1)

    max_gamma_idx = int(np.argmax(gex_values))
    min_gamma_idx = int(np.argmin(gex_values))
    max_gamma_dol = round(float(sweep_prices[max_gamma_idx]), 2)
    min_gamma_dol = round(float(sweep_prices[min_gamma_idx]), 2)

    flip_dol = None
    best_flip_dist = float("inf")
    for i in range(len(gex_values) - 1):
        if gex_values[i] * gex_values[i + 1] < 0:
            x0, x1 = sweep_prices[i], sweep_prices[i + 1]
            y0, y1 = gex_values[i], gex_values[i + 1]
            cross = x0 - y0 * (x1 - x0) / (y1 - y0)
            dist = abs(cross - current_wdo)
            if dist < best_flip_dist:
                best_flip_dist = dist
                flip_dol = round(float(cross), 2)

    if flip_dol is None:
        near_mask = (sweep_prices >= current_wdo * 0.98) & (sweep_prices <= current_wdo * 1.02)
        if np.any(near_mask):
            near_prices = sweep_prices[near_mask]
            near_abs_gex = np.abs(gex_values[near_mask])
            flip_dol = round(float(near_prices[int(np.argmin(near_abs_gex))]), 2)
        else:
            flip_dol = round(float(current_wdo), 2)

    walls.append({"price": max_gamma_dol, "type": "MaxGamma", "width": 3, "gex": float(gex_values[max_gamma_idx])})
    walls.append({"price": min_gamma_dol, "type": "MinGamma", "width": 3, "gex": float(gex_values[min_gamma_idx])})
    walls.append({"price": flip_dol, "type": "GammaFlip", "width": 2, "gex": 0.0})

    return walls


def extract_special_metrics(walls):
    flip = max_g = min_g = None
    for w in walls:
        t = _norm_wall_type(w.get("type", ""))
        if t == "GammaFlip":
            flip = w["price"]
        elif t == "MaxGamma":
            max_g = w["price"]
        elif t == "MinGamma":
            min_g = w["price"]
    return flip, max_g, min_g


def backfill_b3_gex_history():
    """
    Processa todos os 212 pregões de 2026:
    - Preserva 100% dos pregões já calculados na base existente (2026-05-07 a 2026-11-05).
    - Calcula os pregões de 2026-01-02 a 2026-05-06 e 2026-11-06 usando a metodologia oficial
      (D-1 OI + M5 16:55 de `WIN$N` / `WDO$N` / `IBOV`).
    """
    prices_ibov, prices_win, prices_wdo = load_mt5_synced_m5_prices()
    existing_win, existing_wdo = load_existing_validated_history()
    print(f"[Base Existente] Preservados do HEAD: {len(existing_win)} sessões WIN, {len(existing_wdo)} sessões WDO")

    files = glob.glob(os.path.join(DATA_DIR, "Posições em aberto-*.csv"))
    dated_files = []
    for f in files:
        m = re.search(r"Posições em aberto-(\d{2})-(\d{2})-(\d{4})\.csv", f)
        if m:
            d, mo, y = m.groups()
            dated_files.append((f"{y}-{mo}-{d}", datetime.date(int(y), int(mo), int(d)), f))

    dated_files.sort(key=lambda x: x[0])

    print("=" * 68)
    print(f"  PROCESSAMENTO HISTÓRICO GEX B3 - TOTAL: {len(dated_files)} PREGÕES (YTD 2026)")
    print("=" * 68)

    # Inicializa os mapas com os pregões já validados
    win_history = dict(existing_win)
    wdo_history = dict(existing_wdo)
    summary_rows = []

    t_start = datetime.datetime.now()

    for idx, (session_str, session_obj, f_path_today) in enumerate(dated_files):
        # Na metodologia oficial (main.py / main_dol.py / mt5_exporter.py):
        # O pregão `session_date` (índice `idx`) opera com as posições em aberto e o fechamento 16:55
        # do pregão anterior `ref_oi_date` (índice `idx - 1`).
        # Para o primeiro pregão do ano (2026-01-02, idx == 0), usa o próprio arquivo de 02/01/2026.
        if idx > 0:
            ref_str, ref_obj, ref_path = dated_files[idx - 1]
        else:
            ref_str, ref_obj, ref_path = session_str, session_obj, f_path_today

        s_ibov = prices_ibov.get(ref_str) or prices_ibov.get(session_str) or 160000.0
        r_selic = get_selic_for_date(session_str)

        _, _, win_expiry_date = get_b3_expected_win_contract(ref_obj)
        win_expiry_days = max(1, int(np.busday_count(ref_obj.isoformat(), win_expiry_date.isoformat())))
        theo_win_factor = (1 + r_selic) ** (win_expiry_days / 252)

        f_win = prices_win.get(ref_str) or prices_win.get(session_str)
        if f_win is None or not (0.995 <= (f_win / s_ibov) <= 1.045):
            f_win = round(s_ibov * theo_win_factor, 0)

        wdo_price = prices_wdo.get(ref_str) or prices_wdo.get(session_str) or 5400.0

        has_preserved_win = session_str in existing_win
        has_preserved_wdo = session_str in existing_wdo

        if has_preserved_win and has_preserved_wdo:
            win_flip, win_max_g, win_min_g = extract_special_metrics(existing_win[session_str])
            dol_flip, dol_max_g, dol_min_g = extract_special_metrics(existing_wdo[session_str])
            ib_count = -1
            dl_count = -1
        else:
            df_ibov_opts, df_dol_opts = parse_b3_file_fast(ref_path, ref_obj)
            ib_count = len(df_ibov_opts)
            dl_count = len(df_dol_opts)

            # 1. Cálculo WIN (se ainda não estiver na base validada)
            if not has_preserved_win:
                if not df_ibov_opts.empty:
                    # Filtra vencimentos futuros em relação a session_str (igual a main.py linha 249)
                    df_fut_ib = df_ibov_opts[df_ibov_opts["expiry"].str[:10] > session_str].copy()
                    df_use_ib = df_fut_ib if not df_fut_ib.empty else df_ibov_opts[df_ibov_opts["expiry"].str[:10] >= ref_str].copy()

                    # Determina expiry_days real da série front-month
                    exp_days_opt = 20
                    if not df_use_ib.empty:
                        front_exp_ib = sorted(df_use_ib["expiry"].unique())[0]
                        exp_dt_ib = datetime.date.fromisoformat(front_exp_ib[:10])
                        exp_days_opt = max(1, int(np.busday_count(ref_str, exp_dt_ib.isoformat())))

                    old_stdout = sys.stdout
                    sys.stdout = io.StringIO()
                    try:
                        walls_win = calculate_gex_profile(
                            options_df=df_use_ib,
                            current_win=f_win,
                            current_ibov=s_ibov,
                            iv=0.20,
                            expiry_days=exp_days_opt,
                            r=r_selic,
                            use_anchored_factor=True,
                            ref_date=ref_obj,
                        )
                    finally:
                        sys.stdout = old_stdout
                    win_history[session_str] = walls_win
                elif win_history:
                    prev_d = max(k for k in win_history.keys() if k < session_str)
                    win_history[session_str] = win_history[prev_d]

            win_flip, win_max_g, win_min_g = extract_special_metrics(win_history.get(session_str, []))

            # 2. Cálculo WDO (se ainda não estiver na base validada)
            if not has_preserved_wdo:
                if not df_dol_opts.empty:
                    walls_dol = calculate_dol_walls_official(df_dol_opts, wdo_price, ref_obj)
                    wdo_history[session_str] = walls_dol
                elif wdo_history:
                    prev_d = max(k for k in wdo_history.keys() if k < session_str)
                    wdo_history[session_str] = wdo_history[prev_d]

            dol_flip, dol_max_g, dol_min_g = extract_special_metrics(wdo_history.get(session_str, []))

        summary_rows.append({
            "date": session_str,
            "ref_oi_date": ref_str,
            "source": "PRESERVED_HEAD" if (has_preserved_win and has_preserved_wdo) else "BACKFILLED_B3",
            "s_ibov": s_ibov,
            "f_win": f_win,
            "win_flip": win_flip,
            "win_max_gamma": win_max_g,
            "win_min_gamma": win_min_g,
            "wdo_close": wdo_price,
            "dol_flip": dol_flip,
            "dol_max_gamma": dol_max_g,
            "dol_min_gamma": dol_min_g,
            "ibov_options_count": ib_count,
            "dol_options_count": dl_count,
        })

        step_num = idx + 1
        if step_num % 20 == 0 or step_num == len(dated_files):
            tag = "HEAD" if (has_preserved_win and has_preserved_wdo) else "CALC"
            print(
                f"[{step_num:3d}/{len(dated_files)}] {session_str} ({tag}) | "
                f"IBOV: {s_ibov:6.0f} | WIN Flip: {win_flip or 0:6.0f} | "
                f"WDO: {wdo_price:6.1f} | DOL Flip: {dol_flip or 0:6.1f}",
                flush=True,
            )

    # 3. Exportar jumba_gex_win_history.csv
    common_dir = get_mt5_common_files_dir()
    win_lines = ["session_date;type;price;width"]
    for d in sorted(win_history.keys()):
        for w in win_history[d]:
            w_type = _norm_wall_type(w.get("type", "Wall"))
            w_price = float(w.get("price", 0.0))
            w_width = int(w.get("width", 1))
            win_lines.append(f"{d};{w_type};{w_price:.2f};{w_width}")

    win_content = "\n".join(win_lines) + "\n"
    for target_dir in (MT5_FILES_DIR, common_dir):
        path = os.path.join(target_dir, "jumba_gex_win_history.csv")
        with open(path, "w", encoding="ascii", errors="ignore") as f:
            f.write(win_content)

    # 4. Exportar jumba_gex_wdo_history.csv
    wdo_lines = ["session_date;type;price;width"]
    for d in sorted(wdo_history.keys()):
        for w in wdo_history[d]:
            w_type = _norm_wall_type(w.get("type", "Wall"))
            w_price = float(w.get("price", 0.0))
            w_width = int(w.get("width", 1))
            wdo_lines.append(f"{d};{w_type};{w_price:.2f};{w_width}")

    wdo_content = "\n".join(wdo_lines) + "\n"
    for target_dir in (MT5_FILES_DIR, common_dir):
        path = os.path.join(target_dir, "jumba_gex_wdo_history.csv")
        with open(path, "w", encoding="ascii", errors="ignore") as f:
            f.write(wdo_content)

    # 5. Exportar espelhos JSON (jumba_gex_win_history.json, jumba_gex_wdo_history.json, jumba_gex_win_wdo_history.json)
    def _build_sessions_json(hist_dict, ticker_label):
        sessions_out = {}
        for d in sorted(hist_dict.keys()):
            w_list = [
                {
                    "type": _norm_wall_type(w.get("type", "Wall")),
                    "price": round(float(w.get("price", 0.0)), 2),
                    "width": int(w.get("width", 1)),
                }
                for w in hist_dict[d]
            ]
            fl, mx, mn = extract_special_metrics(w_list)
            sessions_out[d] = {
                "session_date": d,
                "ticker": ticker_label,
                "total_levels": len(w_list),
                "gamma_flip": round(float(fl), 2) if fl is not None else None,
                "max_gamma": round(float(mx), 2) if mx is not None else None,
                "min_gamma": round(float(mn), 2) if mn is not None else None,
                "walls": w_list,
            }
        dates_sorted = sorted(sessions_out.keys())
        return {
            "ticker": ticker_label,
            "from_date": dates_sorted[0] if dates_sorted else None,
            "to_date": dates_sorted[-1] if dates_sorted else None,
            "total_sessions": len(dates_sorted),
            "sessions": sessions_out,
        }

    win_json_obj = _build_sessions_json(win_history, "WIN")
    wdo_json_obj = _build_sessions_json(wdo_history, "WDO")
    all_dates_union = sorted(set(win_history.keys()) | set(wdo_history.keys()))
    by_date_obj = {}
    for d in all_dates_union:
        entry = {}
        if d in win_json_obj["sessions"]:
            entry["WIN"] = win_json_obj["sessions"][d]
        if d in wdo_json_obj["sessions"]:
            entry["WDO"] = wdo_json_obj["sessions"][d]
        by_date_obj[d] = entry

    combined_json_obj = {
        "metadata": {
            "description": "Histórico Completo Calculado de MagicWalls GEX (Mini-Índice WIN e Mini-Dólar WDO)",
            "from_date": all_dates_union[0] if all_dates_union else None,
            "to_date": all_dates_union[-1] if all_dates_union else None,
            "total_sessions": len(all_dates_union),
            "win_sessions": len(win_json_obj["sessions"]),
            "wdo_sessions": len(wdo_json_obj["sessions"]),
        },
        "WIN": win_json_obj["sessions"],
        "WDO": wdo_json_obj["sessions"],
        "by_date": by_date_obj,
    }

    for target_dir in (MT5_FILES_DIR, common_dir):
        with open(os.path.join(target_dir, "jumba_gex_win_history.json"), "w", encoding="utf-8") as f:
            json.dump(win_json_obj, f, indent=2, ensure_ascii=False)
        with open(os.path.join(target_dir, "jumba_gex_wdo_history.json"), "w", encoding="utf-8") as f:
            json.dump(wdo_json_obj, f, indent=2, ensure_ascii=False)
        with open(os.path.join(target_dir, "jumba_gex_win_wdo_history.json"), "w", encoding="utf-8") as f:
            json.dump(combined_json_obj, f, indent=2, ensure_ascii=False)

    # 6. Salvar resumo consolidado de mercado
    df_summary = pd.DataFrame(summary_rows)
    summary_path = os.path.join(DATA_DIR, "b3_gex_history_2026.csv")
    df_summary.to_csv(summary_path, index=False, sep=";")

    duration = (datetime.datetime.now() - t_start).total_seconds()
    print("\n" + "=" * 68)
    print("  RECONSTRUÇÃO E PRESERVAÇÃO DA BASE HISTÓRICA CONCLUÍDA COM SUCESSO!")
    print(f"  - Tempo total de processamento: {duration:.1f} segundos")
    print(f"  - Sessões WIN no histórico: {len(win_history)} ({len(win_lines)-1:,} níveis)")
    print(f"  - Sessões WDO no histórico: {len(wdo_history)} ({len(wdo_lines)-1:,} níveis)")
    print("=" * 68)


if __name__ == "__main__":
    backfill_b3_gex_history()
