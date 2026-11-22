"""Carregamento de trades dos relatórios HTML do MT5 Strategy Tester e barras M1."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_HTM_DIR = ROOT_DIR / "data" / "reports" / "mt5_tester_ohlc_2026"
WIN_M1_CSV = ROOT_DIR / "data" / "mt5_rates" / "mt5_WIN_N_M1.csv"
WDO_MT5_M1_CSV = ROOT_DIR / "data" / "mt5_rates" / "mt5_WDO_N_M1.csv"
WDO_HIST_M1_CSV = ROOT_DIR / "data" / "historical" / "WDO$N_M1_202103100900_202603261829.csv"

DATE_START_2026 = "2026-01-02"
DATE_END_2026 = "2026-11-06"


@dataclass(frozen=True)
class RobotSpec:
    """Metadados operacionais de cada estratégia do portfólio."""

    code: str
    htm_code: str
    asset: str
    tf: str
    magic: int
    desc: str
    pt_val: float
    mt5_native_spread_brl: float
    full_b3_cost_brl: float


ROBOT_METADATA: dict[str, RobotSpec] = {
    "EST-01": RobotSpec("EST-01", "EST01", "WIN", "M5", 88001, "WIN_PA_PINBAR_WALL", 0.20, 1.0, 2.0),
    "EST-03": RobotSpec("EST-03", "EST03", "WIN", "M15", 88003, "WIN_M15_FAKEOUT_TRAP", 0.20, 1.0, 2.0),
    "EST-04": RobotSpec("EST-04", "EST04", "WIN", "M5", 88004, "WIN_PB_WDO_ALIGNED", 0.20, 1.0, 2.0),
    "EST-05": RobotSpec("EST-05", "EST05", "WIN", "M15", 88005, "WIN_M15_MIDWALL_PULLBACK", 0.20, 1.0, 2.0),
    "EST-07": RobotSpec("EST-07", "EST07", "WIN", "M5", 88007, "WIN_OF_CLIMAX_WALL", 0.20, 1.0, 2.0),
    "EST-09": RobotSpec("EST-09", "EST09", "WIN", "M5", 88009, "WIN_BO_STOP_LIM_NY_2D", 0.20, 1.0, 2.0),
    "EST-10": RobotSpec("EST-10", "EST10", "WIN", "M5", 88010, "WIN_MAINWALL_STOP_LIM_1D", 0.20, 1.0, 2.0),
    "EST-13": RobotSpec("EST-13", "EST13", "WIN", "M5", 88013, "WIN_SG_SCALPER_3C", 0.20, 1.0, 2.0),
    "EST-14": RobotSpec("EST-14", "EST14", "WIN", "M5", 88014, "WIN_SG_MOMENTUM_3C", 0.20, 1.0, 2.0),
    "EST-15": RobotSpec("EST-15", "EST15", "WIN", "M5", 88015, "WIN_SG_Z30_REV_WALL", 0.20, 1.0, 2.0),
    "EST-16": RobotSpec("EST-16", "EST16", "WIN", "M5", 88016, "WIN_SG_SPRING_Z30_WALL", 0.20, 1.0, 2.0),
    "WDO-01": RobotSpec("WDO-01", "WDO01", "WDO", "M5", 89001, "WDO_PA_WALL_SCALPER_NY", 10.0, 5.0, 5.0),
    "WDO-05": RobotSpec("WDO-05", "WDO05", "WDO", "M5", 89005, "WDO_PA_CLUSTER_NWE", 10.0, 5.0, 5.0),
    "WDO-07": RobotSpec("WDO-07", "WDO07", "WDO", "M5", 89007, "WDO_OF_CLIMAX_WALL", 10.0, 5.0, 5.0),
    "WDO-09": RobotSpec("WDO-09", "WDO09", "WDO", "M5", 89009, "WDO_PB_WALL_PULLBACK", 10.0, 5.0, 5.0),
}

PORTFOLIO_PRESETS: dict[str, dict] = {
    "proposta_b_11": {
        "id": "proposta_b_11",
        "label": "Proposta B · 11 Robôs (Oficial)",
        "subtitle": "8 WIN (EST-01, 03, 04, 05, 07, 13, 14, 15) + 3 WDO (WDO-01, 05, 07)",
        "robots": [
            "EST-01", "EST-03", "EST-04", "EST-05", "EST-07", "EST-13", "EST-14", "EST-15",
            "WDO-01", "WDO-05", "WDO-07",
        ],
    },
    "m5_11": {
        "id": "m5_11",
        "label": "XP M5 · 11 Robôs",
        "subtitle": "7 WIN M5 (EST-01, 04, 07, 13, 14, 15, 16) + 4 WDO M5 (WDO-01, 05, 07, 09)",
        "robots": [
            "EST-01", "EST-04", "EST-07", "EST-13", "EST-14", "EST-15", "EST-16",
            "WDO-01", "WDO-05", "WDO-07", "WDO-09",
        ],
    },
    "top_8": {
        "id": "top_8",
        "label": "Campeões · 8 Robôs",
        "subtitle": "5 WIN (EST-04, 07, 13, 14, 15) + 3 WDO (WDO-01, 05, 07)",
        "robots": [
            "EST-04", "EST-07", "EST-13", "EST-14", "EST-15",
            "WDO-01", "WDO-05", "WDO-07",
        ],
    },
    "top_10": {
        "id": "top_10",
        "label": "Campeões + EST-09/10 · 10 Robôs",
        "subtitle": "7 WIN (EST-04, 07, 09, 10, 13, 14, 15) + 3 WDO (WDO-01, 05, 07)",
        "robots": [
            "EST-04", "EST-07", "EST-09", "EST-10", "EST-13", "EST-14", "EST-15",
            "WDO-01", "WDO-05", "WDO-07",
        ],
    },
}

_DEAL_ROW_PAT = re.compile(
    r"<tr[^>]*>\s*"
    r"<td[^>]*>(\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}:\d{2})</td>\s*"
    r"<td[^>]*>(\d+)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>\s*"
    r"<td[^>]*>([^<]*)</td>",
    flags=re.IGNORECASE,
)


def _clean_num(raw: str) -> float:
    cleaned = raw.strip().replace(" ", "").replace("\xa0", "").split("/")[0].replace(",", ".")
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _time_to_min(dt_str: str) -> int:
    # Format: "YYYY.MM.DD HH:MM:SS" or "YYYY-MM-DD HH:MM:SS"
    hh = int(dt_str[11:13])
    mm = int(dt_str[14:16])
    return hh * 60 + mm


def _time_to_sec(dt_str: str) -> int:
    hh = int(dt_str[11:13])
    mm = int(dt_str[14:16])
    ss = int(dt_str[17:19])
    return hh * 3600 + mm * 60 + ss


def parse_mt5_htm_trades(
    htm_path: str | Path,
    strat_code: str,
    cost_mode: str = "net",
    lot_mult: float = 1.0,
) -> list[dict]:
    """Lê um relatório UTF-16 `.htm` do MT5 Strategy Tester e pareia deals `in` -> `out`.

    Em estratégias SmartGrid (EST-13..EST-16), o MT5 pode fechar pernas em ordem
    diferente do FIFO; portanto o pareamento busca primeiro perna aberta com volume
    exato e menor erro absoluto contra `(px_out - px_in) * side * pt_val * vol`.
    """
    spec = ROBOT_METADATA[strat_code]
    htm_path = Path(htm_path)
    if not htm_path.exists():
        raise FileNotFoundError(f"Relatório MT5 não encontrado: {htm_path}")

    text = htm_path.read_bytes().decode("utf-16", errors="ignore")

    raw_deals: list[dict] = []
    for m in _DEAL_ROW_PAT.finditer(text):
        dt_str, deal_id, _sym, dtype, direction, vol_s, price_s, _ord, _comm, _swap, profit_s, _bal, comment = m.groups()
        dtype_l = dtype.strip().lower()
        if dtype_l not in ("buy", "sell", "compra", "venda"):
            continue
        dir_l = direction.strip().lower()
        if dir_l not in ("in", "out", "in/out", "entrada", "saída", "entrada/saída"):
            continue
        raw_deals.append({
            "datetime": dt_str.strip(),
            "date": dt_str.strip()[:10].replace(".", "-"),
            "deal_id": int(deal_id),
            "side": 1 if dtype_l in ("buy", "compra") else -1,
            "dir": dir_l,
            "vol": _clean_num(vol_s),
            "price": _clean_num(price_s),
            "profit": _clean_num(profit_s),
            "comment": comment.strip(),
        })

    open_legs: list[dict] = []
    trades: list[dict] = []

    def _emit_trade(leg: dict, out_deal: dict, vol: float, raw_profit: float) -> None:
        scaled_vol = vol * lot_mult
        raw_brl = raw_profit * lot_mult
        gross_brl = raw_brl + spec.mt5_native_spread_brl * scaled_vol
        extra_cost = max(0.0, spec.full_b3_cost_brl - spec.mt5_native_spread_brl) * scaled_vol
        if cost_mode == "net":
            pnl = raw_brl - extra_cost
            applied_extra = extra_cost
        elif cost_mode == "mt5_raw":
            pnl = raw_brl
            applied_extra = 0.0
        elif cost_mode == "gross":
            pnl = gross_brl
            applied_extra = 0.0
        else:
            raise ValueError(f"cost_mode inválido: {cost_mode}")

        t_in = leg["t_in"].replace(".", "-")
        t_out = out_deal["datetime"].replace(".", "-")
        trades.append({
            "strat": strat_code,
            "asset": spec.asset,
            "tf": spec.tf,
            "magic": spec.magic,
            "side": leg["side"],
            "lots": scaled_vol,
            "t_in": t_in,
            "t_out": t_out,
            "date": out_deal["date"],
            "date_in": leg["date_in"],
            "min_in": _time_to_min(t_in),
            "min_out": _time_to_min(t_out),
            "sec_in": _time_to_sec(t_in),
            "sec_out": _time_to_sec(t_out),
            "px_in": leg["px_in"],
            "px_out": out_deal["price"],
            "pnl": round(pnl, 2),
            "pnl_mt5_raw": round(raw_brl, 2),
            "pnl_gross": round(gross_brl, 2),
            "cost_extra": round(applied_extra, 2),
            "cost_total": round((spec.full_b3_cost_brl if cost_mode == "net" else (spec.mt5_native_spread_brl if cost_mode == "mt5_raw" else 0.0)) * scaled_vol, 2),
            "comment": out_deal["comment"] or leg["comment"],
        })

    for d in raw_deals:
        if d["dir"] in ("in", "entrada"):
            open_legs.append({
                "t_in": d["datetime"],
                "date_in": d["date"],
                "px_in": d["price"],
                "vol": d["vol"],
                "side": d["side"],
                "comment": d["comment"],
            })
        elif d["dir"] in ("out", "saída", "in/out", "entrada/saída"):
            vol_out = d["vol"]
            best_idx = None
            best_err = 1e18
            for idx, leg in enumerate(open_legs):
                if abs(leg["vol"] - vol_out) < 1e-6:
                    exp_prof = leg["side"] * (d["price"] - leg["px_in"]) * spec.pt_val * vol_out
                    err = abs(exp_prof - d["profit"])
                    if err < best_err:
                        best_err = err
                        best_idx = idx
            if best_idx is not None:
                leg = open_legs.pop(best_idx)
                _emit_trade(leg, d, vol_out, d["profit"])
            else:
                # Fallback FIFO proporcional caso um deal out feche frações
                rem = vol_out
                while rem > 1e-9 and open_legs:
                    leg = open_legs[0]
                    take = min(rem, leg["vol"])
                    frac_prof = d["profit"] * (take / vol_out) if vol_out > 0 else 0.0
                    _emit_trade(leg, d, take, frac_prof)
                    leg["vol"] -= take
                    rem -= take
                    if leg["vol"] <= 1e-9:
                        open_legs.pop(0)

    if open_legs:
        raise ValueError(f"{strat_code} ({htm_path.name}) terminou com {len(open_legs)} perna(s) em aberto")

    return trades


def load_portfolio_trades(
    robot_codes: Iterable[str],
    htm_dir: str | Path = DEFAULT_HTM_DIR,
    cost_mode: str = "net",
    win_mult: float = 1.0,
    wdo_mult: float = 1.0,
) -> list[dict]:
    """Carrega todos os trades dos robôs selecionados, ordenados por entrada."""
    htm_dir = Path(htm_dir)
    all_trades: list[dict] = []
    for code in robot_codes:
        spec = ROBOT_METADATA[code]
        mult = win_mult if spec.asset == "WIN" else wdo_mult
        fp = htm_dir / f"{spec.htm_code}_P1.htm"
        all_trades.extend(parse_mt5_htm_trades(fp, code, cost_mode=cost_mode, lot_mult=mult))
    all_trades.sort(key=lambda t: (t["date"], t["sec_in"], t["sec_out"], t["strat"]))
    return all_trades


def _df_to_daily_m1_dict(df: pd.DataFrame) -> dict[str, dict]:
    df = df.sort_values("t").drop_duplicates(subset=["t"], keep="last").reset_index(drop=True)
    df["date"] = df["t"].str.slice(0, 10)
    df = df[(df["date"] >= DATE_START_2026) & (df["date"] <= DATE_END_2026)].copy()
    df["min"] = df["t"].str.slice(11, 13).astype(int) * 60 + df["t"].str.slice(14, 16).astype(int)

    out: dict[str, dict] = {}
    for date, grp in df.groupby("date", sort=True):
        mins = grp["min"].to_numpy(dtype=np.int32)
        out[str(date)] = {
            "mins": mins,
            "open": grp["open"].to_numpy(dtype=np.float64),
            "high": grp["high"].to_numpy(dtype=np.float64),
            "low": grp["low"].to_numpy(dtype=np.float64),
            "close": grp["close"].to_numpy(dtype=np.float64),
            "min_to_idx": {int(m): idx for idx, m in enumerate(mins)},
        }
    return out


def load_m1_bars(
    win_csv: str | Path = WIN_M1_CSV,
    wdo_mt5_csv: str | Path = WDO_MT5_M1_CSV,
    wdo_hist_csv: str | Path = WDO_HIST_M1_CSV,
) -> tuple[dict[str, dict], dict[str, dict]]:
    """Carrega barras M1 reais de WIN e WDO para o período 2026-01-02..2026-11-06."""
    win_df = pd.read_csv(win_csv, usecols=["t", "open", "high", "low", "close"])
    win_days = _df_to_daily_m1_dict(win_df)

    wdo_parts = []
    if Path(wdo_hist_csv).exists():
        wh = pd.read_csv(wdo_hist_csv, sep="\t", usecols=["<DATE>", "<TIME>", "<OPEN>", "<HIGH>", "<LOW>", "<CLOSE>"])
        wh["t"] = wh["<DATE>"].str.replace(".", "-", regex=False) + " " + wh["<TIME>"]
        wh = wh[wh["t"] >= "2026-01-01"].rename(
            columns={"<OPEN>": "open", "<HIGH>": "high", "<LOW>": "low", "<CLOSE>": "close"}
        )[["t", "open", "high", "low", "close"]]
        wdo_parts.append(wh)
    if Path(wdo_mt5_csv).exists():
        wm = pd.read_csv(wdo_mt5_csv, usecols=["t", "open", "high", "low", "close"])
        wdo_parts.append(wm)

    if not wdo_parts:
        raise FileNotFoundError("Nenhuma base M1 do WDO encontrada.")

    wdo_df = pd.concat(wdo_parts, ignore_index=True)
    wdo_days = _df_to_daily_m1_dict(wdo_df)
    return win_days, wdo_days


def enrich_trades_with_m1_mae_mfe(
    trades: list[dict],
    win_m1: dict[str, dict],
    wdo_m1: dict[str, dict],
) -> list[dict]:
    """Calcula MAE e MFE reais por trade usando barras M1 entre `[min_in, min_out]`."""
    for tr in trades:
        spec = ROBOT_METADATA[tr["strat"]]
        day_bars = (win_m1 if tr["asset"] == "WIN" else wdo_m1).get(tr["date"])
        side = tr["side"]
        px_in = tr["px_in"]
        lots = tr["lots"]
        cost = tr["cost_extra"]
        pnl = tr["pnl"]

        # Pior/melhor excursão garantidamente cobrem entrada e saída reais do trade
        worst_raw = min(0.0, pnl)
        best_raw = max(0.0, pnl)

        if day_bars is not None:
            mins = day_bars["mins"]
            i0 = int(np.searchsorted(mins, tr["min_in"], side="left"))
            i1 = int(np.searchsorted(mins, tr["min_out"], side="right"))
            # Para barras estritamente entre entrada e saída (ou barra de entrada se diferente da saída),
            # usa high/low da barra M1; na barra de saída evita ultrapassar o próprio SL/saída.
            if i1 > i0:
                hi_slice = day_bars["high"][i0:i1]
                lo_slice = day_bars["low"][i0:i1]
                m_slice = mins[i0:i1]
                for idx_local, m_val in enumerate(m_slice):
                    lo_px = lo_slice[idx_local]
                    hi_px = hi_slice[idx_local]
                    if side == 1:
                        adv_brl = (lo_px - px_in) * spec.pt_val * lots - cost
                        fav_brl = (hi_px - px_in) * spec.pt_val * lots - cost
                    else:
                        adv_brl = (px_in - hi_px) * spec.pt_val * lots - cost
                        fav_brl = (px_in - lo_px) * spec.pt_val * lots - cost

                    if m_val == tr["min_out"]:
                        # Na barra exata da saída, a execução já ocorreu no máx/min até px_out:
                        # se fechou com loss, não extrapolar pior que o loss realizado se foi SL.
                        if pnl < 0:
                            adv_brl = max(adv_brl, pnl)
                        if pnl > 0:
                            fav_brl = min(fav_brl, pnl)
                    worst_raw = min(worst_raw, adv_brl)
                    best_raw = max(best_raw, fav_brl)

        tr["mae_brl"] = round(abs(min(0.0, worst_raw)), 2)
        tr["mfe_brl"] = round(max(0.0, best_raw), 2)
    return trades
