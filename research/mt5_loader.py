"""
Loader alinhado 100% com o MetaTrader 5 (Strategy Tester):
- Carrega barras M5 e M1 do próprio terminal MT5 (cacheadas em `data/mt5_rates/mt5_WIN_N_M5.csv`,
  `mt5_WIN_N_M1.csv`, `mt5_WDO_N_M5.csv`, com atualização via `MetaTrader5.copy_rates_range`).
- Carrega as GEX Walls diretamente dos mesmos arquivos CSV lidos pelos EAs no Strategy Tester:
  `mt5/Files/jumba_gex_win_history.csv` e `mt5/Files/jumba_gex_wdo_history.csv`.
"""
import os
import datetime as dt
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RATES_DIR = os.path.join(ROOT_DIR, "data", "mt5_rates")
os.makedirs(RATES_DIR, exist_ok=True)

TERM_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
HIST_WIN = os.path.join(ROOT_DIR, "mt5", "Files", "jumba_gex_win_history.csv")
HIST_WDO = os.path.join(ROOT_DIR, "mt5", "Files", "jumba_gex_wdo_history.csv")


# ── Corte único de dados (paridade BT × ao vivo) ──────────────────────────────────────────────
# `_BAR_CUTOFF`: instante T (horário do servidor MT5). Só entram barras FECHADAS até T
# (abertura + duração <= T). `_LIVE_EXT`: barras recentes (ex.: pregão de hoje via MT5) anexadas ao cache.
_BAR_CUTOFF = None
_BAR_FLOOR = None   # opcional: descarta barras antes desta data (aquecimento curto)
_LIVE_EXT = {}
_TF_MIN = {"M1": 1, "M5": 5}


def set_bar_cutoff(ts):
    """Define (ou remove, com None) o instante T do corte (o cache do CSV bruto não depende dele)."""
    global _BAR_CUTOFF
    _BAR_CUTOFF = None if ts is None else pd.Timestamp(ts)


def set_bar_floor(ts):
    """Descarta barras antes de `ts` (None = sem limite). Usado para aquecimento curto no ao vivo."""
    global _BAR_FLOOR
    _BAR_FLOOR = None if ts is None else pd.Timestamp(ts)


def set_live_extension(sym: str, timeframe: str, df):
    """Anexa barras recentes (colunas t, open, high, low, close, tick_volume, real_volume)."""
    _LIVE_EXT[(sym, timeframe)] = None if df is None else df.copy()


def get_mt5_rates(sym: str, timeframe: str = "M5", since: str = "2026-04-01", until: str = "2026-11-06", refresh: bool = False) -> pd.DataFrame:
    """Retorna barras M5 ou M1 do símbolo no horário do servidor MT5, respeitando o corte de dados."""
    df = _get_mt5_rates_raw(sym, timeframe, since, until, refresh).copy()
    ext = _LIVE_EXT.get((sym, timeframe))
    if ext is not None and len(ext):
        df = pd.concat([df, ext[~ext["t"].isin(df["t"])]], ignore_index=True).sort_values("t").reset_index(drop=True)
    if _BAR_FLOOR is not None:
        df = df[df["t"] >= _BAR_FLOOR].reset_index(drop=True)
    if _BAR_CUTOFF is not None:
        df = df[df["t"] + pd.Timedelta(minutes=_TF_MIN[timeframe]) <= _BAR_CUTOFF].reset_index(drop=True)
    return df


from functools import lru_cache  # noqa: E402


@lru_cache(maxsize=16)
def _get_mt5_rates_raw(sym: str, timeframe: str, since: str, until: str, refresh: bool) -> pd.DataFrame:
    cache_path = os.path.join(RATES_DIR, f"mt5_{sym.replace('$', '_')}_{timeframe}.csv")
    if os.path.exists(cache_path) and not refresh:
        return pd.read_csv(cache_path, parse_dates=["t"])

    import MetaTrader5 as mt5
    if not mt5.initialize(TERM_PATH, timeout=15000):
        raise RuntimeError(f"Falha ao inicializar MT5: {mt5.last_error()}")
    tf_map = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5}
    raw = mt5.copy_rates_range(sym, tf_map[timeframe], dt.datetime.fromisoformat(since), dt.datetime.fromisoformat(until))
    df = pd.DataFrame(raw)
    df["t"] = pd.to_datetime(df["time"], unit="s")
    df = df[["t", "open", "high", "low", "close", "tick_volume", "real_volume"]]
    df.to_csv(cache_path, index=False)
    return df


def load_gex_csv(path: str = HIST_WIN) -> dict:
    """Lê o arquivo CSV de histórico GEX no formato exato usado pelo EA no MT5."""
    h = pd.read_csv(path, sep=";")
    out = {}
    for d, x in h.groupby("session_date"):
        w = x[x["type"] == "Wall"].sort_values("price")
        m = x[x["type"] == "MidWall"].sort_values("price")
        one = lambda t: (float(x[x["type"] == t]["price"].iloc[0]) if (x["type"] == t).any() else None)
        walls_arr = w["price"].values.astype(float)
        widths_arr = w["width"].values.astype(int) if "width" in w.columns else np.ones(len(w), dtype=int)
        mid_arr = m["price"].values.astype(float)
        levels_list = (
            [{"type": "wall", "price": float(p), "width": int(wd)} for p, wd in zip(walls_arr, widths_arr)]
            + [{"type": "mid_wall", "price": float(p), "width": 1} for p in mid_arr]
        )
        out[str(d)] = dict(
            run_name="csv",
            levels=levels_list,
            walls=walls_arr,
            wall_widths=widths_arr,
            mid_walls=mid_arr,
            gamma_flip=one("GammaFlip"),
            max_gamma=one("MaxGamma"),
            min_gamma=one("MinGamma"),
        )
    return out


def load_aligned_data():
    """Substituto direto de `discover_gex_nwe_setups.load_aligned_data()` usando dados do MT5."""
    w = get_mt5_rates("WIN$N", "M5").copy()
    w["session_date"] = w["t"].dt.strftime("%Y-%m-%d")
    w["t_min"] = w["t"].dt.hour * 60 + w["t"].dt.minute
    w = w[(w["t_min"] >= 540) & (w["t_min"] <= 1075)].copy()
    w["dt_brt"] = w["t"]
    w["hour"] = w["t_min"] // 60
    w["minute"] = w["t_min"] % 60
    w["volume"] = w["real_volume"]
    w["delta"] = 0.0
    w["timestamp_utc"] = w["t"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return w.reset_index(drop=True), load_gex_csv(HIST_WIN)


def load_win_and_wdo_aligned():
    """Substituto direto de `optimize_existing_16_setups.load_win_and_wdo_aligned()` usando dados do MT5."""
    w, gex = load_aligned_data()
    x = get_mt5_rates("WDO$N", "M5")[["t", "close"]].rename(columns={"close": "wdo_close"})
    x["wdo_ret3"] = x["wdo_close"].diff(3).fillna(0.0)
    rm = x["wdo_close"].rolling(20).mean()
    rs = x["wdo_close"].rolling(20).std().replace(0, 1.0)
    x["wdo_z"] = ((x["wdo_close"] - rm) / rs).fillna(0.0)
    w = w.merge(x[["t", "wdo_ret3", "wdo_z"]], on="t", how="left")
    w[["wdo_ret3", "wdo_z"]] = w[["wdo_ret3", "wdo_z"]].ffill().fillna(0.0)
    return w.reset_index(drop=True), gex


def load_wdo_and_win_aligned():
    """Substituto direto de `evaluate_and_optimize_wdo_16.load_wdo_and_win_aligned()` usando dados do MT5."""
    df_wdo = get_mt5_rates("WDO$N", "M5").copy()
    df_wdo["session_date"] = df_wdo["t"].dt.strftime("%Y-%m-%d")
    df_wdo["t_min"] = df_wdo["t"].dt.hour * 60 + df_wdo["t"].dt.minute
    df_wdo = df_wdo[(df_wdo["t_min"] >= 540) & (df_wdo["t_min"] <= 1075)].copy()
    df_wdo["dt_brt"] = df_wdo["t"]
    df_wdo["hour"] = df_wdo["t_min"] // 60
    df_wdo["minute"] = df_wdo["t_min"] % 60
    df_wdo["volume"] = df_wdo["real_volume"]
    df_wdo["delta"] = 0.0
    df_wdo["timestamp_utc"] = df_wdo["t"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    df_win = get_mt5_rates("WIN$N", "M5")[["t", "close"]].rename(columns={"close": "win_close"}).reset_index(drop=True)
    wc = df_win["win_close"].values
    win_ret3 = np.zeros(len(wc), dtype=float)
    win_z = np.zeros(len(wc), dtype=float)
    rets = np.zeros(len(wc), dtype=float)
    for i in range(1, len(wc)):
        if wc[i - 1] > 0:
            rets[i] = wc[i] / wc[i - 1] - 1.0
    for i in range(25, len(wc)):
        if wc[i - 3] > 0:
            win_ret3[i] = (wc[i] / wc[i - 3] - 1.0) * 10000.0
        window_r = rets[i - 19 : i + 1]
        std = np.std(window_r)
        if std > 1e-9:
            win_z[i] = (rets[i] - np.mean(window_r)) / std
    df_win["win_ret3"] = win_ret3
    df_win["win_z"] = win_z

    df_wdo = df_wdo.merge(df_win[["t", "win_ret3", "win_z"]], on="t", how="left")
    df_wdo[["win_ret3", "win_z"]] = df_wdo[["win_ret3", "win_z"]].ffill().fillna(0.0)

    df_csv = pd.read_csv(HIST_WDO, sep=";")
    gex_by_date = {}
    for s_date, grp in df_csv.groupby("session_date"):
        walls = sorted(grp[grp["type"].isin(["Wall", "wall"])]["price"].astype(float).tolist())
        mid_walls = sorted(grp[grp["type"].isin(["MidWall", "mid_wall"])]["price"].astype(float).tolist())
        gf_rows = grp[grp["type"].isin(["GammaFlip", "gamma_flip"])]["price"].astype(float).tolist()
        maxg_rows = grp[grp["type"].isin(["MaxGamma", "max_gamma"])]["price"].astype(float).tolist()
        ming_rows = grp[grp["type"].isin(["MinGamma", "min_gamma"])]["price"].astype(float).tolist()
        all_lvls = sorted(grp["price"].astype(float).tolist())
        gex_by_date[str(s_date)] = {
            "walls": np.array(walls, dtype=float),
            "mid_walls": np.array(mid_walls, dtype=float),
            "all_levels": np.array(all_lvls, dtype=float),
            "gamma_flip": gf_rows[0] if gf_rows else 0.0,
            "max_gamma": maxg_rows[0] if maxg_rows else 0.0,
            "min_gamma": ming_rows[0] if ming_rows else 0.0,
        }
    return df_wdo.reset_index(drop=True), gex_by_date


def load_m5_m1_wdo_gex():
    """Carrega M5 WIN$N, M1 WIN$N, M5 WDO$N e GEX WIN CSV para o simulador tick-a-tick SmartGrid (`sg_sim.py`)."""
    m5 = get_mt5_rates("WIN$N", "M5").reset_index(drop=True)
    m1 = get_mt5_rates("WIN$N", "M1")
    wdo = get_mt5_rates("WDO$N", "M5")[["t", "close"]]
    return m5, m1, wdo, load_gex_csv(HIST_WIN)
