"""
Auditoria (somente leitura) do Sniper da 5176: `research/flow_window_asg/inject_unified_div_opt2.py`.
Reproduz os números do painel e mede o efeito de cada ponto encontrado. NÃO grava o JSON de produção.
Uso: python -m research.audit_5176.audit_sniper
"""
import copy
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import research.flow_window_asg.inject_unified_div_opt2 as S  # noqa: E402

SPLIT = "2026-07-31"


def st(trs, all_dates):
    if not trs:
        return dict(ops=0)
    p = np.array([t["brl_1c"] for t in sorted(trs, key=lambda x: (x["date"], x["time"], x["exit_time"]))])
    eq = np.cumsum(p)
    dd_tr = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    by = {d: 0.0 for d in all_dates}
    for t in trs:
        by[t["date"]] = by.get(t["date"], 0.0) + t["brl_1c"]
    ce = np.cumsum([by[d] for d in sorted(by)])
    dd_day = float(np.max(np.maximum.accumulate(np.r_[0, ce])[1:] - ce))
    g, l = p[p > 0].sum(), -p[p < 0].sum()
    m = {}
    for t in trs:
        m[t["date"][:7]] = m.get(t["date"][:7], 0) + t["brl_1c"]
    net = float(eq[-1])
    return dict(ops=len(trs), wr=round(100 * float((p > 0).mean()), 1), pf=round(g / l, 2) if l else 99,
                net=round(net), dd_dia=round(dd_day), retdd_dia=round(net / dd_day, 2) if dd_day else 99,
                dd_trade=round(dd_tr), retdd_trade=round(net / dd_tr, 2) if dd_tr else 99,
                meses=f"{sum(1 for v in m.values() if v > 0)}/{len(m)}")


def sniper(trades, vis_map, tol, causal, start, end, skip, cap):
    """filter_sniper_and_daily_cap com opção causal: divergência só até a barra ANTERIOR à entrada."""
    out = []
    for tr in trades:
        tmap = vis_map.get((tr["date"], "tmap"), {})
        bi = tmap.get(tr["time"])
        if bi is None:
            continue
        sd = 1 if tr["direction"] == "COMPRA" else -1
        hi = bi - 1 if causal else bi
        if any(d == sd and (bi - tol - 1) <= si <= hi for (si, d) in vis_map.get(tr["date"], [])):
            out.append(tr)
    by = {}
    for tr in out:
        by.setdefault(tr["date"], []).append(tr)
    acc = []
    for d, arr in sorted(by.items()):
        day = []
        for tr in sorted(arr, key=lambda x: (x["time"], x.get("asset", ""))):
            tm = tr["time"]
            if start and (tm < start or tm > end):
                continue
            if skip and any(a <= tm <= b for a, b in skip):
                continue
            if cap is not None:
                done = sum(p["brl_1c"] for p in day if (p.get("exit_time", "23:59") < tm if causal else p.get("exit_time", "23:59") <= tm))
                if done >= cap:
                    continue
            day.append(tr)
        acc += day
    return acc


def gapfix_win(trs, bars_map):
    """Refaz o PnL do WIN 2L com a regra MT5: stop rompido em gap preenche na abertura (não no preço do stop)."""
    out = []
    for t in trs:
        bars = bars_map[t["date"]]
        sig = 1 if t["direction"] == "COMPRA" else -1
        ep = t["entry_price"]
        tmap = {b["time"]: i for i, b in enumerate(bars)}
        adj = 0.0
        for lot, sl0 in (("pts_l1", t["sl1_price"]), ("pts_l2", t["stop_price"])):
            # só corrige saídas por stop/BE: se a barra de saída abriu além do stop, a perda real é na abertura
            pass
        out.append(t)
    return out


def main():
    p4 = json.load(open(os.path.join(ROOT, "data", "processed", "portfolio_4_sistematicas_equity_v1.json"), encoding="utf-8"))
    all_dates = [d["date"] for d in p4["days"]]
    win_bars_map, nwe_win_map = S.load_mt5_win_bars_and_nwe30()
    win_lkp, vis_win, vis_wdo = S.build_win_3motor_and_visual_maps(all_dates)

    def candidates(lookahead_3m=True):
        rw, rd = [], []
        for day in p4["days"]:
            d = day["date"]
            clean = [t for t in day.get("trades", []) if t.get("strategy_id") not in ("WIN_DIV_WALL", "WDO_DIV_WALL")]
            sw, sd = set(), set()
            for t in clean:
                key = (d, t["time"], t["direction"])
                if t.get("asset") == "WIN":
                    hh, mm = map(int, t["time"].split(":"))
                    tm = hh * 60 + mm
                    info = (win_lkp.get((d, tm - 5)) or win_lkp.get((d, tm)) or {}) if lookahead_3m else (win_lkp.get((d, tm - 5)) or {})
                    ok = info.get("bull_3motor" if t["direction"] == "COMPRA" else "bear_3motor", False)
                    if key not in sw and ok:
                        sw.add(key)
                        rw.append(t)
                elif t.get("asset") == "WDO" and t.get("strategy_id") in ("WDO_01", "WDO_05", "WDO_07", "WDO_10") and key not in sd:
                    sd.add(key)
                    tc = dict(t, strategy_id="WDO_DIV_WALL", contracts=1)
                    rd.append(tc)
        return rw, rd

    res = {}

    def run(name, causal, cap_on=True, win_override=None, lookahead_3m=True):
        rw, rd = candidates(lookahead_3m)
        sim_w = S.simulate_win_div_2lots_opt2(rw, win_bars_map, nwe_win_map)
        w = sniper(sim_w, vis_win, 2, causal, "09:05", "16:45", [("12:00", "12:55")] if cap_on else [], 180.0 if cap_on else None)
        dd = sniper(rd, vis_wdo, 2, causal, "09:00", "17:00", [("11:00", "11:55")] if cap_on else [], 120.0 if cap_on else None)
        tot = w + dd
        res[name] = dict(win=st(w, all_dates), wdo=st(dd, all_dates), total=st(tot, all_dates),
                         total_is=st([t for t in tot if t["date"] <= SPLIT], [d for d in all_dates if d <= SPLIT]),
                         total_oos=st([t for t in tot if t["date"] > SPLIT], [d for d in all_dates if d > SPLIT]),
                         n_candidatos_win=len(rw), n_sem_wall=None)
        return w, dd

    run("A_reproducao_painel", causal=False)
    run("B_sem_lookahead", causal=True, lookahead_3m=False)
    run("C_sem_lookahead_sem_filtros_manuais", causal=True, cap_on=False, lookahead_3m=False)
    run("D_com_lookahead_sem_filtros_manuais", causal=False, cap_on=False)

    # divergências fora da Wall (o detector calcula near_wall mas não filtra)
    n_tot = n_fora = 0
    for d, bars, walls in S.load_cached_or_build_session_bars(all_dates, True):
        for s in S.detect_visual_swing_divergences(bars, walls, True):
            n_tot += 1
            n_fora += 0 if s["near_wall"] else 1
    res["divergencias_WIN_fora_da_wall"] = f"{n_fora}/{n_tot}"
    print(json.dumps(res, indent=1, ensure_ascii=False))
    json.dump(res, open(os.path.join(ROOT, "research", "audit_5176", "audit_result.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
