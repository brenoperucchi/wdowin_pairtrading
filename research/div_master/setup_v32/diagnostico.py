# -*- coding: utf-8 -*-
import json, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from motor_addon import *
from collections import Counter

# --- descarte E22 jan-jul / ago-nov ---
data = {d: v for d, v in load_asset("WIN", "M5").items() if d <= END}
DS = bt.market("WIN")
cnt_is, cnt_all = Counter(), Counter()
n_trig_is = n_trig_all = 0
entered_is = entered_all = 0
for d in sorted(data):
    if d not in DS:
        continue
    fb, walls, ex = day_inputs(DS, data, d, "WIN")
    trs, rows = classify_e22_funnel(fb, walls, ex)
    isv = d <= IS_END
    for r in rows:
        n_trig_all += 1
        if isv:
            n_trig_is += 1
        if r.get("entered"):
            entered_all += 1
            if isv:
                entered_is += 1
            key = "entrou"
        else:
            key = "+".join(r["reasons"]) or "ok"
        cnt_all[key] += 1
        if isv:
            cnt_is[key] += 1
print("TRIG ALL", n_trig_all, "entrou", entered_all)
print("IS", dict(cnt_is))
print("ALL", dict(cnt_all))
print("IS trig", n_trig_is, "entrou", entered_is)

# G4 debug: quantos candidatos teriam ext<=-0.8
P = M.PARAMS["WIN"]
n_c = n_ext = n_g4 = 0
for d in sorted(data):
    if d not in DS or d > IS_END:
        continue
    fb, walls, ex = day_inputs(DS, data, d, "WIN")
    lv = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES)
    atr = M.atr_series(fb, P["tick"])
    cs = M.engine_v32(fb, lv, P, "common", atr=atr, opt=M.V32_PROD)
    pos = DS[d]["pos"]
    for c in cs:
        n_c += 1
        t = first_hit(fb, c, P, "G4", D=DS[d], pos=pos, tick=5.0, levels=lv)
        if t is not None:
            n_g4 += 1
print("G4 jan-jul cands", n_c, "hits", n_g4)

# 13/11 sanity from snapshot if present
snap_p = os.path.join(ROOT, "_tmp_box_copy", "compass_1311.json")
print("snapshot", os.path.exists(snap_p))
if os.path.exists(snap_p):
    data13 = json.loads(open(snap_p, encoding="utf-8").read())

    def session_bars(asset):
        raw = data13[asset]["caminho_a"]["m5_dealer_vs_flow_series"]
        out = []
        for b in raw:
            if b.get("is_prev_day"):
                continue
            t = str(b.get("time") or "")
            t = t[11:16] if len(t) >= 16 else t[:5]
            out.append(dict(time=t, open=float(b["open"]), high=float(b["high"]), low=float(b["low"]),
                            close=float(b["close"]), wave=float(b.get("smart_swing_wave") or 0.0),
                            nwe50_line=b.get("nwe50_line") or 0.0, nwe50_upper=b.get("nwe50_upper") or 0.0,
                            nwe50_lower=b.get("nwe50_lower") or 0.0))
        return out

    def walls(asset):
        return [{"type": w["type"], "price": w["price"]} for w in data13[asset]["all_walls"] if w.get("type") in M.LEVEL_TYPES]

    for asset in ("WIN", "WDO"):
        fb = session_bars(asset)
        wl = walls(asset)
        Prm = M.PARAMS[asset]
        lv = sorted(w["price"] for w in wl)
        atr = M.atr_series(fb, Prm["tick"])
        cs = M.engine_v32(fb, lv, Prm, "common", atr=atr, opt=M.V32_PROD)
        if asset == "WIN":
            trs, rows = classify_e22_funnel(fb, wl, fb)
            print("13/11 E22 trades", [(t["time"], t["direction"], t["exit_time"], t["exit_reason"], t.get("be_time")) for t in trs])
            print("13/11 funil:")
            for r in rows:
                x = r["x"]
                print(" ", "VENDA" if x["dir"]==-1 else "COMPRA", x["time"], "seq", r["seq"], "super", x["super"],
                      "reasons", r["reasons"], "ent", r.get("t_in"))
            # T1 G1 would take super/seq with NWE
            print("13/11 T1-G1 candidatos (sinal):")
            for r in rows:
                if r.get("t_in") and ("super" in r["reasons"] or "seq" in r["reasons"]):
                    if r.get("ext") is not None and r["ext"] > -0.5 and r["slope"] > -0.5 and T_START <= r["tm"] < T_END:
                        print("  PASSA filtro T1-G1", r["t_in"], r["reasons"], "ext", round(r["ext"],2), "slope", round(r["slope"],2))
                        # coexist
                        ok = allowed_vs_e22(r["tm"], r["x"]["dir"], [
                            dict(tm=hm(t["time"]), xt=hm(t["exit_time"]), d=t["dir_num"],
                                 be_tm=hm(t["be_time"]) if t.get("be_time") else None) for t in trs])
                        print("   coexistencia", ok)
        else:
            trig, _ = M.triggers(fb, cs, Prm)
            print("13/11 WDO OPC:")
            for x in trig:
                t_in = fb[x["idx"]+1]["time"] if x["idx"]+1 < len(fb) else None
                print(" ", x["dir"], x["esp"], x["sub"], "trig", x["time"], "in", t_in, "super", x["super"],
                      "janela", t_in and T_START <= hm(t_in) < T_END)
