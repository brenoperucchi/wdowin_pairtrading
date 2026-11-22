"""Robustez e diagnóstico completo dos principais candidatos da Fase 1 no WDO."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import modulo as M
from research.div_master.especialistas import bt

raw_m5 = {d: v for d, v in load_asset("WDO", "M5").items() if d <= bt.END}
DS = bt.market("WDO")
X = bt.X["WDO"]
P = M.PARAMS["WDO"]
lo_w, hi_w = bt.WINDOW["WDO"]
D_args = {d: bt._args(D) for d, D in DS.items()}


def sim_pessimistic(D, band, e, ep, d, sl, tp_fix, use_band, front, tp_lo, tp_hi, be_trig, be_lock, tmax,
                    tick, cost, stop_slip, entry_slip, adv_m1=False):
    """Simulador M1 explícito (permite cost, stop_slip, entry_slip e pior caminho M1 intra-minuto)."""
    ep_eff = ep + d * entry_slip
    stop = ep_eff - d * sl
    be_hit = False
    max_fav = 0.0
    px = D["px"]
    op = D["op"]
    off = D["off"]
    nn = D["nn"]
    fb = D["fb"]
    o5 = D["o5"]
    c5 = D["c5"]
    tm5 = D["tm5"]
    n_b = len(o5)

    for k in range(e, n_b):
        if k > e and tm5[k] >= 1045:
            return (d * (o5[k] - ep_eff) - cost) * X["brl"], int(tm5[k])
        if k - e > tmax:
            return (d * (o5[k] - ep_eff) - cost) * X["brl"], int(tm5[k])

        if use_band:
            tgt = band[k] - d * front
            dist = d * (tgt - ep_eff)
            if dist < tp_lo:
                tgt = ep_eff + d * tp_lo
            elif dist > tp_hi:
                tgt = ep_eff + d * tp_hi
        else:
            tgt = tp_fix

        if fb[k] == 1:
            return (d * (c5[k] - ep_eff) - cost) * X["brl"], int(tm5[k])

        s_i = int(off[k])
        cnt = int(nn[k])
        for m in range(s_i, s_i + cnt):
            p = float(px[m])
            is_o = bool(op[m])
            # Se adv_m1=True, dentro de cada bloco de 4 ticks M1, checa stop antes se o tick p não for open
            if d == 1:
                if p <= stop:
                    fill = p if is_o else stop - stop_slip
                    return (fill - ep_eff - cost) * X["brl"], int(tm5[k])
                if p >= tgt:
                    if adv_m1 and not is_o:
                        # Checa se no restante do bloco de 4 ticks deste minuto tem stop antes
                        blk_end = min(s_i + cnt, ((m - s_i) // 4 + 1) * 4 + s_i)
                        hit_sl = any(float(px[q]) <= stop for q in range(m, blk_end))
                        if hit_sl:
                            return (stop - stop_slip - ep_eff - cost) * X["brl"], int(tm5[k])
                    return (tgt - ep_eff - cost) * X["brl"], int(tm5[k])
                fav = p - ep_eff
            else:
                if p >= stop:
                    fill = p if is_o else stop + stop_slip
                    return (ep_eff - fill - cost) * X["brl"], int(tm5[k])
                if p <= tgt:
                    if adv_m1 and not is_o:
                        blk_end = min(s_i + cnt, ((m - s_i) // 4 + 1) * 4 + s_i)
                        hit_sl = any(float(px[q]) >= stop for q in range(m, blk_end))
                        if hit_sl:
                            return (ep_eff - (stop + stop_slip) - cost) * X["brl"], int(tm5[k])
                    return (ep_eff - tgt - cost) * X["brl"], int(tm5[k])
                fav = ep_eff - p

            if be_trig > 0.0 and not be_hit and fav >= be_trig:
                be_hit = True
                if d == 1:
                    stop = max(stop, ep_eff + be_lock)
                else:
                    stop = min(stop, ep_eff - be_lock)

    return (d * (c5[-1] - ep_eff) - cost) * X["brl"], int(tm5[-1])


def eval_trades(rows, exit_fn, mgmt="UM", **sim_kw):
    if not rows:
        return dict(ops=0, rdd=0.0)
    df_t = pd.DataFrame(rows).sort_values(["date", "tm", "j"]).reset_index(drop=True)
    pnls, xts = [], []
    for r in df_t.itertuples():
        D = DS[r.date]
        p, xt = exit_fn(D, r, **sim_kw)
        pnls.append(p)
        xts.append(xt)
    df_t["pnl"] = pnls
    df_t["xt"] = xts
    if mgmt == "UM":
        keep = []
        last_d, last_xt = None, -1
        for i, r in enumerate(df_t.itertuples()):
            if r.date != last_d:
                last_d, last_xt = r.date, -1
            if r.tm <= last_xt:
                continue
            keep.append(i)
            last_xt = r.xt
        df_t = df_t.iloc[keep].copy()
    return bt.stats(df_t, "pnl", "xt"), df_t


def collect_engine_signals(engine, mode="OPC", use_open_v32=False, levels_filter="all", nodiv=False):
    out = []
    for d in sorted(raw_m5):
        D = DS.get(d)
        if D is None:
            continue
        bars, walls, _ = raw_m5[d]
        fb = M.compute_flow(bars, "WDO")
        atr = M.atr_series(fb, P["tick"])
        w_all = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
        w_wall = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall")
        w_lv = w_wall if levels_filter == "wall_only" else w_all

        if nodiv:
            # Placebo sem divergência: todos os pivôs ZigZag + L2/R1 com âncora, sem exigir divergência de onda!
            cands = []
            piv_zz = M.zigzag(fb, atr, M.COMMON["r_atr"], P["zz_floor"])
            seen = set()
            evs = [(p["conf"], p["idx"], p["side"]) for p in piv_zz]
            for j in range(2, len(fb) - 1):
                for dr in (1, -1):
                    if M.is_piv(fb, j, dr, 2, 1):
                        evs.append((j + 1, j, dr))
            for conf, j, dr in sorted(evs):
                if (dr, j) in seen or conf + 1 >= len(fb):
                    continue
                seen.add((dr, j))
                a = M.anchors(fb, j, dr, w_lv, P)
                if not M.eligible(a, "common", fb, j, dr, w_lv, P):
                    continue
                cands.append(M._cand("placebo", dr, j, max(0, j - 5), conf, fb, 0.0, 0.0, 1.0, a))
        elif engine == "v3.1":
            cands = M.engine_v31(fb, w_lv, P, "common", atr=atr)
        elif engine == "v3.2":
            opt = {**M.V32, "abertura": M.V22_ABERTURA} if use_open_v32 else M.V32_PROD
            cands = M.engine_v32(fb, w_lv, P, "all", atr=atr, opt=opt)
        elif engine == "v2.2":
            cands = M.engine_v22(fb, w_lv, P, "common", atr=atr, opt=M.V22_ABERTURA)
        elif engine == "v3":
            cands = M.engine_v3(fb, w_lv, P, "common")

        trigs, _ = M.triggers(fb, cands, P)
        opc_by = {(tr["dir"], tr["j"]): tr for tr in trigs if not tr["dup"]}

        for c in cands:
            dr, j, conf = c["dir"], c["j"], c["conf"]
            if mode == "OPC":
                tr = opc_by.get((dr, j))
                if tr is None or tr["idx"] + 1 >= len(fb):
                    continue
                idx_in = tr["idx"] + 1
                esp = tr["esp"]
            else:
                if conf + 1 >= len(fb):
                    continue
                idx_in = conf + 1
                esp = "SUPER" if (c["c1"] or c["c2"]) and c["day"] else ("FURO" if c["c1"] else ("WALL" if c["c2"] else ("EXT" if c["day"] else "NONE")))

            tm = bt.hm(fb[idx_in]["time"])
            if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
                continue
            e = D["pos"][tm]
            ep = float(D["o5"][e])
            half = max(float(D["u50"][e] - D["c50"][e]), X["tick"])
            ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half if e >= 1 else np.nan
            slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half
            ext30 = -dr * float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / max(0.5 * (D["u30"][e] - D["l30"][e]), X["tick"]) if e >= 1 else np.nan
            px2 = float(c["px2"])
            d_wall = min((abs(px2 - w) for w in w_wall), default=999.0)
            pass_sum = dr * sum(float(fb[x].get("inst_pass_delta", 0)) for x in range(j, conf + 1))
            wyck_sum = dr * sum(float(fb[x].get("wyckoff_abs", 0)) for x in range(j, conf + 1))
            candle_dir = dr * (float(fb[conf]["close"]) - float(fb[conf]["open"])) > 0
            out.append(dict(
                date=d, e=e, ep=ep, dir=dr, j=j, conf=conf, tm=tm, hora=tm // 100,
                anc=esp, has_c1=c["c1"] is not None, has_c2=c["c2"] is not None, has_day=c["day"] is not None,
                d_wall=d_wall, ext50=ext50, slope50=slope50, ext30=ext30,
                wd_ratio=float(c["wd"]) / max(float(c["thr"]), 1e-9),
                pass_=pass_sum, wyck=wyck_sum, candle_dir=candle_dir, micro=bool(c["micro"]),
            ))
    return out


# ── Exit functions ──
def mk_n30(sl, be_t=0.0, be_l=0.0, tmax=24):
    def fn(D, r, cost=0.5, stop_slip=0.5, entry_slip=0.0, adv_m1=False, inv=False):
        dr = -r.dir if inv else r.dir
        band = D["u30"] if dr == 1 else D["l30"]
        return sim_pessimistic(D, band, r.e, r.ep, dr, sl, 0.0, True, X["front"], 2.0, 30.0,
                               be_t, be_l, tmax, X["tick"], cost, stop_slip, entry_slip, adv_m1)
    return fn

def mk_fix(sl, tp, be_t=0.0, be_l=0.0, tmax=24):
    def fn(D, r, cost=0.5, stop_slip=0.5, entry_slip=0.0, adv_m1=False, inv=False):
        dr = -r.dir if inv else r.dir
        tp_px = r.ep + dr * entry_slip + dr * (tp if tp > 0 else 1e9)
        return sim_pessimistic(D, D["u30"], r.e, r.ep, dr, sl, tp_px, False, 0.0, 0.0, 0.0,
                               be_t, be_l, tmax, X["tick"], cost, stop_slip, entry_slip, adv_m1)
    return fn

def mk_n50(sl, be_t=0.0, be_l=0.0, tmax=24):
    def fn(D, r, cost=0.5, stop_slip=0.5, entry_slip=0.0, adv_m1=False, inv=False):
        dr = -r.dir if inv else r.dir
        band = D["u50"] if dr == 1 else D["l50"]
        return sim_pessimistic(D, band, r.e, r.ep, dr, sl, 0.0, True, X["front"], 2.0, 40.0,
                               be_t, be_l, tmax, X["tick"], cost, stop_slip, entry_slip, adv_m1)
    return fn


print("=== 1. DIAGNOSTICO FAMILIA A: v3.1 | OPC | WALL_ONLY | ext50 ===")
s_v31 = collect_engine_signals("v3.1", "OPC", levels_filter="all")
s_v31_w = collect_engine_signals("v3.1", "OPC", levels_filter="wall_only")
s_plac = collect_engine_signals("placebo", "OPC", levels_filter="all", nodiv=True)

print("\n[Plateau d_wall x ext50 com N30 sl=10 tm=24 (UM)]")
for dw in (2.5, 3.0, 3.5, 4.0, 5.0, 999.0):
    row_s = []
    for e5 in (-0.5, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5):
        sub = [r for r in s_v31 if r["d_wall"] <= dw and r["ext50"] > e5]
        st, _ = eval_trades(sub, mk_n30(10.0), mgmt="UM")
        row_s.append(f"e>{e5:+.1f}:{st['rdd']:4.1f}({st['ops']})")
    print(f"  dw<={dw:5.1f} | " + "  ".join(row_s))

print("\n[Plateau SL x Saida fixa/N30 com d_wall<=3.5 & ext50>0.3 (UM)]")
base_a = [r for r in s_v31 if r["d_wall"] <= 3.5 and r["ext50"] > 0.3]
for sl in (6.5, 8.5, 10.0, 12.0, 14.0):
    outs = []
    for label, fn in [("N30", mk_n30(sl)), ("N30_be4", mk_n30(sl, 4.0, 1.0)),
                      ("tp4", mk_fix(sl, 4.0)), ("tp6", mk_fix(sl, 6.0)),
                      ("tp9", mk_fix(sl, 9.0)), ("tp12", mk_fix(sl, 12.0))]:
        st, _ = eval_trades(base_a, fn, mgmt="UM")
        outs.append(f"{label}:{st['rdd']:4.2f}[{st['h1']}/{st['h2']}/{st['oos']}]")
    print(f"  SL={sl:4.1f} | " + " ".join(outs))

print("\n[v3.1 passando APENAS Wall (sem MidWall) no motor vs Filtro d_wall<=3.5]")
for e5 in (0.0, 0.2, 0.3):
    sub = [r for r in s_v31_w if r["anc"] == "WALL" and r["ext50"] > e5]
    st, _ = eval_trades(sub, mk_n30(10.0), mgmt="UM")
    print(f"  wall_only engine | WALL | ext50>{e5:.1f} -> {st}")

print("\n[Stress + Placebo + Invertida na Familia A (v3.1 OPC d_wall<=3.5 ext50>0.3)]")
for label, fn in [("N30_sl10", mk_n30(10.0)), ("N30_sl12_be4", mk_n30(12.0, 4.0, 1.0)), ("tp6_sl12_tm12", mk_fix(12.0, 6.0, tmax=12))]:
    print(f"  >> {label}")
    print("     Base (0.5/0.5):         ", eval_trades(base_a, fn, mgmt="UM")[0])
    print("     LIVRE (sem UM):         ", eval_trades(base_a, fn, mgmt="LIVRE")[0])
    print("     Custo 2x (1.0/0.5):     ", eval_trades(base_a, fn, mgmt="UM", cost=1.0)[0])
    print("     Pesado (1.0/1.0/+0.5e): ", eval_trades(base_a, fn, mgmt="UM", cost=1.0, stop_slip=1.0, entry_slip=0.5)[0])
    print("     Pior M1 + Pesado:       ", eval_trades(base_a, fn, mgmt="UM", cost=1.0, stop_slip=1.0, entry_slip=0.5, adv_m1=True)[0])
    print("     Invertida (-dir):       ", eval_trades(base_a, fn, mgmt="UM", inv=True)[0])
    plac_a = [r for r in s_plac if r["d_wall"] <= 3.5 and r["ext50"] > 0.3]
    print("     Placebo SEM diverg.:    ", eval_trades(plac_a, fn, mgmt="UM")[0])


print("\n=== 2. DIAGNOSTICO FAMILIA B: v3.2 | OPC | EXT_OR_FURO / EXTREMO | PASS_POS ===")
s_v32 = collect_engine_signals("v3.2", "OPC", use_open_v32=False)
s_v32_open = collect_engine_signals("v3.2", "OPC", use_open_v32=True)
base_b = [r for r in s_v32 if (r["has_c1"] or r["has_day"]) and r["pass_"] > 0]
print("  v3.2 open_module=False count:", len(s_v32), "| open_module=True count:", len(s_v32_open))
for sl in (8.5, 10.0, 12.0, 14.0):
    for label, fn in [("N50", mk_n50(sl)), ("tp10", mk_fix(sl, 10.0)), ("tp12", mk_fix(sl, 12.0)), ("tp15", mk_fix(sl, 15.0))]:
        st, _ = eval_trades(base_b, fn, mgmt="UM")
        print(f"  B SL={sl:4.1f} {label:5s} -> ops={st['ops']} wr={st['wr']} pf={st['pf']} net={st['net']} dd={st['dd']} rdd={st['rdd']} ({st['meses']}) h1={st['h1']} h2={st['h2']} oos={st['oos']}")

print("\n[Stress + Placebo + Invertida na Familia B (tp12 sl10)]")
fn_b = mk_fix(10.0, 12.0)
print("  Base (0.5/0.5):         ", eval_trades(base_b, fn_b, mgmt="UM")[0])
print("  Pesado (1.0/1.0/+0.5e): ", eval_trades(base_b, fn_b, mgmt="UM", cost=1.0, stop_slip=1.0, entry_slip=0.5, adv_m1=True)[0])
print("  Invertida (-dir):       ", eval_trades(base_b, fn_b, mgmt="UM", inv=True)[0])
plac_b = [r for r in s_plac if (r["has_c1"] or r["has_day"]) and r["pass_"] > 0]
print("  Placebo SEM diverg.:    ", eval_trades(plac_b, fn_b, mgmt="UM")[0])


print("\n=== 3. DIAGNOSTICO FAMILIA C: v2.2 | OPC | HAS_DAY | wd_ratio ===")
s_v22 = collect_engine_signals("v2.2", "OPC")
for wd_max in (1.5, 1.8, 2.0, 2.5, 99.0):
    sub = [r for r in s_v22 if r["has_day"] and r["wd_ratio"] <= wd_max]
    st, _ = eval_trades(sub, mk_fix(8.5, 6.0), mgmt="UM")
    print(f"  v2.2 HAS_DAY wd<={wd_max:4.1f} -> {st}")
base_c = [r for r in s_v22 if r["has_day"] and r["wd_ratio"] <= 2.0]
fn_c = mk_fix(8.5, 6.0)
print("  Pesado (1.0/1.0/+0.5e): ", eval_trades(base_c, fn_c, mgmt="UM", cost=1.0, stop_slip=1.0, entry_slip=0.5, adv_m1=True)[0])
print("  Invertida (-dir):       ", eval_trades(base_c, fn_c, mgmt="UM", inv=True)[0])
