"""
Verificador Oficial de Alinhamento Trade-a-Trade Python x MT5 Strategy Tester
=============================================================================
Compara os resultados dos simuladores Python do projeto:
  1. `research.optimizers.optimize_existing_16_setups` (EST-01, 02, 06, 07, 08, 12)
  2. `research.optimizers.test_win_aligned_wdo_matrix` (EST-04)
  3. `research.optimizers.sg_sim` (SmartGrids M1 tick-a-tick: EST-13, 14, 15, 16)
contra os relatórios `.htm` do Strategy Tester do MetaTrader 5 (`*_P1.htm`),
auditando o casamento individual de entradas, saídas, lotes e resultado financeiro (com e sem custo).
"""
import os
import re
import sys
import html
import numpy as np
import pandas as pd

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.discover_gex_nwe_setups as disc
import research.optimizers.optimize_existing_16_setups as o16
from research.optimizers.test_win_aligned_wdo_matrix import simulate_aligned_win_wdo_slot
import research.optimizers.sg_sim as sg_sim
import research.optimizers.wdo_mt5_sim as wdo_sim

REF_DIR = os.path.join(ROOT_DIR, "data", "reports", "mt5_tester_reference")
APPDATA_REP = os.path.join(
    os.environ.get("APPDATA", ""),
    r"MetaQuotes\Terminal\D0E8209F77C8CF37AD8BF550E51FF075\jumba_bt",
)
REP_DIR = REF_DIR if os.path.exists(os.path.join(REF_DIR, "EST01_P1.htm")) else APPDATA_REP

CFG = {
    1: ("3p", "CURRENT", "BE_WALL_SHIELD", 25.0, "TP_MAIN_WALL"),
    2: ("3p", "LIMIT_B1_MID", "BE_ZERO", 0.0, "TP_MAIN_WALL"),
    4: ("wdo", "ALIGNED", "BE_WALL_2STAGE_177K", 15.0, "TP_MIDWALL"),
    6: ("3p", "STOP_B1_EXT", "BE_WALL_SHIELD", 15.0, "TP_MAIN_WALL"),
    7: ("3p", "CURRENT", "BE_WALL_SHIELD", 15.0, "TP_CURRENT"),
    8: ("3p", "CURRENT", "BE_ZERO", 0.0, "TP_MAIN_WALL"),
    12: ("3p", "CURRENT", "BE_ZERO", 0.0, "TP_MAIN_WALL"),
}


def read_htm(p: str) -> str:
    raw = open(p, "rb").read()
    for enc in ("utf-16", "utf-8", "cp1252"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return ""


def cells(row: str):
    return [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


def num(s: str):
    s = s.replace("\xa0", "").replace(" ", "")
    m = re.match(r"-?[\d.,]+", s)
    if not m:
        return None
    t = m.group(0)
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)


def mt5_orders(ea: str) -> pd.DataFrame:
    o = []
    htm_path = os.path.join(REP_DIR, f"{ea}_P1.htm")
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", read_htm(htm_path), re.S):
        x = cells(r)
        if len(x) == 11 and re.match(r"\d{4}\.\d{2}\.\d{2}", x[0]) and x[9] == "filled":
            o.append(dict(
                t=pd.Timestamp(x[0].replace(".", "-")),
                typ=x[3],
                px=num(x[5]),
                sl=num(x[6]) if x[6] else None,
                tp=num(x[7]) if x[7] else None,
                cm=x[10],
            ))
    return pd.DataFrame(o)


def mt5_positions(ea: str) -> pd.DataFrame:
    deals = []
    htm_path = os.path.join(REP_DIR, f"{ea}_P1.htm")
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", read_htm(htm_path), re.S):
        x = cells(r)
        if len(x) >= 13 and re.match(r"\d{4}\.\d{2}\.\d{2}", x[0]) and x[4].lower() in ("in", "out", "in/out"):
            deals.append((pd.Timestamp(x[0].replace(".", "-")), x[3], x[4].lower(), num(x[5]), num(x[6]), (num(x[10]) or 0), x[12]))
    pos, net, cur = [], 0, None
    for t, typ, d, v, px, pnl, cm in deals:
        sgn = 1 if typ == "buy" else -1
        if d == "in":
            if net == 0:
                cur = dict(t_in=t, side=sgn, px_in=px, lots_max=0, lots_in=0.0, brl=0.0, t_out=None, why="", legs=0)
            net += sgn * v
            cur["lots_max"] = max(cur["lots_max"], abs(net))
            cur["lots_in"] += v
            cur["legs"] += 1
        else:
            net += sgn * v
            cur["brl"] += pnl
            cur["px_out"] = px
            if abs(net) < 1e-9:
                cur["t_out"] = t
                cur["why"] = cm[:2]
                pos.append(cur)
                cur = None
    return pd.DataFrame(pos)


def run_verification():
    os.makedirs(REF_DIR, exist_ok=True)
    df, gex = o16.load_win_and_wdo_aligned()
    c = df["close"].values
    n50 = disc.compute_nwe_series(c, lookback=50, bw=5.0, mult=2.0)
    n30 = disc.compute_nwe_series(c, lookback=30, bw=3.0, mult=1.6)
    dp = pd.Series(c).diff()
    rsi7 = (100.0 - (100.0 / (1.0 + (dp.clip(lower=0).rolling(7).mean() / (-dp.clip(upper=0)).rolling(7).mean().replace(0, 1e-6))))).fillna(50.0).values
    A = (df, gex, n50[0], n50[1], n50[2], n50[4], n30[0], n30[1], n30[2], n30[4], rsi7)
    T = pd.to_datetime(df["dt_brt"].values)

    cost_pts = float(os.environ.get("PY_COST", "0.0"))

    print("=" * 110)
    print(f"  1. CASAMENTO TRADE-A-TRADE M5 (EST-01, 02, 04, 06, 07, 08, 12) | cost_pts={cost_pts}")
    print("=" * 110)

    out_m5 = []
    for k in CFG:
        ea = f"EST{k:02d}"
        eng, ent, be, buf, tp = CFG[k]
        if eng == "3p":
            tr, _ = o16.simulate_single_est_slot(k, *A, entry_override=ent, be_mode=be, wall_shield_buf=buf, tp_mode=tp, cost_pts=cost_pts)
        else:
            tr, _ = simulate_aligned_win_wdo_slot(k, *A, be_mode=be, wall_shield_buf=buf, tp_mode=tp, entry_override=ent, cost_pts=cost_pts)
        p = pd.DataFrame(tr)
        p = p[p["date"] >= "2026-05-11"].copy()
        p["t_in"] = T[p["i_sig"].values]
        p["t_out"] = T[p["j_exit"].values] + pd.Timedelta(minutes=5)
        p.reset_index(drop=True, inplace=True)

        m = mt5_positions(ea)
        od = mt5_orders(ea).set_index("t")
        m["sl0"] = [od["sl"].get(t) if t in od.index and not isinstance(od["sl"].get(t), pd.Series) else None for t in m["t_in"]]
        m["tp0"] = [od["tp"].get(t) if t in od.index and not isinstance(od["tp"].get(t), pd.Series) else None for t in m["t_in"]]

        used = set()
        cat = []
        for _, r in p.iterrows():
            dt_sec = (m["t_in"] - r["t_in"]).abs().dt.total_seconds()
            ok = (dt_sec <= 900) & (m["side"] == r["side"]) & (~m.index.isin(used))
            if ok.any():
                j = dt_sec[ok].idxmin()
                used.add(j)
                mm = m.loc[j]
                same_exit = abs((mm["t_out"] - r["t_out"]).total_seconds()) <= 600
                cat.append(dict(
                    ea=ea, tipo="ambos", py_brl=r["pnl_brl"], mt5_brl=mm["brl"],
                    saida_igual=same_exit, py_lots=r["contracts"], mt5_lots=mm["lots_max"],
                ))
            else:
                cat.append(dict(ea=ea, tipo="so_python", py_brl=r["pnl_brl"], mt5_brl=0.0))
        for j, mm in m.iterrows():
            if j not in used:
                cat.append(dict(ea=ea, tipo="so_mt5", py_brl=0.0, mt5_brl=mm["brl"]))

        cdf = pd.DataFrame(cat)
        cdf.to_csv(os.path.join(REF_DIR, f"match_{ea}.csv"), index=False)
        both = cdf[cdf["tipo"] == "ambos"]
        match_pct = 100.0 * len(both) / max(1, len(m))
        out_m5.append(dict(
            EA=f"EST-{k:02d}",
            py_n=len(p),
            mt5_n=len(m),
            ambos=len(both),
            match_pct=f"{match_pct:.1f}%",
            so_py=int((cdf["tipo"] == "so_python").sum()),
            so_mt5=int((cdf["tipo"] == "so_mt5").sum()),
            saida_igual=f"{100 * both['saida_igual'].mean():.0f}%",
            ambos_py_brl=round(both["py_brl"].sum()),
            ambos_mt5_brl=round(both["mt5_brl"].sum()),
            lots_dif=int((both["py_lots"] != both["mt5_lots"]).sum()),
        ))

    print(pd.DataFrame(out_m5).to_string(index=False))

    print("\n" + "=" * 110)
    print(f"  2. CASAMENTO TRADE-A-TRADE SMARTGRIDS M1 (EST-13, 14, 15, 16) | cost_pts={cost_pts}")
    print("=" * 110)

    py_sg = sg_sim.run(cost_pts=cost_pts)
    py_sg.to_csv(os.path.join(REF_DIR, "sg_trades.csv"), index=False)
    rows_sg = []
    for k in (13, 14, 15, 16):
        m = mt5_positions(f"EST{k}")
        p = py_sg[py_sg["k"] == k].reset_index(drop=True)
        used = set()
        amb = []
        sp = 0
        for _, r in p.iterrows():
            dt_sec = (m["t_in"] - r["t_in"]).abs().dt.total_seconds()
            ok = (dt_sec <= 300) & (m["side"] == r["side"]) & (~m.index.isin(used))
            if ok.any():
                j = dt_sec[ok].idxmin()
                used.add(j)
                amb.append((r["brl"], m["brl"][j], r["lots"] == m["lots_max"][j], abs((m["t_out"][j] - r["t_out"]).total_seconds()) <= 600))
            else:
                sp += 1
        a = pd.DataFrame(amb, columns=["py", "mt", "lots_eq", "out_eq"])
        match_pct = 100.0 * len(a) / max(1, len(m))
        rows_sg.append(dict(
            EA=f"EST-{k:02d}",
            py_n=len(p),
            mt5_n=len(m),
            ambos=len(a),
            match_pct=f"{match_pct:.1f}%",
            so_py=sp,
            so_mt5=len(m) - len(used),
            lotes_iguais=f"{100 * a['lots_eq'].mean():.0f}%",
            saida_igual=f"{100 * a['out_eq'].mean():.0f}%",
            ambos_py_brl=round(a["py"].sum()),
            ambos_mt5_brl=round(a["mt"].sum()),
        ))

    print(pd.DataFrame(rows_sg).to_string(index=False))

    print("\n" + "=" * 110)
    print("  3. CASAMENTO TRADE-A-TRADE WDO M5 (WDO-02, 06, 07, 09, 10, 11, 15) | cost_pts=0.5 (R$ 5/ctr)")
    print("=" * 110)

    df_wdo_sum, tr_wdo_map = wdo_sim.run_all_wdo_slots(cost_pts=0.5)
    df_wdo_sum.to_csv(os.path.join(ROOT_DIR, "data", "reports", "wdo_mt5_alignment_summary.csv"), index=False)

    wdo_active = (2, 6, 7, 9, 10, 11, 15)
    rows_wdo = []
    mt5_wdo_daily_cost = {}
    py_wdo_daily_cost = {}
    for k in wdo_active:
        ea = f"WDO{k:02d}"
        p = pd.DataFrame(tr_wdo_map[k])
        aud_path = os.path.join(REF_DIR, f"audit_{ea}_P1.csv")
        m_aud = pd.read_csv(
            aud_path, sep=";", header=None,
            names=["close_time", "ea", "magic", "symbol", "dir", "lots", "avg_price", "exit_price", "pnl_brl_nocost", "reason"],
        )
        m_aud["close_dt"] = pd.to_datetime(m_aud["close_time"].str.replace(".", "-", regex=False))
        m_aud["date"] = m_aud["close_dt"].dt.strftime("%Y-%m-%d")
        m_aud["pnl_brl_cost"] = m_aud["pnl_brl_nocost"] - (0.5 * m_aud["lots"] * 10.0)
        mt5_wdo_daily_cost[k] = m_aud.groupby("date")["pnl_brl_cost"].sum()
        py_wdo_daily_cost[k] = p.groupby("date")["pnl_brl"].sum()

        n_min = min(len(p), len(m_aud))
        amb_exact = int((np.abs(p["pnl_brl"].values[:n_min] - m_aud["pnl_brl_cost"].values[:n_min]) < 0.01).sum())
        out_eq = int((np.abs((m_aud["close_dt"].values[:n_min] - p["exit_time"].values[:n_min]) / np.timedelta64(1, "s")) <= 300).sum())

        rows_wdo.append(dict(
            EA=f"WDO-{k:02d}",
            py_n=len(p),
            mt5_n=len(m_aud),
            match_count_pct=f"{100.0 * n_min / max(1, len(m_aud)):.1f}%",
            pnl_exact_pct=f"{100.0 * amb_exact / max(1, len(m_aud)):.1f}%",
            saida_igual=f"{100.0 * out_eq / max(1, n_min):.1f}%",
            py_brl_sem_custo=round(p["pnl_brl_nocost"].sum()),
            mt5_brl_sem_custo=round(m_aud["pnl_brl_nocost"].sum()),
            py_brl_com_custo=round(p["pnl_brl"].sum()),
            mt5_brl_com_custo=round(m_aud["pnl_brl_cost"].sum()),
        ))

    print(pd.DataFrame(rows_wdo).to_string(index=False))

    # 4. Carteira Consolidada WIN + WDO (MT5 com custo: R$ 2/ctr no WIN e R$ 5/ctr no WDO)
    mt5_win_daily_cost = {}
    for k in (1, 2, 4, 6, 7, 8, 12, 13, 14, 15, 16):
        ea = f"EST{k:02d}" if k < 13 else f"EST{k}"
        m = mt5_positions(ea)
        m["date"] = m["t_out"].dt.strftime("%Y-%m-%d")
        m["brl_cost"] = m["brl"] - 2.0 * m["lots_in"]
        mt5_win_daily_cost[k] = m.groupby("date")["brl_cost"].sum()

    def port_stats(label: str, win_keys: tuple, wdo_keys: tuple) -> dict:
        s_list = [mt5_win_daily_cost[k] for k in win_keys] + [mt5_wdo_daily_cost[k] for k in wdo_keys]
        df_d = pd.concat(s_list, axis=1).fillna(0.0)
        tot_d = df_d.sum(axis=1).sort_index()
        net = float(tot_d.sum())
        cum = tot_d.cumsum()
        dd = float((cum.cummax().clip(lower=0.0) - cum).max())
        ret_dd = net / dd if dd > 0 else 0.0
        worst = float(tot_d.min())
        win_days = float(100.0 * (tot_d > 0).mean())
        return dict(
            Carteira=label,
            Lucro_R_custo=round(net),
            Max_DD_R=round(dd),
            Ret_DD=round(ret_dd, 2),
            Pior_Dia_R=round(worst),
            Dias_Positivos_pct=round(win_days, 1),
        )

    print("\n" + "=" * 110)
    print("  4. COMPARATIVO DE CARTEIRAS MT5 COM CUSTO (WIN: R$ 2/ctr | WDO: R$ 5/ctr)")
    print("=" * 110)
    port_rows = [
        port_stats("WIN 11 Atuais (01,02,04,06,07,08,12,13,14,15,16)", (1, 2, 4, 6, 7, 8, 12, 13, 14, 15, 16), ()),
        port_stats("WIN 7 Recomendadas (01,04,07,13,14,15,16)", (1, 4, 7, 13, 14, 15, 16), ()),
        port_stats("WDO 7 Atuais (02,06,07,09,10,11,15)", (), (2, 6, 7, 9, 10, 11, 15)),
        port_stats("WDO 5 Sem 11 e 15 (02,06,07,09,10)", (), (2, 6, 7, 9, 10)),
        port_stats("WDO 4 Recomendadas (02,07,09,10)", (), (2, 7, 9, 10)),
        port_stats("CONSOLIDADO ATUAL: 11 WIN + 7 WDO (18 EAs)", (1, 2, 4, 6, 7, 8, 12, 13, 14, 15, 16), (2, 6, 7, 9, 10, 11, 15)),
        port_stats("CONSOLIDADO RECOMENDADO A: 7 WIN + 5 WDO (12 EAs)", (1, 4, 7, 13, 14, 15, 16), (2, 6, 7, 9, 10)),
        port_stats("CONSOLIDADO RECOMENDADO B: 7 WIN + 4 WDO (11 EAs)", (1, 4, 7, 13, 14, 15, 16), (2, 7, 9, 10)),
    ]
    df_port = pd.DataFrame(port_rows)
    df_port.to_csv(os.path.join(ROOT_DIR, "data", "reports", "mt5_alignment_summary.csv"), index=False)
    print(df_port.to_string(index=False))


if __name__ == "__main__":
    run_verification()

