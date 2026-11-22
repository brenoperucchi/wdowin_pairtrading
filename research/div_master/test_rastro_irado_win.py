# -*- coding: utf-8 -*-
"""
MOMENTO 1 — TESTE DO DIRECIONAMENTO DO RASTRO IRADO NO ÍNDICE (WIN)

Consulta em modo estritamente somente leitura (`mode=ro`) o projeto irmão
`C:\\Users\\ryzen\\Downloads\\Antigravity\\rastro_irado` (banco `data\\irai_live.db`),
computa o Rastro causal M5 para todos os 213 pregões de 2026 (`2026-01-02` a `2026-11-11`)
em 3 fontes complementares:
  1) IRAI V2 (Kalman adaptativo encadeado em memória, versão `win-nowcast-20261110T192649Z`)
  2) IRAI V1 (Pesos estáticos calibrados, `unit_fix=True`)
  3) Fair Value Walk-Forward 10 Fatores (`backend.irai.features.fair_value`, 100% OOS por sessão)

Executa 4 baterias completas no simulador tick-a-tick M1 (`bt.py`):
  - Bateria 1A: Rastro como filtro direcional nas 3 estratégias WIN da 5176 (`E22_WIN`, `C1a_BRK_WIN`, `SYM_DIV_WIN`)
  - Bateria 1B: Rastro nos motores base de WIN (Rompimento Convergente e Divergência V3.2) c/ e s/ NWE50
  - Bateria 1C: Estratégia nativa do Playbook Rastro Irado (`signalProcessor.js`: Rastro + desconto/pullback NWE/Fluxo/Wall) + Placebo sem Rastro
  - Bateria 1D: Impacto no Portfólio da carteira 5176 (E22 + C1a + V1a + SYM_PAR)

Uso: python research/div_master/test_rastro_irado_win.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
IRAI_ROOT = Path(r"C:\Users\ryzen\Downloads\Antigravity\rastro_irado")
IRAI_DB = IRAI_ROOT / "data" / "irai_live.db"

for p in (str(ROOT), str(IRAI_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Conexão estritamente somente leitura para rastro_irado
from backend.eval.data import connect_ro  # noqa: E402
from backend.timeconv import broker_wall_to_brt_wall  # noqa: E402
import backend.db as irai_db  # noqa: E402
import backend.irai.engine as irai_engine  # noqa: E402
import backend.irai.features as irai_feat  # noqa: E402


def _ro_conn(db_path=None):
    c = connect_ro(db_path or str(IRAI_DB))
    c.row_factory = sqlite3.Row
    return c


irai_db.get_connection = _ro_conn
irai_engine.get_connection = _ro_conn

_KALMAN_MEM: dict = {}


def _mem_load_kalman(conn, slug, timeframe, session_date, expected_dim=None, model_version=None, accept_untagged=False):
    st = _KALMAN_MEM.get(slug)
    if st is None or st["session_date"] >= session_date or st["model_version"] != model_version:
        return None
    if expected_dim is not None and len(st["state_mean"]) != expected_dim:
        return None
    return {
        k: st[k]
        for k in ("state_mean", "state_covariance", "johansen_p_value", "is_cointegrated", "timestamp_utc")
    }


def _mem_save_kalman(conn, slug, timeframe, session_date, state_mean, state_covariance, p_value, is_coint, ts, model_version=None):
    _KALMAN_MEM[slug] = {
        "session_date": session_date,
        "state_mean": np.array(state_mean),
        "state_covariance": np.array(state_covariance),
        "johansen_p_value": p_value,
        "is_cointegrated": bool(is_coint),
        "timestamp_utc": ts,
        "model_version": model_version,
    }


irai_engine.load_kalman_state = _mem_load_kalman
irai_engine.save_kalman_state = _mem_save_kalman

from research.discover_gex_nwe_setups import compute_nwe_series  # noqa: E402
from research.div_master.especialistas import bt, modulo as M  # noqa: E402
from research.div_master.win_especialista.audit_e22_win import (  # noqa: E402
    DS_WIN,
    XW,
    get_e22_signals,
    sim_win_exact,
)
from research.div_master.wdo_especialista.robustez_final import make_P as make_P_wdo  # noqa: E402
from research.div_master.wdo_especialista.robustez_v32_100 import (  # noqa: E402
    OPT_OPEN,
    eval_v32 as eval_wdo,
    run_v32 as run_v32_wdo,
)
from research.div_master.flow_breakout.busca_convergencia_v32 import collect_asset_conv  # noqa: E402
from research.div_master.flow_breakout.audit_convergencia_v32 import sim_win_df  # noqa: E402
from research.div_master.test_sym_top1 import collect_sym_top1, sim_asset  # noqa: E402
from research.div_master.wdo_especialista.robustez_final import DS as DS_WDO  # noqa: E402

MODEL_VER = "win-nowcast-20261110T192649Z"
REPORT_PATH = ROOT / "research" / "div_master" / "RESULTADOS_RASTRO_IRADO_WIN.md"


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONSTRUÇÃO DO PAINEL CAUSAL DO RASTRO IRADO (V1 + V2 + FAIR VALUE 10F)
# ─────────────────────────────────────────────────────────────────────────────

def build_rastro_lookup(dates: List[str]) -> Tuple[Dict[Tuple[str, int], dict], dict]:
    """
    Computa Rastro causal barra a barra em horário BRT para todas as datas em `dates`.
    Indexado por `(date, bar_open_tm_brt)` onde `bar_open_tm_brt` é o minuto de abertura
    da barra M5 que fecha exatamente quando a barra seguinte abre.
    Portanto, para uma entrada em `tm_in`, a leitura causal é `lookup.get((date, tm_in - 5))`.
    """
    t0 = time.time()
    _KALMAN_MEM.clear()
    eng = irai_engine.IRAIEngine(str(IRAI_DB))
    w_stat, sig_stat, a_stat, ic_stat, cfg = eng._get_model_config("WIN$N", version_id=MODEL_VER)
    opts = cfg["options"]
    scale = float(opts.get("score_scale", 1.0) or 1.0)

    # Fair value 10 fatores (100% walk-forward 60 sessões anteriores)
    conn = _ro_conn()
    panel = irai_feat.build_panel(conn, "WIN$N", irai_feat.BASKETS["WIN$N"], "2025-09-01", max(dates))
    fv_df = irai_feat.fair_value(panel, irai_feat.FairValueConfig(window_sessions=60, step_bars=6))

    # Montar lookup do Fair Value por (sess, tm_brt)
    pdf = panel.df
    st_cols = [c for c in pdf.columns if c.startswith("stale_")]
    stale_any = (pdf[st_cols].sum(axis=1) > 0).to_numpy() if st_cols else np.zeros(len(pdf), dtype=bool)
    fv_vals = fv_df["fv"].to_numpy(float)
    z_vals = fv_df["z"].to_numpy(float)
    tm_vals = (pdf["ts_brt"].dt.hour * 60 + pdf["ts_brt"].dt.minute).to_numpy(int)
    sess_vals = pdf["sess"].to_numpy()

    fv_by_key: Dict[Tuple[str, int], dict] = {}
    last_sess = None
    hist_fv: List[float] = []
    for i in range(len(pdf)):
        s = sess_vals[i]
        if s != last_sess:
            last_sess = s
            hist_fv = []
        fv_i = float(fv_vals[i]) if np.isfinite(fv_vals[i]) else np.nan
        hist_fv.append(fv_i)
        fv12 = hist_fv[-13] if len(hist_fv) >= 13 else 0.0
        dfv60 = (fv_i - fv12) if (np.isfinite(fv_i) and np.isfinite(fv12)) else np.nan
        fv_by_key[(s, int(tm_vals[i]))] = {
            "fv": fv_i,
            "dfv60": dfv60,
            "fv_gap_z": float(z_vals[i]) if np.isfinite(z_vals[i]) else np.nan,
            "fv_stale": bool(stale_any[i]),
        }

    # Live snapshots gravados no banco (para referência / auditoria de integridade no OOS)
    live_rows = conn.execute(
        "SELECT session_date, timestamp_utc, p_up, score, price_diverge_z FROM irai_live_snapshots "
        "WHERE target='WIN$N' AND timeframe='M5' AND is_ghost=0"
    ).fetchall()
    conn.close()
    live_count = len(live_rows)

    lookup: Dict[Tuple[str, int], dict] = {}
    days_with_v2 = 0
    for d in dates:
        snaps = eng.compute_from_db(
            d, target="WIN$N", version="v2", timeframe="M5", persist_state=True, model_version_id=MODEL_VER
        )
        had_real = False
        for sn in snaps:
            if sn.is_ghost or sn.is_pre_market:
                continue
            had_real = True
            dt_brt = broker_wall_to_brt_wall(datetime.fromisoformat(sn.timestamp))
            d_brt = dt_brt.strftime("%Y-%m-%d")
            tm_brt = dt_brt.hour * 60 + dt_brt.minute
            v1_sc = sum(
                w_stat[f"w_{lbl}"] * sig_stat[lbl] * sn.factors[lbl]["z_score"] / scale
                for lbl in sn.factors
                if f"w_{lbl}" in w_stat and lbl in sig_stat
            )
            v1_p = float(irai_engine.sigmoid(a_stat * v1_sc + ic_stat) * 100.0)
            fv_info = fv_by_key.get((d_brt, tm_brt), {})
            lookup[(d_brt, tm_brt)] = {
                "p_up_v2": float(sn.p_up),
                "score_v2": float(sn.score),
                "p_up_v1": v1_p,
                "score_v1": float(v1_sc),
                "div_z_v2": float(sn.price_diverge_z) if sn.price_diverge_z is not None else np.nan,
                "flow_confirms": sn.flow_confirms,
                "win_return": float(sn.win_return),
                "fv": fv_info.get("fv", np.nan),
                "dfv60": fv_info.get("dfv60", np.nan),
                "fv_gap_z": fv_info.get("fv_gap_z", np.nan),
                "fv_stale": fv_info.get("fv_stale", True),
            }
        if had_real:
            days_with_v2 += 1

    meta = {
        "elapsed_s": round(time.time() - t0, 1),
        "days_total": len(dates),
        "days_with_v2": days_with_v2,
        "bars_indexed": len(lookup),
        "live_snapshots_db": live_count,
    }
    return lookup, meta


def enrich_df_with_rastro(df: pd.DataFrame, lookup: Dict[Tuple[str, int], dict]) -> pd.DataFrame:
    """Adiciona ao DataFrame as colunas causais do Rastro no fechamento de `tm - 5` (barra anterior à entrada `tm`)."""
    df = df.copy()
    keys = list(zip(df["date"], df["tm"] - 5))
    cols = ["p_up_v2", "score_v2", "p_up_v1", "score_v1", "div_z_v2", "fv", "dfv60", "fv_gap_z"]
    data = {c: [] for c in cols}
    has_rastro = []
    for k in keys:
        rec = lookup.get(k)
        if rec is None:
            has_rastro.append(False)
            for c in cols:
                data[c].append(np.nan)
        else:
            has_rastro.append(True)
            for c in cols:
                data[c].append(rec.get(c, np.nan))
    df["has_rastro"] = has_rastro
    for c in cols:
        df[c] = data[c]
    return df


# ─────────────────────────────────────────────────────────────────────────────
# 2. REGRAS DE ORIENTAÇÃO DO RASTRO
# ─────────────────────────────────────────────────────────────────────────────

def rastro_rules() -> List[Tuple[str, str, Callable[[pd.DataFrame], pd.Series]]]:
    """Lista de regras `(id, descrição, fn(df) -> mask booleano)`."""
    return [
        ("BASE_SEM_RASTRO", "Sem filtro Rastro (baseline)", lambda d: pd.Series(True, index=d.index)),
        ("V2_SCORE_0",      "IRAI V2 Direção Pura (C: score>0 | V: score<0)",
         lambda d: ((d["dir"] == 1) & (d["score_v2"] > 0.0)) | ((d["dir"] == -1) & (d["score_v2"] < 0.0))),
        ("V2_P50",          "IRAI V2 P(↑) > 50 / < 50",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] > 50.0)) | ((d["dir"] == -1) & (d["p_up_v2"] < 50.0))),
        ("V2_P55_45",       "IRAI V2 Veredito Comprador/Vendedor (C>=55 | V<=45)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] >= 55.0)) | ((d["dir"] == -1) & (d["p_up_v2"] <= 45.0))),
        ("V2_P60_40",       "IRAI V2 Rastro Forte SignalGauge (C>=60 | V<=40)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] >= 60.0)) | ((d["dir"] == -1) & (d["p_up_v2"] <= 40.0))),
        ("V2_P65_35",       "IRAI V2 RISK-ON / RISK-OFF (C>=65 | V<=35)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] >= 65.0)) | ((d["dir"] == -1) & (d["p_up_v2"] <= 35.0))),
        ("V2_VETO_45_55",   "IRAI V2 Veto Leve (C>=45 | V<=55 — não operar contra)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] >= 45.0)) | ((d["dir"] == -1) & (d["p_up_v2"] <= 55.0))),
        ("V2_VETO_40_60",   "IRAI V2 Veto Forte (C>40 | V<60 — evita extremo oposto)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] > 40.0)) | ((d["dir"] == -1) & (d["p_up_v2"] < 60.0))),
        ("V2_VETO_35_65",   "IRAI V2 Veto RISK-ON/OFF (C>35 | V<65)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] > 35.0)) | ((d["dir"] == -1) & (d["p_up_v2"] < 65.0))),
        ("V1_SCORE_0",      "IRAI V1 Estático (C: score>0 | V: score<0)",
         lambda d: ((d["dir"] == 1) & (d["score_v1"] > 0.0)) | ((d["dir"] == -1) & (d["score_v1"] < 0.0))),
        ("V1_P55_45",       "IRAI V1 Estático (C>=55 | V<=45)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v1"] >= 55.0)) | ((d["dir"] == -1) & (d["p_up_v1"] <= 45.0))),
        ("V1_VETO_45_55",   "IRAI V1 Estático Veto (C>=45 | V<=55)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v1"] >= 45.0)) | ((d["dir"] == -1) & (d["p_up_v1"] <= 55.0))),
        ("FV_DIA_0",        "Fair Value 10F Walk-Forward Dia (C: fv>0 | V: fv<0)",
         lambda d: ((d["dir"] == 1) & (d["fv"] > 0.0)) | ((d["dir"] == -1) & (d["fv"] < 0.0))),
        ("FV_SLOPE_60M",    "Fair Value 10F Walk-Forward Slope 60m (C: dfv>0 | V: dfv<0)",
         lambda d: ((d["dir"] == 1) & (d["dfv60"] > 0.0)) | ((d["dir"] == -1) & (d["dfv60"] < 0.0))),
        ("FV_GAP_FAV",      "Fair Value 10F Gap Favorável (C: gap_z<=0 | V: gap_z>=0)",
         lambda d: ((d["dir"] == 1) & (d["fv_gap_z"] <= 0.0)) | ((d["dir"] == -1) & (d["fv_gap_z"] >= 0.0))),
        ("PLACEBO_OPOSTO",  "Placebo Oposto ao Rastro V2 (C<=45 | V>=55)",
         lambda d: ((d["dir"] == 1) & (d["p_up_v2"] <= 45.0)) | ((d["dir"] == -1) & (d["p_up_v2"] >= 55.0))),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 3. SIMULADORES BASE PARA WIN (SEM PERDER SINAIS POR MGMT ANTES DO FILTRO!)
# ─────────────────────────────────────────────────────────────────────────────

def simulate_raw_win(df: pd.DataFrame, sl: float, tp: float, be_trig: float, be_lock: float, tmax: int) -> pd.DataFrame:
    """Simula todos os sinais candidatos de WIN em M1 tick-a-tick BEFORE `bt.mgmt(..., 'UM')`."""
    df = df.sort_values(["date", "tm"]).reset_index(drop=True)
    pnls, xts = [], []
    for r in df.itertuples():
        p, xt = sim_win_exact(
            DS_WIN[r.date], int(r.e), float(r.ep), int(r.dir),
            sl, tp, be_trig, be_lock, int(tmax),
            XW["tick"], 10.0, 5.0, 0.0, adv_m1=False,
        )
        pnls.append(p)
        xts.append(xt)
    df["pnl"] = pnls
    df["xt"] = xts
    return df


def eval_filtered(df_raw: pd.DataFrame, mask: pd.Series, mult: float = 1.0, mgmt: str = "UM") -> Tuple[dict, pd.DataFrame]:
    sub = df_raw[mask].copy()
    if len(sub) == 0:
        return dict(ops=0, wr=0.0, pf=0.0, net=0, dd=0, rdd=0.0, meses="0/0", h1=0, h2=0, is_=0, oos=0, worst_day=0), sub
    if mult != 1.0:
        sub["pnl"] = sub["pnl"] * mult
    tf = bt.mgmt(sub, "pnl", "xt", mgmt) if mgmt == "UM" else sub
    st = bt.stats(tf, "pnl", "xt")
    d_sum = tf.groupby("date")["pnl"].sum()
    st["worst_day"] = round(float(d_sum.min())) if len(d_sum) else 0
    return st, tf


def build_base_candidates(lookup: Dict[Tuple[str, int], dict]):
    # 1. E22_WIN (produção e sem NWE50)
    r_e22 = get_e22_signals("all", M.V32_PROD, use_filters=True)
    df_e22 = simulate_raw_win(enrich_df_with_rastro(pd.DataFrame(r_e22), lookup), 200.0, 0.0, 180.0, 20.0, 12)

    # E22 sem filtro NWE50 (apenas !super, seq<=1, 10h-16h)
    from research.div_master.win_especialista.audit_e22_win import win_cache, PW
    rows_e22_no50 = []
    for d in sorted(win_cache):
        fb, w_all, w_wall, D = win_cache[d]
        atr = M.atr_series(fb, PW["tick"])
        cands = M.engine_v32(fb, w_all, PW, "common", atr=atr, opt=M.V32_PROD)
        trig, _ = M.triggers(fb, cands, PW)
        seq = {1: 0, -1: 0}
        for x in trig:
            if x.get("dup"):
                continue
            s = seq[x["dir"]]
            seq[x["dir"]] += 1
            t = x["idx"]
            if t + 1 >= len(fb):
                continue
            tm = bt.hm(fb[t + 1]["time"])
            if tm not in D["pos"] or x.get("super") or s > 1 or not (600 <= tm < 960):
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            rows_e22_no50.append(dict(date=d, e=e, ep=float(D["o5"][e]), dir=int(x["dir"]), tm=tm))
    df_e22_no50 = simulate_raw_win(enrich_df_with_rastro(pd.DataFrame(rows_e22_no50), lookup), 200.0, 0.0, 180.0, 20.0, 12)

    # 2. C1a_BRK_WIN (com ext50_trend < 0.5 e sem ext50_trend)
    df_conv = collect_asset_conv("WIN", "wall", True)
    m_c1_no50 = (
        (df_conv["family"] == "BRK_F1F2")
        & df_conv["conv_k1_ok"]
        & df_conv["w2_fav"]
        & df_conv["near_wall"]
        & df_conv["crossed_wall"]
        & (df_conv["hh"] != 11)
    )
    df_c1_no50 = enrich_df_with_rastro(df_conv[m_c1_no50].copy(), lookup)
    df_c1_no50 = simulate_raw_win(df_c1_no50, 280.0, 280.0, 0.0, 0.0, 24)
    df_c1a = df_c1_no50[df_c1_no50["ext50_trend"] < 0.5].copy().reset_index(drop=True)

    # Sem near_wall / crossed_wall (motor base BRK_F1F2 mais amplo c/ conv_k1_ok & w2_fav & hh!=11)
    m_brk_raw = (df_conv["family"] == "BRK_F1F2") & df_conv["conv_k1_ok"] & df_conv["w2_fav"] & (df_conv["hh"] != 11)
    df_brk_raw = simulate_raw_win(enrich_df_with_rastro(df_conv[m_brk_raw].copy(), lookup), 280.0, 280.0, 0.0, 0.0, 24)

    # 3. SYM_DIV_WIN (com NWE50 e sem NWE50)
    df_sym_w = enrich_df_with_rastro(collect_sym_top1("WIN", nodiv=False, strict_no_super=False), lookup)
    df_sym_w = simulate_raw_win(df_sym_w, 280.0, 240.0, 0.0, 0.0, 24)

    # SYM_WIN sem NWE50 (V32_OPEN wall CONF seq<=1 hh!=11)
    rows_sym_no50 = []
    for d in sorted(win_cache):
        fb, w_all, w_wall, D = win_cache[d]
        atr = M.atr_series(fb, PW["tick"])
        cands = M.engine_v32(fb, w_wall, PW, "common", atr=atr, opt=OPT_OPEN)
        seq = {1: 0, -1: 0}
        for c in cands:
            conf = int(c["conf"])
            dr = int(c["dir"])
            if conf + 1 >= len(fb):
                continue
            s = seq[dr]
            seq[dr] += 1
            if s > 1:
                continue
            tm = bt.hm(fb[conf + 1]["time"])
            lo_w, hi_w = bt.WINDOW["WIN"]
            if not (lo_w <= tm <= hi_w) or tm not in D["pos"] or (tm // 60) == 11:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            half50 = max(float(D["u50"][e] - D["c50"][e]), XW["tick"])
            ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half50
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
            rows_sym_no50.append(dict(
                date=d, e=e, ep=float(D["o5"][e]), dir=dr, tm=tm, ext50=ext50, slope50=slope50
            ))
    df_sym_no50 = simulate_raw_win(enrich_df_with_rastro(pd.DataFrame(rows_sym_no50), lookup), 280.0, 240.0, 0.0, 0.0, 24)

    return {
        "E22_WIN": df_e22,
        "E22_NO_NWE50": df_e22_no50,
        "C1a_WIN": df_c1a,
        "C1_NO_NWE50": df_c1_no50,
        "BRK_F1F2_RAW": df_brk_raw,
        "SYM_WIN": df_sym_w,
        "SYM_NO_NWE50": df_sym_no50,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. BATERIA 1C — ESTRATÉGIA NATIVA DO PLAYBOOK RASTRO IRADO NO WIN
#    (Rastro Macro + Canal/Banda NWE + Confirmação Candle/Flip/Fluxo/Wall)
# ─────────────────────────────────────────────────────────────────────────────

def build_native_rastro_win(lookup: Dict[Tuple[str, int], dict]) -> pd.DataFrame:
    """
    Constrói candidatos barra a barra no WIN seguindo o Playbook IRAI (`signalProcessor.js` + `manual-operacao-irai.html`):
      - Rastro V2 (`p_up_v2`, `score_v2`), V1 (`p_up_v1`), Fair Value (`fv`, `dfv60`)
      - Posição relativa no envelope NWE causal do `rastro_irado` (LB=95, BW=8, MULT=3.0) E do `bt` (NWE30 / NWE50)
      - Confirmação na barra de sinal (`e-1`): candle a favor (`flip`), rejeição/martelo (`pavio >= 1.5x corpo`),
        fluxo Smart Money (`wave > 0` na compra / `< 0` na venda), e proximidade de Wall (`dist_wall <= 150`).
    """
    from research.div_master.win_especialista.audit_e22_win import win_cache

    # Série contínua NWE 95/8/3 (estilo rastro_irado/backend/irai/nwe.py com gap-stitching diário)
    # e NWE 30 / 50 de DS_WIN já disponível
    dates = sorted(win_cache)
    lo_w, hi_w = bt.WINDOW["WIN"]
    recs = []

    for d in dates:
        fb, w_all, w_wall, D = win_cache[d]
        pos_fb = {bt.hm(b["time"]): i for i, b in enumerate(fb)}
        n5 = len(D["o5"])
        o5, h5, l5, c5, tm5 = D["o5"], D["h5"], D["l5"], D["close"] if "close" in D else D["c5"], D["tm5"]

        for e in range(2, n5):
            tm = int(tm5[e])
            if not (lo_w <= tm <= hi_w):
                continue
            tm_sig = tm - 5
            r = lookup.get((d, tm_sig))
            if r is None:
                continue

            # Preço fechado em t = e - 1
            o_t, h_t, l_t, c_t = float(o5[e - 1]), float(h5[e - 1]), float(l5[e - 1]), float(c5[e - 1])
            c_prev = float(c5[e - 2])
            rng = max(h_t - l_t, 5.0)
            body = abs(c_t - o_t)
            upper_wick = h_t - max(o_t, c_t)
            lower_wick = min(o_t, c_t) - l_t

            # NWE30 causal (de DS_WIN, já deslocado para e)
            u30, l30 = float(D["u30"][e]), float(D["l30"][e])
            c30 = 0.5 * (u30 + l30)
            nwe30_pos = (c_t - l30) / max(u30 - l30, 5.0) * 100.0  # 0 = lower, 50 = center, 100 = upper

            # NWE50 causal
            u50, l50, c50 = float(D["u50"][e]), float(D["l50"][e]), float(D["c50"][e])
            half50 = max(u50 - c50, 5.0)
            nwe50_slope = float(c50 - D["c50"][max(0, e - 6)]) / half50

            # Fluxo Profit na barra de sinal
            idx_fb = pos_fb.get(tm_sig)
            wave_sig = float(fb[idx_fb].get("wave", 0.0)) if idx_fb is not None else 0.0

            # Proximidade de Wall no fechamento ou extremo da barra sinal
            d_wall_low = min((abs(l_t - w) for w in w_all), default=99999.0)
            d_wall_high = min((abs(h_t - w) for w in w_all), default=99999.0)
            d_wall_c = min((abs(c_t - w) for w in w_all), default=99999.0)

            for dr in (1, -1):
                # Condições de timing NWE (estilo signalProcessor.js)
                is_disc_30 = (nwe30_pos <= 35.0) if dr == 1 else (nwe30_pos >= 65.0)
                is_mid_30 = (c_t <= c30) if dr == 1 else (c_t >= c30)
                is_ext_30 = (l_t <= l30 or c_t <= l30) if dr == 1 else (h_t >= u30 or c_t >= u30)
                is_disc_50 = (c_t <= c50) if dr == 1 else (c_t >= c50)
                # Rompimento/Retomada de NWE central ou pullback com flip de candle a favor
                flip_candle = (dr * (c_t - o_t) > 0)
                # Martelo/Estrela Cadente ou barra com pavio de defesa >= 1.2x corpo
                rej_wick = (lower_wick >= max(body, 20.0) * 1.2 and dr * (c_t - o_t) >= 0) if dr == 1 else (
                    upper_wick >= max(body, 20.0) * 1.2 and dr * (c_t - o_t) >= 0
                )
                # Pullback simples na banda NWE: barra prévia ou atual tocou/abaixo da central + fechou a favor
                pb_nwe30 = (is_mid_30 and flip_candle)
                pb_nwe50 = (is_disc_50 and flip_candle)
                strong_nwe30 = (is_disc_30 and flip_candle)
                near_wall = (min(d_wall_c, d_wall_low if dr == 1 else d_wall_high) <= 150.0)
                flow_fav = (dr * wave_sig > 0.0)
                slope50_fav = (dr * nwe50_slope > 0.0)

                recs.append(dict(
                    date=d, e=e, ep=float(o5[e]), dir=dr, tm=tm, hh=tm // 60,
                    p_up_v2=r["p_up_v2"], score_v2=r["score_v2"],
                    p_up_v1=r["p_up_v1"], score_v1=r["score_v1"],
                    div_z_v2=r["div_z_v2"],
                    fv=r["fv"], dfv60=r["dfv60"], fv_gap_z=r["fv_gap_z"],
                    nwe30_pos=nwe30_pos,
                    is_disc_30=is_disc_30, is_mid_30=is_mid_30, is_ext_30=is_ext_30,
                    is_disc_50=is_disc_50,
                    flip_candle=flip_candle, rej_wick=rej_wick,
                    pb_nwe30=pb_nwe30, pb_nwe50=pb_nwe50, strong_nwe30=strong_nwe30,
                    near_wall=near_wall, flow_fav=flow_fav, slope50_fav=slope50_fav,
                ))

    return pd.DataFrame(recs)


# ─────────────────────────────────────────────────────────────────────────────
# 5. FORMATAÇÃO DO RELATÓRIO
# ─────────────────────────────────────────────────────────────────────────────

def fmt_row(lbl: str, st: dict) -> str:
    sub = f"{st['h1']:+5d}/{st['h2']:+5d}/{st['oos']:+5d}"
    return (
        f"| {lbl:<42} | {st['ops']:4d} | {st['wr']:4.1f}% | {st['pf']:4.2f} | "
        f"{st['net']:+7d} | {st['dd']:5d} | {st['rdd']:5.2f} | {st['meses']:>5} | "
        f"{sub:<19} | {st.get('worst_day', 0):+6d} |"
    )


HDR = (
    "| Estratégia / Filtro                        |  Ops |    WR |   PF |  Net R$ |    DD |  R/DD | Meses | H1 / H2 / OOS       | PiorDia |\n"
    "|--------------------------------------------|------|-------|------|---------|-------|-------|-------|---------------------|---------|"
)


def main():
    t_all = time.time()
    dates = sorted(DS_WIN.keys())
    print(f"[Momento 1] Calculando Rastro Irado (V1 + V2 + Fair Value 10F) para {len(dates)} pregões WIN...")
    lookup, meta = build_rastro_lookup(dates)
    print(f"  -> Rastro lookup pronto em {meta['elapsed_s']}s | dias={meta['days_with_v2']}/{meta['days_total']} | barras={meta['bars_indexed']}")

    lines: List[str] = [
        "# Momento 1 — Direcionamento do Rastro Irado no Índice (WIN)",
        "",
        f"**Banco consultado (somente leitura):** `C:\\Users\\ryzen\\Downloads\\Antigravity\\rastro_irado\\data\\irai_live.db`  ",
        f"**Pregões avaliados:** {len(dates)} (`{dates[0]}` a `{dates[-1]}` | H1 `<= {bt.H1_END}` · H2 `<= {bt.IS_END}` · OOS `> {bt.IS_END}`)  ",
        f"**Cobertura Rastro M5 causal (`tm_in - 5`):** {meta['days_with_v2']}/{meta['days_total']} sessões, {meta['bars_indexed']:,} barras M5 (modelo V1/V2 `{MODEL_VER}`, calibrado 2025-10-16..2026-10-28; mais Fair Value 10 Fatores **100% walk-forward** 60 sessões).  ",
        "**Custo / slippage WIN:** R$ 2,00/op (10 pts) + slippage de 1 tick (5 pts) no stop, execução M1 tick-a-tick (`bt.sim`), 1 contrato por estratégia (exceto seção de portfólio com E22=2ct).",
        "",
        "> **Nota sobre calibração:** O modelo V1/V2 (`win-nowcast-20261110T192649Z`) possui pesos estáticos ajustados até `2026-10-28` (Kalman V2 encadeado barra a barra). Já o **Fair Value 10 Fatores (`FV_DIA_0` / `FV_SLOPE_60M`)** é reestimado por OLS a cada pregão usando *apenas* os 60 pregões anteriores (100% fora da amostra em todo o ano de 2026).",
        "",
    ]

    bases = build_base_candidates(lookup)
    rules = rastro_rules()

    # ── BATERIA 1A ──
    print("[Bateria 1A] Testando filtro Rastro nas 3 estratégias WIN da carteira 5176...")
    lines.append("## 1A. Rastro Irado aplicado às 3 Estratégias WIN da Carteira 5176 (1 ct)")
    lines.append("")
    best_by_strat: Dict[str, Tuple[str, dict, pd.DataFrame]] = {}
    for sname in ("E22_WIN", "C1a_WIN", "SYM_WIN"):
        df_raw = bases[sname]
        lines.append(f"### {sname}")
        lines.append("")
        lines.append(HDR)
        best_rdd = -1.0
        for rid, rdesc, rfn in rules:
            st, tf = eval_filtered(df_raw, rfn(df_raw))
            lines.append(fmt_row(f"{rid} ({rdesc[:22]})", st))
            if rid != "BASE_SEM_RASTRO" and st["ops"] >= 40 and st["rdd"] > best_rdd:
                best_rdd = st["rdd"]
                best_by_strat[sname] = (rid, st, tf)
        lines.append("")

    # Soma combinada das 3 estratégias WIN com as principais regras de Rastro
    lines.append("### Carteira WIN Combinada (`E22 1ct + C1a 1ct + SYM_WIN 1ct`) sob o mesmo filtro Rastro")
    lines.append("")
    lines.append(HDR)
    for rid, rdesc, rfn in rules:
        parts = []
        for sname in ("E22_WIN", "C1a_WIN", "SYM_WIN"):
            _, tf = eval_filtered(bases[sname], rfn(bases[sname]))
            if len(tf):
                parts.append(tf[["date", "tm", "xt", "pnl"]])
        comb = pd.concat(parts, ignore_index=True).sort_values(["date", "xt", "tm"]) if parts else pd.DataFrame(columns=["date", "tm", "xt", "pnl"])
        st = bt.stats(comb, "pnl", "xt") if len(comb) else dict(ops=0, wr=0, pf=0, net=0, dd=0, rdd=0, meses="0/0", h1=0, h2=0, oos=0)
        d_sum = comb.groupby("date")["pnl"].sum() if len(comb) else pd.Series(dtype=float)
        st["worst_day"] = round(float(d_sum.min())) if len(d_sum) else 0
        lines.append(fmt_row(f"{rid}", st))
    lines.append("")

    # ── BATERIA 1B ──
    print("[Bateria 1B] Testando Rastro vs NWE50 nos motores base (sem filtro NWE50)...")
    lines.append("## 1B. Rastro Irado substituindo ou somando ao NWE50 nos motores base WIN")
    lines.append("")
    selected_rules_1b = [
        "BASE_SEM_RASTRO", "V2_SCORE_0", "V2_P50", "V2_P55_45", "V2_P60_40",
        "V2_VETO_45_55", "V2_VETO_40_60", "V1_SCORE_0", "FV_DIA_0", "FV_SLOPE_60M", "PLACEBO_OPOSTO"
    ]
    rmap = {r[0]: r[2] for r in rules}
    for bname, label in [
        ("C1_NO_NWE50", "BRK_F1F2 Rompimento Convergente (conv_k1w2 + near&crs + hh!=11, SEM NWE50)"),
        ("BRK_F1F2_RAW", "BRK_F1F2 Amplo (conv_k1w2 + hh!=11, SEM wall e SEM NWE50)"),
        ("SYM_NO_NWE50", "SYM_TOP1 Divergência V3.2 (wall + CONF + seq<=1 + hh!=11, SEM NWE50)"),
        ("E22_NO_NWE50", "E22 Divergência V3.2 Produção (all + OPC + !super + seq<=1 + 10-16h, SEM NWE50)"),
    ]:
        lines.append(f"### {label}")
        lines.append("")
        lines.append(HDR)
        df_raw = bases[bname]
        for rid in selected_rules_1b:
            st, _ = eval_filtered(df_raw, rmap[rid](df_raw))
            lines.append(fmt_row(rid, st))
        lines.append("")

    # ── BATERIA 1C ──
    print("[Bateria 1C] Testando estratégia nativa do Rastro Irado no WIN (Rastro + Pullback NWE / Flip / Wall)...")
    df_nat = build_native_rastro_win(lookup)
    # Pré-simular 4 perfis de saída em uma única passada sobre as barras únicas (date, e, dir)
    exit_profiles = [
        ("SL200_BE180_t12", 200.0, 0.0, 180.0, 20.0, 12),
        ("SL240_TP240_t24", 240.0, 240.0, 0.0, 0.0, 24),
        ("SL280_TP280_t24", 280.0, 280.0, 0.0, 0.0, 24),
        ("SL240_TP360_t24", 240.0, 360.0, 0.0, 0.0, 24),
    ]
    for prof, sl, tp, bt_tr, bt_lk, tmax in exit_profiles:
        pnls, xts = [], []
        for r in df_nat.itertuples():
            p, xt = sim_win_exact(DS_WIN[r.date], int(r.e), float(r.ep), int(r.dir), sl, tp, bt_tr, bt_lk, tmax, 5.0, 10.0, 5.0, 0.0)
            pnls.append(p)
            xts.append(xt)
        df_nat[f"p_{prof}"] = pnls
        df_nat[f"x_{prof}"] = xts

    rastro_dirs = [
        ("V2_P60_40",    lambda d: ((d["dir"] == 1) & (d["p_up_v2"] >= 60.0)) | ((d["dir"] == -1) & (d["p_up_v2"] <= 40.0))),
        ("V2_P55_45",    lambda d: ((d["dir"] == 1) & (d["p_up_v2"] >= 55.0)) | ((d["dir"] == -1) & (d["p_up_v2"] <= 45.0))),
        ("V2_SCORE_0",   lambda d: ((d["dir"] == 1) & (d["score_v2"] > 0.0)) | ((d["dir"] == -1) & (d["score_v2"] < 0.0))),
        ("V1_P60_40",    lambda d: ((d["dir"] == 1) & (d["p_up_v1"] >= 60.0)) | ((d["dir"] == -1) & (d["p_up_v1"] <= 40.0))),
        ("FV_DIA_0",     lambda d: ((d["dir"] == 1) & (d["fv"] > 0.0)) | ((d["dir"] == -1) & (d["fv"] < 0.0))),
        ("FV_SLOPE_60M", lambda d: ((d["dir"] == 1) & (d["dfv60"] > 0.0)) | ((d["dir"] == -1) & (d["dfv60"] < 0.0))),
        ("SEM_RASTRO",   lambda d: pd.Series(True, index=d.index)),
    ]
    timing_modes = [
        ("NWE30_MID_FLIP",  lambda d: d["pb_nwe30"] & (d["hh"] != 11)),
        ("NWE30_DISC_FLIP", lambda d: d["strong_nwe30"] & (d["hh"] != 11)),
        ("NWE50_MID_FLIP",  lambda d: d["pb_nwe50"] & (d["hh"] != 11)),
        ("PB30_FLOW_WALL",  lambda d: d["pb_nwe30"] & d["flow_fav"] & d["near_wall"] & (d["hh"] != 11)),
        ("PB50_FLOW_WALL",  lambda d: d["pb_nwe50"] & d["flow_fav"] & d["near_wall"] & (d["hh"] != 11)),
        ("FLIP_WALL_FLOW",  lambda d: d["flip_candle"] & d["flow_fav"] & d["near_wall"] & (d["hh"] != 11)),
        ("EXT30_REJ",       lambda d: d["is_ext_30"] & d["rej_wick"] & (d["hh"] != 11)),
    ]

    nat_rows = []
    for rname, rfn in rastro_dirs:
        rm = rfn(df_nat)
        for tname, tfn in timing_modes:
            m = rm & tfn(df_nat)
            sub_base = df_nat[m]
            if len(sub_base) < 20:
                continue
            for prof, _, _, _, _, _ in exit_profiles:
                sub = sub_base[["date", "tm", "dir", f"p_{prof}", f"x_{prof}"]].rename(
                    columns={f"p_{prof}": "pnl", f"x_{prof}": "xt"}
                )
                tf = bt.mgmt(sub.sort_values(["date", "tm"]), "pnl", "xt", "UM")
                if len(tf) < 40:
                    continue
                st = bt.stats(tf, "pnl", "xt")
                d_sum = tf.groupby("date")["pnl"].sum()
                st["worst_day"] = round(float(d_sum.min())) if len(d_sum) else 0
                nat_rows.append((st["rdd"], rname, tname, prof, st, tf))

    nat_rows.sort(key=lambda x: x[0], reverse=True)
    lines.append("## 1C. Estratégia Nativa do Rastro Irado no WIN (Playbook: Rastro + Pullback NWE / Fluxo / Wall)")
    lines.append("")
    lines.append("### Top 20 combinações ordenadas por Ret/DD (com >= 40 ops, UM_POR_VEZ)")
    lines.append("")
    lines.append(HDR)
    shown_nat = 0
    for rdd, rname, tname, prof, st, _ in nat_rows:
        if rname == "SEM_RASTRO":
            continue
        lines.append(fmt_row(f"{rname} | {tname} | {prof[:9]}", st))
        shown_nat += 1
        if shown_nat >= 20:
            break
    lines.append("")

    # Comparação explícita com Placebos (MESMO timing + exit COM Rastro vs SEM Rastro)
    lines.append("### Teste Placebo Nativo (Mesmo gatilho NWE/Fluxo COM Rastro vs SEM Rastro)")
    lines.append("")
    lines.append(HDR)
    nat_lookup = {(r, t, p): (st, tf) for _, r, t, p, st, tf in nat_rows}
    seen_tp = set()
    for _, rname, tname, prof, st, _ in nat_rows:
        if rname == "SEM_RASTRO" or (tname, prof) in seen_tp:
            continue
        seen_tp.add((tname, prof))
        lines.append(fmt_row(f"COM {rname}: {tname} ({prof[:9]})", st))
        pl = nat_lookup.get(("SEM_RASTRO", tname, prof))
        if pl:
            lines.append(fmt_row(f"SEM Rastro (Placebo): {tname}", pl[0]))
        if len(seen_tp) >= 6:
            break
    lines.append("")

    # ── BATERIA 1D: PORTFÓLIO ──
    print("[Bateria 1D] Simulando impacto no portfólio completo (E22 2ct + C1a + V1a + SYM_PAR)...")
    P_wdo = make_P_wdo(zone=3.5, pierce_max=6.0)
    r_v1a = run_v32_wdo(
        P_wdo, "wall", "common", OPT_OPEN, "CONF",
        lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0,
    )
    _, tf_v1a = eval_wdo(r_v1a, 14.0, "nw", 0.0, 24, "UM")
    df_sd = collect_sym_top1("WDO", nodiv=False, strict_no_super=False)
    _, tf_sym_d = sim_asset(df_sd, "WDO", 14.0, "nw_all", 0.0, 0.0, 0.0, 18)

    _, tf_e22_base = eval_filtered(bases["E22_WIN"], pd.Series(True, index=bases["E22_WIN"].index), mult=2.0)
    _, tf_c1a_base = eval_filtered(bases["C1a_WIN"], pd.Series(True, index=bases["C1a_WIN"].index), mult=1.0)
    _, tf_sym_base = eval_filtered(bases["SYM_WIN"], pd.Series(True, index=bases["SYM_WIN"].index), mult=1.0)

    def comb_stats(dfs: List[pd.DataFrame]) -> dict:
        c = pd.concat([d[["date", "tm", "xt", "pnl"]] for d in dfs if len(d)], ignore_index=True)
        c = c.sort_values(["date", "xt", "tm"])
        st = bt.stats(c, "pnl", "xt")
        d_sum = c.groupby("date")["pnl"].sum()
        st["worst_day"] = round(float(d_sum.min())) if len(d_sum) else 0
        return st

    lines.append("## 1D. Impacto no Portfólio Completo (Carteira 5176 com E22=2ct)")
    lines.append("")
    lines.append(HDR)
    lines.append(fmt_row("BASE 5176 (E22 2c+C1a+SYM_W + V1a+SYM_D)", comb_stats([tf_e22_base, tf_c1a_base, tf_sym_base, tf_v1a, tf_sym_d])))

    for rid in ("V2_VETO_45_55", "V2_VETO_40_60", "V2_P55_45", "V2_SCORE_0", "FV_DIA_0", "FV_SLOPE_60M"):
        _, te = eval_filtered(bases["E22_WIN"], rmap[rid](bases["E22_WIN"]), mult=2.0)
        _, tc = eval_filtered(bases["C1a_WIN"], rmap[rid](bases["C1a_WIN"]), mult=1.0)
        _, ts = eval_filtered(bases["SYM_WIN"], rmap[rid](bases["SYM_WIN"]), mult=1.0)
        lines.append(fmt_row(f"WIN c/ {rid} + WDO base", comb_stats([te, tc, ts, tf_v1a, tf_sym_d])))

    # Adicionar melhor nativa (com H1/H2/OOS > 0 e Rastro ativo) ao portfólio base
    nat_valid = [x for x in nat_rows if x[1] != "SEM_RASTRO" and x[4]["h1"] > 0 and x[4]["h2"] > 0 and x[4]["oos"] > 0]
    if nat_valid:
        _, rn, tn, pr, st_nat, tf_nat = nat_valid[0]
        lines.append(fmt_row(f"BASE 5176 + Nativa ({rn}|{tn[:10]})", comb_stats([tf_e22_base, tf_c1a_base, tf_sym_base, tf_v1a, tf_sym_d, tf_nat])))

    lines.append("")
    lines.append(f"*Gerado em {time.time() - t_all:.1f}s em modo somente leitura.*")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[Momento 1 CONCLUÍDO em {time.time() - t_all:.1f}s] Relatório salvo em: {REPORT_PATH}")
    print("\n".join(lines[lines.index("## 1A. Rastro Irado aplicado às 3 Estratégias WIN da Carteira 5176 (1 ct)"):]))


if __name__ == "__main__":
    main()
