"""
Estudo Quantitativo IS / OOS — Relevancia GEX & Regime Gamma (Tests 1, 2 e 3)
Totalmente isolado em research/gex_audit_bt/ (ZERO alteracoes em producao).

Uso: python -m research.gex_audit_bt.run_gex_relevance_study
"""
from __future__ import annotations

import os
import sys
import time
from bisect import bisect_right

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import setups_runner  # noqa: E402
from research.flow_window_asg import generate_portfolio_6_json as gp  # noqa: E402
from research.flow_window_asg.flow_filters import load_flow_tables, make_sig_filter  # noqa: E402
from research.gex_audit_bt.run_bt_compare import set_gex_paths, verify_gex_loaded  # noqa: E402
from research.optimizers import sg_sim  # noqa: E402
from research.setup_parity.bt_32_slots import END, SPLIT, START, stats  # noqa: E402

CSV_DIR = os.path.join(ROOT, "research", "gex_audit_bt", "gex_csvs")
RES_DIR = os.path.join(ROOT, "research", "gex_audit_bt", "results")

WIN_PLAIN = os.path.join(CSV_DIR, "win_prod_plain.csv")
WDO_PLAIN = os.path.join(CSV_DIR, "wdo_prod_plain.csv")
WIN_SIGNED = os.path.join(CSV_DIR, "win_prod_signed.csv")
WDO_SIGNED = os.path.join(CSV_DIR, "wdo_prod_signed.csv")

WIN_LIVE_7 = [4, 7, 9, 10, 13, 14, 15]
WDO_LIVE_3 = [1, 5, 7]

WDO_NATIVE_FLIP_RULE = {
    1: "PULLBACK_ONLY",
    2: "DIRECTIONAL",
    3: "DIRECTIONAL_8P",
    4: "DIRECTIONAL_4P",
    5: "PULLBACK_ONLY",
    6: "NONE",
    7: "NONE",
    8: "DIRECTIONAL",
    9: "DIRECTIONAL_5P",
    10: "NONE",
    11: "DIRECTIONAL_3P",
    12: "DIRECTIONAL_4P",
    13: "DIRECTIONAL_5P",
    14: "DIRECTIONAL_5P",
    15: "DIRECTIONAL_6P",
    16: "DIRECTIONAL",
}


def load_signed_gex_map(path: str) -> dict[str, dict]:
    df = pd.read_csv(path, sep=";")
    out = {}
    for d, x in df.groupby("session_date"):
        gf = float(x.loc[x["type"] == "GammaFlip", "price"].iloc[0])
        mxg = float(x.loc[x["type"] == "MaxGamma", "price"].iloc[0])
        mng = float(x.loc[x["type"] == "MinGamma", "price"].iloc[0])
        wm = x[x["type"].isin(["Wall", "MidWall"])].sort_values("price")
        levels = [
            (
                float(r["price"]),
                str(r["type"]),
                int(r["width"]),
                float(r["gex"]),
                float(r["gex_share"]),
                int(r["rank_abs_gex"]),
            )
            for _, r in wm.iterrows()
        ]
        out[str(d)] = {
            "gamma_flip": gf,
            "max_gamma": mxg,
            "min_gamma": mng,
            "levels": levels,
        }
    return out


def build_bar_lookup(df: pd.DataFrame):
    bar_map = {}
    day_tmins = {}
    dates = df["session_date"].astype(str).values
    tmins = df["t_min"].astype(int).values
    opens = df["open"].astype(float).values
    highs = df["high"].astype(float).values
    lows = df["low"].astype(float).values
    closes = df["close"].astype(float).values
    for i in range(len(df)):
        d = dates[i]
        tm = int(tmins[i])
        bar_map[(d, tm)] = (float(opens[i]), float(highs[i]), float(lows[i]), float(closes[i]))
        day_tmins.setdefault(d, []).append(tm)
    for d in day_tmins:
        day_tmins[d].sort()
    return bar_map, day_tmins


class ContextProvider:
    def __init__(self, signed_gex: dict, bar_maps: dict, day_tmins: dict):
        self.signed_gex = signed_gex
        self.bar_maps = bar_maps
        self.day_tmins = day_tmins
        self.misses = 0
        self._ctx_cache = {}

    def get_ctx(self, asset: str, date_str: str, b1_tmin: int) -> dict | None:
        key = (asset, date_str, int(b1_tmin))
        if key in self._ctx_cache:
            return self._ctx_cache[key]

        g = self.signed_gex[asset].get(date_str)
        bar = self.bar_maps[asset].get((date_str, int(b1_tmin)))
        if g is None or bar is None:
            self.misses += 1
            self._ctx_cache[key] = None
            return None

        o1, h1, l1, c1 = bar
        gf = g["gamma_flip"]
        is_pos_gamma = c1 >= gf
        dist_flip = c1 - gf

        best_lvl = None
        best_score = (float("inf"), float("inf"))
        for lvl in g["levels"]:
            p = lvl[0]
            if l1 <= p <= h1:
                d_bar = 0.0
            else:
                d_bar = min(abs(l1 - p), abs(h1 - p))
            score = (d_bar, abs(c1 - p))
            if score < best_score:
                best_score = score
                best_lvl = lvl

        p, typ, wd, gex_val, gex_sh, rank = best_lvl
        if typ == "MidWall":
            polarity = "MIDWALL"
        elif gex_val > 0:
            polarity = "CALL_WALL"
        else:
            polarity = "PUT_WALL"

        ctx = {
            "o1": o1,
            "h1": h1,
            "l1": l1,
            "c1": c1,
            "gamma_flip": gf,
            "is_pos_gamma": is_pos_gamma,
            "dist_flip": dist_flip,
            "lvl_price": p,
            "lvl_type": typ,
            "lvl_width": wd,
            "lvl_gex": gex_val,
            "lvl_share": gex_sh,
            "lvl_rank": rank,
            "polarity": polarity,
        }
        self._ctx_cache[key] = ctx
        return ctx

    def prev_bar_tmin(self, asset: str, date_str: str, entry_hhmm: str) -> int | None:
        hh, mm = map(int, entry_hhmm.split(":"))
        e_tmin = hh * 60 + mm
        tms = self.day_tmins[asset].get(date_str)
        if not tms:
            return None
        pos = bisect_right(tms, e_tmin - 1) - 1
        if pos >= 0:
            return tms[pos]
        return tms[0]


def make_gate_filter(ctx_prov: ContextProvider, asset: str, gate_name: str):
    if gate_name == "ALL":
        return None

    def _gf(date_str: str, b1_tmin: int, sig_dir: int) -> bool:
        ctx = ctx_prov.get_ctx(asset, str(date_str), int(b1_tmin))
        if ctx is None:
            return False
        df = ctx["dist_flip"]
        pol = ctx["polarity"]
        typ = ctx["lvl_type"]
        sh = ctx["lvl_share"]
        rk = ctx["lvl_rank"]
        wd = ctx["lvl_width"]
        tm = int(b1_tmin)

        if gate_name == "ONLY_POS_GAMMA":
            return df >= 0.0
        if gate_name == "ONLY_NEG_GAMMA":
            return df < 0.0
        if gate_name == "POS_OR_NEAR_5":
            return df >= -5.0
        if gate_name == "POS_OR_NEAR_10":
            return df >= -10.0
        if gate_name == "POS_STRICT_5":
            return df >= 5.0
        if gate_name == "NO_FLIP_ZONE_10":
            return abs(df) >= 10.0
        if gate_name == "DIR_POS_SELL_NEG_BUY":
            return (df >= 0.0 and sig_dir == -1) or (df < 0.0 and sig_dir == 1)
        if gate_name == "DIR_POS_BUY_NEG_SELL":
            return (df >= 0.0 and sig_dir == 1) or (df < 0.0 and sig_dir == -1)
        if gate_name == "ALL_WITH_15H_CAP":
            return tm <= 895
        if gate_name == "ONLY_POS_WITH_15H_CAP":
            return tm <= 895 and df >= 0.0
        if gate_name == "ONLY_NEG_WITH_15H_CAP":
            return tm <= 895 and df < 0.0

        # Test 2: Polarity
        if gate_name == "ONLY_CALL_WALL":
            return pol == "CALL_WALL"
        if gate_name == "ONLY_PUT_WALL":
            return pol == "PUT_WALL"
        if gate_name == "ONLY_WALL_ANY":
            return typ == "Wall"
        if gate_name == "CALL_OR_MID":
            return pol in ("CALL_WALL", "MIDWALL")
        if gate_name == "NO_PUT_WALL":
            return pol != "PUT_WALL"
        if gate_name == "NO_MIDWALL":
            return typ != "MidWall"

        # Test 3: Concentration & combined
        if gate_name == "SHARE_GE_03":
            return typ == "Wall" and sh >= 0.03
        if gate_name == "SHARE_GE_05":
            return typ == "Wall" and sh >= 0.05
        if gate_name == "SHARE_GE_08":
            return typ == "Wall" and sh >= 0.08
        if gate_name == "RANK_TOP5":
            return typ == "Wall" and 1 <= rk <= 5
        if gate_name == "RANK_TOP8":
            return typ == "Wall" and 1 <= rk <= 8
        if gate_name == "WIDTH_GE_2":
            return typ == "Wall" and wd >= 2
        if gate_name == "POS_GAMMA_ONLY_WALL":
            return df >= 0.0 and typ == "Wall"
        if gate_name == "POS_GAMMA_CALL_WALL":
            return df >= 0.0 and pol == "CALL_WALL"
        if gate_name == "POS_GAMMA_NO_PUT_WALL":
            return df >= 0.0 and pol != "PUT_WALL"
        if gate_name == "POS_GAMMA_SHARE_GE_04":
            return df >= 0.0 and typ == "Wall" and sh >= 0.04
        if gate_name == "POS_GAMMA_SHARE_GE_06":
            return df >= 0.0 and typ == "Wall" and sh >= 0.06
        if gate_name == "POS_GAMMA_CALL_OR_MID":
            return df >= 0.0 and pol in ("CALL_WALL", "MIDWALL")

        raise ValueError(f"Gate desconhecido: {gate_name}")

    return _gf


def compose_filters(*filters):
    active = [f for f in filters if f is not None]
    if not active:
        return None
    if len(active) == 1:
        return active[0]

    def _combined(date_str: str, b1_tmin: int, sig_dir: int) -> bool:
        return all(f(date_str, b1_tmin, sig_dir) for f in active)

    return _combined


class SimRunner:
    def __init__(self, mk, ft, ctx_prov: ContextProvider):
        self.mk = mk
        self.ft = ft
        self.ctx_prov = ctx_prov
        self.cache = {}

    def run(self, asset: str, k: int, flow_name: str = "0_BASE_MT5", gate_name: str = "ALL", max_entry_tmin: int | None = None) -> list[dict]:
        ckey = (asset, int(k), flow_name, gate_name, max_entry_tmin)
        if ckey in self.cache:
            return self.cache[ckey]

        df_win, gex_win, n50w, n30w, rsi7w, df_wdo, gex_wdo, n50d, n30d, rsi7d = self.mk
        sf_flow = make_sig_filter(self.ft, asset, flow_name)
        sf_gate = make_gate_filter(self.ctx_prov, asset, gate_name)
        sf_cap = (lambda _d, tmin, _s: int(tmin) <= max_entry_tmin) if max_entry_tmin is not None else None
        sf = compose_filters(sf_flow, sf_gate, sf_cap)

        sid = f"{asset}_{k:02d}" if asset == "WDO" else f"EST_{k:02d}"
        if asset == "WDO":
            raw = gp.wsim.simulate_wdo_core_slot(
                k, df_wdo, gex_wdo,
                n50d[0], n50d[1], n50d[2], n50d[4],
                n30d[0], n30d[1], n30d[2], n30d[4],
                rsi7d, start_date=START, end_date=END, cost_pts=gp.COST_WDO_PTS, sig_filter=sf,
            )
            out = gp.format_wdo_trades(raw, sid)
        else:
            A = (df_win, gex_win, n50w[0], n50w[1], n50w[2], n50w[4], n30w[0], n30w[1], n30w[2], n30w[4], rsi7w)
            if k == 4:
                tr, _ = gp.simulate_aligned_win_wdo_slot(
                    4, *A, be_mode="BE_WALL_2STAGE_177K", wall_shield_buf=15.0,
                    tp_mode="TP_MIDWALL", entry_override="ALIGNED",
                    cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START,
                )
                out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)
            elif k == 7:
                tr, _ = gp.o16.simulate_single_est_slot(
                    7, *A, entry_override="CURRENT", be_mode="BE_WALL_SHIELD",
                    wall_shield_buf=15.0, tp_mode="TP_CURRENT",
                    cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START,
                )
                out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)
            elif k == 9:
                tr, _ = gp.o16.simulate_single_est_slot(
                    9, *A, max_trades_day=2, cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START,
                )
                out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)
            elif k == 10:
                tr, _ = gp.o16.simulate_single_est_slot(
                    10, *A, max_trades_day=1, cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START,
                )
                out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)
            elif k in (13, 14, 15, 16):
                out = gp.format_sg_trades(sg_sim.run(slots=(k,), start=START, cost_pts=gp.COST_WIN_PTS, sig_filter=sf))
            else:
                tr, _ = gp.o16.simulate_single_est_slot(
                    k, *A, cost_pts=gp.COST_WIN_PTS, sig_filter=sf, start_date=START,
                )
                out = gp.format_win_o16_trades([t for t in tr if START <= str(t["date"]) <= END], df_win, sid)

        out = [t for t in out if START <= t["date"] <= END]
        self.cache[ckey] = out
        return out


def eval_metrics(trades: list[dict]) -> dict:
    s_all = stats(trades)
    s_is = stats(trades, hi=SPLIT)
    s_oos = stats(trades, lo=SPLIT)
    ev_all = round(s_all["net"] / s_all["ops"], 2) if s_all["ops"] > 0 else 0.0
    ev_is = round(s_is["net"] / s_is["ops"], 2) if s_is["ops"] > 0 else 0.0
    ev_oos = round(s_oos["net"] / s_oos["ops"], 2) if s_oos["ops"] > 0 else 0.0
    return {
        "ops": s_all["ops"], "wr": s_all["wr"], "pf": s_all["pf"], "ev": ev_all,
        "net": s_all["net"], "mdd": s_all["mdd"], "ret_dd": s_all["ret_dd"], "pos_m": s_all["pos_m"],
        "is_ops": s_is["ops"], "is_wr": s_is["wr"], "is_pf": s_is["pf"], "is_ev": ev_is,
        "is_net": s_is["net"], "is_mdd": s_is["mdd"], "is_ret_dd": s_is["ret_dd"], "is_pos_m": s_is["pos_m"],
        "oos_ops": s_oos["ops"], "oos_wr": s_oos["wr"], "oos_pf": s_oos["pf"], "oos_ev": ev_oos,
        "oos_net": s_oos["net"], "oos_mdd": s_oos["mdd"], "oos_ret_dd": s_oos["ret_dd"], "oos_pos_m": s_oos["pos_m"],
    }


def enrich_trades(trades: list[dict], asset: str, ctx_prov: ContextProvider) -> list[dict]:
    enriched = []
    for t in trades:
        d = str(t["date"])
        b1_tm = ctx_prov.prev_bar_tmin(asset, d, str(t["time"]))
        ctx = ctx_prov.get_ctx(asset, d, b1_tm) if b1_tm is not None else None
        if ctx is None:
            ctx_prov.misses += 1
            continue
        ep = float(t["entry_price"])
        gf = ctx["gamma_flip"]
        entry_regime = "POS_GAMMA" if ep >= gf else "NEG_GAMMA"
        b1_regime = "POS_GAMMA" if ctx["is_pos_gamma"] else "NEG_GAMMA"
        abs_dist_flip = abs(ep - gf)
        if abs_dist_flip < 15.0:
            dist_bkt = "NEAR_<15"
        elif abs_dist_flip < 40.0:
            dist_bkt = "MID_15_40"
        else:
            dist_bkt = "FAR_>=40"
        sh = ctx["lvl_share"]
        if ctx["lvl_type"] == "MidWall":
            sh_bkt = "0_MIDWALL"
            wd_lbl = "MidWall"
        else:
            wd_lbl = f"Wall_W{ctx['lvl_width']}"
            if sh < 0.04:
                sh_bkt = "1_LOW_<4%"
            elif sh < 0.12:
                sh_bkt = "2_MED_4_12%"
            else:
                sh_bkt = "3_HIGH_>=12%"
        nt = dict(t)
        nt.update({
            "b1_regime": b1_regime,
            "entry_regime": entry_regime,
            "reg_dir": f"{b1_regime}_{t['direction']}",
            "dist_bkt": dist_bkt,
            "polarity": ctx["polarity"],
            "lvl_type": ctx["lvl_type"],
            "lvl_width": ctx["lvl_width"],
            "wd_lbl": wd_lbl,
            "lvl_share": sh,
            "sh_bkt": sh_bkt,
        })
        enriched.append(nt)
    return enriched


def daily_pnl_series(trades: list[dict], all_dates: list[str]) -> pd.Series:
    if not trades:
        return pd.Series(0.0, index=all_dates)
    s = pd.DataFrame(trades).groupby("date")["brl_1c"].sum()
    return s.reindex(all_dates, fill_value=0.0).astype(float)


def main():
    t0 = time.time()
    os.makedirs(RES_DIR, exist_ok=True)
    ft, _ = load_flow_tables("min")

    set_gex_paths(WIN_PLAIN, WDO_PLAIN)
    verify_gex_loaded("PROD_SIGNED_STUDY", WIN_PLAIN, WDO_PLAIN)

    signed_gex = {
        "WIN": load_signed_gex_map(WIN_SIGNED),
        "WDO": load_signed_gex_map(WDO_SIGNED),
    }

    with setups_runner._window(START, END, None, None):
        mk = setups_runner._load_market()
        df_win, _, _, _, _, df_wdo, _, _, _, _ = mk

        bm_win, dt_win = build_bar_lookup(df_win)
        bm_wdo, dt_wdo = build_bar_lookup(df_wdo)
        ctx_prov = ContextProvider(signed_gex, {"WIN": bm_win, "WDO": bm_wdo}, {"WIN": dt_win, "WDO": dt_wdo})
        runner = SimRunner(mk, ft, ctx_prov)

        # 0) Startup Live-Parity Check (Portfolio Elite 10 Robos)
        print("\n=== STARTUP LIVE-PARITY CHECK (0_BASE_MT5) ===")
        for asset, k, live_cap, ref_lbl in (
            [("WIN", k, 955, f"EST-{k:02d}") for k in WIN_LIVE_7]
            + [("WDO", k, 895, f"WDO-{k:02d}") for k in WDO_LIVE_3]
        ):
            tr_full = runner.run(asset, k, "0_BASE_MT5", "ALL", None)
            tr_cap = runner.run(asset, k, "0_BASE_MT5", "ALL", live_cap)
            s_full = stats(tr_full)
            s_cap = stats(tr_cap)
            print(
                f"  {ref_lbl}: full={s_full['ops']} tr (WR {s_full['wr']}% PF {s_full['pf']} R$ {s_full['net']:.0f}) | "
                f"cap_live={s_cap['ops']} tr (WR {s_cap['wr']}% PF {s_cap['pf']} R$ {s_cap['net']:.0f})"
            )

        # =====================================================================
        # TEST 1A: WDO LIVE 3 DEEP DIVE (WDO_01, WDO_05, WDO_07 + WDO_LIVE_3)
        # =====================================================================
        print("\n=== TEST 1A: WDO LIVE 3 DEEP DIVE ===")
        t1a_rows = []
        wdo_gates = [
            "ALL",
            "ONLY_POS_GAMMA",
            "ONLY_NEG_GAMMA",
            "POS_OR_NEAR_5",
            "POS_OR_NEAR_10",
            "POS_STRICT_5",
            "NO_FLIP_ZONE_10",
            "DIR_POS_SELL_NEG_BUY",
            "DIR_POS_BUY_NEG_SELL",
            "ALL_WITH_15H_CAP",
            "ONLY_POS_WITH_15H_CAP",
            "ONLY_NEG_WITH_15H_CAP",
        ]
        is_sel_cands = ["ALL", "ONLY_POS_GAMMA", "ONLY_NEG_GAMMA", "POS_OR_NEAR_5"]

        for flow_mode in ("0_BASE_MT5", "3_FLUXO_INST"):
            for gate in wdo_gates:
                comb = []
                for k in WDO_LIVE_3:
                    trs = runner.run("WDO", k, flow_mode, gate)
                    comb.extend(trs)
                    t1a_rows.append({"kind": "GATE", "sid": f"WDO_{k:02d}", "flow": flow_mode, "rule": gate, **eval_metrics(trs)})
                t1a_rows.append({"kind": "GATE", "sid": "WDO_LIVE_3", "flow": flow_mode, "rule": gate, **eval_metrics(comb)})

            # IS-selected per-slot rule
            sel_comb = []
            sel_desc = []
            for k in WDO_LIVE_3:
                best_g, best_score = "ALL", -1e9
                for gc in is_sel_cands:
                    s_is = stats(runner.run("WDO", k, flow_mode, gc), hi=SPLIT)
                    if s_is["ops"] >= 30 and s_is["net"] > 0 and s_is["ret_dd"] > best_score:
                        best_score = s_is["ret_dd"]
                        best_g = gc
                sel_desc.append(f"WDO_{k:02d}:{best_g}")
                sel_comb.extend(runner.run("WDO", k, flow_mode, best_g))
            t1a_rows.append({
                "kind": "GATE", "sid": "WDO_LIVE_3", "flow": flow_mode,
                "rule": f"IS_SEL({','.join(sel_desc)})", **eval_metrics(sel_comb),
            })

            # Post-trade attribution (regime x dir, dist_flip)
            base_comb = []
            for k in WDO_LIVE_3:
                etr = enrich_trades(runner.run("WDO", k, flow_mode, "ALL"), "WDO", ctx_prov)
                base_comb.extend(etr)
                df_e = pd.DataFrame(etr)
                for col, tag in (("b1_regime", "ATTR_B1_REG"), ("entry_regime", "ATTR_EP_REG"), ("reg_dir", "ATTR_REG_DIR"), ("dist_bkt", "ATTR_DIST")):
                    for val, grp in df_e.groupby(col):
                        t1a_rows.append({"kind": tag, "sid": f"WDO_{k:02d}", "flow": flow_mode, "rule": str(val), **eval_metrics(grp.to_dict("records"))})
            df_bc = pd.DataFrame(base_comb)
            for col, tag in (("b1_regime", "ATTR_B1_REG"), ("entry_regime", "ATTR_EP_REG"), ("reg_dir", "ATTR_REG_DIR"), ("dist_bkt", "ATTR_DIST")):
                for val, grp in df_bc.groupby(col):
                    t1a_rows.append({"kind": tag, "sid": "WDO_LIVE_3", "flow": flow_mode, "rule": str(val), **eval_metrics(grp.to_dict("records"))})

        df_t1a = pd.DataFrame(t1a_rows)
        df_t1a.to_csv(os.path.join(RES_DIR, "study_t1_wdo_live3_deep.csv"), index=False)

        # =====================================================================
        # TEST 1B: ALL 16 WDO SLOTS SCAN (0_BASE_MT5)
        # =====================================================================
        print("=== TEST 1B: ALL 16 WDO SLOTS SCAN ===")
        all_wdo_dates = sorted(df_wdo.loc[(df_wdo["session_date"] >= START) & (df_wdo["session_date"] <= END), "session_date"].unique())
        live3_base_trs = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "ALL")]
        live3_daily = daily_pnl_series(live3_base_trs, all_wdo_dates)

        t1b_rows = []
        for k in range(1, 17):
            for gate in ("ALL", "ONLY_POS_GAMMA", "ONLY_NEG_GAMMA"):
                trs = runner.run("WDO", k, "0_BASE_MT5", gate)
                s_d = daily_pnl_series(trs, all_wdo_dates)
                corr = float(s_d.corr(live3_daily)) if s_d.std() > 0 and live3_daily.std() > 0 else 0.0
                t1b_rows.append({
                    "sid": f"WDO_{k:02d}",
                    "is_live": k in WDO_LIVE_3,
                    "native_flip_rule": WDO_NATIVE_FLIP_RULE[k],
                    "gate": gate,
                    "corr_live3": round(corr, 3),
                    **eval_metrics(trs),
                })
        df_t1b = pd.DataFrame(t1b_rows)
        df_t1b.to_csv(os.path.join(RES_DIR, "study_t1_wdo_16_scan.csv"), index=False)

        # =====================================================================
        # TEST 1C: ALL 16 WIN SLOTS SCAN + PORTFOLIOS
        # =====================================================================
        print("=== TEST 1C: ALL 16 WIN SLOTS SCAN + PORTFOLIOS ===")
        t1c_rows = []
        for k in range(1, 17):
            for gate in ("ALL", "ONLY_POS_GAMMA", "ONLY_NEG_GAMMA"):
                trs = runner.run("WIN", k, "0_BASE_MT5", gate)
                t1c_rows.append({
                    "sid": f"EST_{k:02d}",
                    "is_live": k in WIN_LIVE_7,
                    "gate": gate,
                    **eval_metrics(trs),
                })
        df_t1c = pd.DataFrame(t1c_rows)
        df_t1c.to_csv(os.path.join(RES_DIR, "study_t1_win_16_scan.csv"), index=False)

        # Portfolio candidates (IS-selected inactive complements)
        inactive_neg_cands = df_t1b[(~df_t1b["is_live"]) & (df_t1b["gate"] == "ONLY_NEG_GAMMA") & (df_t1b["is_ops"] >= 40) & (df_t1b["is_pf"] >= 1.25) & (df_t1b["is_ret_dd"] >= 2.0)].sort_values("is_ret_dd", ascending=False)
        inactive_all_cands = df_t1b[(~df_t1b["is_live"]) & (df_t1b["gate"] == "ALL") & (df_t1b["is_ops"] >= 40) & (df_t1b["is_pf"] >= 1.25) & (df_t1b["is_ret_dd"] >= 2.0)].sort_values("is_ret_dd", ascending=False)
        top_inact_neg = [int(x.split("_")[1]) for x in inactive_neg_cands["sid"].head(2)]
        top_inact_all = [int(x.split("_")[1]) for x in inactive_all_cands["sid"].head(2)]

        # Best gate per WDO slot on IS across all 16 slots
        wdo16_best = []
        for k in range(1, 17):
            best_g, best_rdd = None, -1e9
            for g in ("ALL", "ONLY_POS_GAMMA", "ONLY_NEG_GAMMA"):
                sub = df_t1b[(df_t1b["sid"] == f"WDO_{k:02d}") & (df_t1b["gate"] == g)].iloc[0]
                if sub["is_ops"] >= 40 and sub["is_pf"] >= 1.25 and sub["is_ret_dd"] >= 2.0 and sub["is_ret_dd"] > best_rdd:
                    best_rdd = sub["is_ret_dd"]
                    best_g = g
            if best_g:
                wdo16_best.append((k, best_g, best_rdd))
        wdo16_best.sort(key=lambda x: x[2], reverse=True)

        wdo_live3_pos = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "ONLY_POS_GAMMA")]
        wdo_live3_neg = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", "ONLY_NEG_GAMMA")]
        wdo_live3_sel = []
        for k in WDO_LIVE_3:
            bg = max(("ALL", "ONLY_POS_GAMMA", "ONLY_NEG_GAMMA"), key=lambda g: stats(runner.run("WDO", k, "0_BASE_MT5", g), hi=SPLIT)["ret_dd"] if stats(runner.run("WDO", k, "0_BASE_MT5", g), hi=SPLIT)["ops"] >= 30 else -1e9)
            wdo_live3_sel.extend(runner.run("WDO", k, "0_BASE_MT5", bg))

        win_live7_base = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", "ALL")]
        win_live7_pos = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", "ONLY_POS_GAMMA")]
        win_live7_neg = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", "ONLY_NEG_GAMMA")]
        win_live7_sel = []
        for k in WIN_LIVE_7:
            bg = max(("ALL", "ONLY_POS_GAMMA", "ONLY_NEG_GAMMA"), key=lambda g: stats(runner.run("WIN", k, "0_BASE_MT5", g), hi=SPLIT)["ret_dd"] if stats(runner.run("WIN", k, "0_BASE_MT5", g), hi=SPLIT)["ops"] >= 30 else -1e9)
            win_live7_sel.extend(runner.run("WIN", k, "0_BASE_MT5", bg))

        port_specs = [
            ("WDO_LIVE_3_BASE", live3_base_trs),
            ("WDO_LIVE_3_POS_GAMMA", wdo_live3_pos),
            ("WDO_LIVE_3_NEG_GAMMA", wdo_live3_neg),
            ("WDO_LIVE_3_IS_SEL", wdo_live3_sel),
            (f"WDO_LIVE_3_POS+INACT_NEG({top_inact_neg})", wdo_live3_pos + [t for k in top_inact_neg for t in runner.run("WDO", k, "0_BASE_MT5", "ONLY_NEG_GAMMA")]),
            (f"WDO_LIVE_3_BASE+INACT_ALL({top_inact_all})", live3_base_trs + [t for k in top_inact_all for t in runner.run("WDO", k, "0_BASE_MT5", "ALL")]),
            (f"WDO_TOP5_IS_REGIME({[(k,g) for k,g,_ in wdo16_best[:5]]})", [t for k, g, _ in wdo16_best[:5] for t in runner.run("WDO", k, "0_BASE_MT5", g)]),
            ("WIN_LIVE_7_BASE", win_live7_base),
            ("WIN_LIVE_7_POS_GAMMA", win_live7_pos),
            ("WIN_LIVE_7_NEG_GAMMA", win_live7_neg),
            ("WIN_LIVE_7_IS_SEL", win_live7_sel),
            ("PORTFOLIO_10_BASE", win_live7_base + live3_base_trs),
            ("PORTFOLIO_10_WDO_POS", win_live7_base + wdo_live3_pos),
            ("PORTFOLIO_10_BOTH_POS", win_live7_pos + wdo_live3_pos),
            ("PORTFOLIO_10_IS_SEL", win_live7_sel + wdo_live3_sel),
        ]
        port_rows = [{"portfolio": name, **eval_metrics(trs)} for name, trs in port_specs]
        df_port = pd.DataFrame(port_rows)
        df_port.to_csv(os.path.join(RES_DIR, "study_t1_portfolio_summary.csv"), index=False)

        # =====================================================================
        # TEST 2: WALL GEX POLARITY (+GEX CALL_WALL vs -GEX PUT_WALL vs MIDWALL)
        # =====================================================================
        print("=== TEST 2: WALL GEX POLARITY ===")
        t2_rows = []
        pol_gates = ["ALL", "ONLY_CALL_WALL", "ONLY_PUT_WALL", "ONLY_WALL_ANY", "CALL_OR_MID", "NO_PUT_WALL", "NO_MIDWALL"]

        # Attribution
        wdo_all16_base = []
        for k in range(1, 17):
            etr = enrich_trades(runner.run("WDO", k, "0_BASE_MT5", "ALL"), "WDO", ctx_prov)
            wdo_all16_base.extend(etr)
            if k in WDO_LIVE_3:
                for val, grp in pd.DataFrame(etr).groupby("polarity"):
                    t2_rows.append({"kind": "ATTR", "group": f"WDO_{k:02d}", "rule": val, **eval_metrics(grp.to_dict("records"))})
        for lbl, tr_list in (("WDO_LIVE_3", [t for t in wdo_all16_base if t["strategy_id"] in {f"WDO_{k:02d}" for k in WDO_LIVE_3}]), ("WDO_ALL_16", wdo_all16_base)):
            for val, grp in pd.DataFrame(tr_list).groupby("polarity"):
                t2_rows.append({"kind": "ATTR", "group": lbl, "rule": val, **eval_metrics(grp.to_dict("records"))})

        win_live7_etr = []
        for k in WIN_LIVE_7:
            etr = enrich_trades(runner.run("WIN", k, "0_BASE_MT5", "ALL"), "WIN", ctx_prov)
            win_live7_etr.extend(etr)
            for val, grp in pd.DataFrame(etr).groupby("polarity"):
                t2_rows.append({"kind": "ATTR", "group": f"EST_{k:02d}", "rule": val, **eval_metrics(grp.to_dict("records"))})
        for val, grp in pd.DataFrame(win_live7_etr).groupby("polarity"):
            t2_rows.append({"kind": "ATTR", "group": "WIN_LIVE_7", "rule": val, **eval_metrics(grp.to_dict("records"))})

        # In-simulation polarity gating
        for gate in pol_gates:
            w_comb = []
            for k in WDO_LIVE_3:
                trs = runner.run("WDO", k, "0_BASE_MT5", gate)
                w_comb.extend(trs)
                t2_rows.append({"kind": "GATE", "group": f"WDO_{k:02d}", "rule": gate, **eval_metrics(trs)})
            t2_rows.append({"kind": "GATE", "group": "WDO_LIVE_3", "rule": gate, **eval_metrics(w_comb)})

            i_comb = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", gate)]
            t2_rows.append({"kind": "GATE", "group": "WIN_LIVE_7", "rule": gate, **eval_metrics(i_comb)})

        df_t2 = pd.DataFrame(t2_rows)
        df_t2.to_csv(os.path.join(RES_DIR, "study_t2_polarity.csv"), index=False)

        # =====================================================================
        # TEST 3: RELATIVE GEX CONCENTRATION (gex_share) vs width & COMBINED
        # =====================================================================
        print("=== TEST 3: CONCENTRATION & COMBINED RULES ===")
        t3_rows = []
        wdo_live3_etr = [t for t in wdo_all16_base if t["strategy_id"] in {f"WDO_{k:02d}" for k in WDO_LIVE_3}]
        for lbl, tr_list in (("WDO_LIVE_3", wdo_live3_etr), ("WIN_LIVE_7", win_live7_etr)):
            df_e = pd.DataFrame(tr_list)
            for col, kind in (("sh_bkt", "ATTR_SHARE"), ("wd_lbl", "ATTR_WIDTH")):
                for val, grp in df_e.groupby(col):
                    t3_rows.append({"kind": kind, "group": lbl, "rule": val, **eval_metrics(grp.to_dict("records"))})

        conc_gates = [
            "ALL",
            "ONLY_POS_GAMMA",
            "SHARE_GE_03",
            "SHARE_GE_05",
            "SHARE_GE_08",
            "RANK_TOP5",
            "RANK_TOP8",
            "WIDTH_GE_2",
            "POS_GAMMA_ONLY_WALL",
            "POS_GAMMA_CALL_WALL",
            "POS_GAMMA_NO_PUT_WALL",
            "POS_GAMMA_SHARE_GE_04",
            "POS_GAMMA_SHARE_GE_06",
            "POS_GAMMA_CALL_OR_MID",
        ]
        for gate in conc_gates:
            w_comb = [t for k in WDO_LIVE_3 for t in runner.run("WDO", k, "0_BASE_MT5", gate)]
            t3_rows.append({"kind": "GATE", "group": "WDO_LIVE_3", "rule": gate, **eval_metrics(w_comb)})
            i_comb = [t for k in WIN_LIVE_7 for t in runner.run("WIN", k, "0_BASE_MT5", gate)]
            t3_rows.append({"kind": "GATE", "group": "WIN_LIVE_7", "rule": gate, **eval_metrics(i_comb)})

        df_t3 = pd.DataFrame(t3_rows)
        df_t3.to_csv(os.path.join(RES_DIR, "study_t3_concentration.csv"), index=False)

        assert ctx_prov.misses == 0, f"Encontrados {ctx_prov.misses} misses em bar_map/signed_gex!"
        print(f"\n[CONCLUIDO] 0 misses em bar_map/signed_gex | Tempo total: {time.time() - t0:.1f}s")

        # Resumo rapido no stdout
        print("\n--- RESUMO T1A (WDO_LIVE_3 | 0_BASE_MT5) ---")
        sub = df_t1a[(df_t1a["sid"] == "WDO_LIVE_3") & (df_t1a["flow"] == "0_BASE_MT5") & (df_t1a["kind"] == "GATE")]
        print(sub[["rule", "ops", "wr", "pf", "ev", "net", "mdd", "ret_dd", "is_ops", "is_pf", "is_net", "is_ret_dd", "oos_ops", "oos_pf", "oos_ev", "oos_net", "oos_ret_dd"]].to_string(index=False))

        print("\n--- RESUMO T1A POR ROBO ATIVO WDO (0_BASE_MT5 | ALL vs POS vs NEG) ---")
        sub_r = df_t1a[(df_t1a["sid"].isin(["WDO_01", "WDO_05", "WDO_07"])) & (df_t1a["flow"] == "0_BASE_MT5") & (df_t1a["rule"].isin(["ALL", "ONLY_POS_GAMMA", "ONLY_NEG_GAMMA"]))]
        print(sub_r[["sid", "rule", "ops", "wr", "pf", "ev", "net", "ret_dd", "is_pf", "is_net", "oos_ops", "oos_pf", "oos_ev", "oos_net", "oos_ret_dd"]].to_string(index=False))

        print("\n--- TOP PORTFOLIOS ---")
        print(df_port[["portfolio", "ops", "wr", "pf", "ev", "net", "mdd", "ret_dd", "is_net", "is_ret_dd", "oos_ops", "oos_pf", "oos_net", "oos_ret_dd"]].to_string(index=False))


if __name__ == "__main__":
    main()
