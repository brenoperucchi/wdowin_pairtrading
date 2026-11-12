"""Compara as marcações do rotulador (research/div_master/labels/labels.csv) com os sinais do detector v3 (WIN)."""
import json, sys, os
import numpy as np, pandas as pd
from datetime import datetime, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
from research.div_wall.data import load_asset
from core.div_wall_signal import compute_flow, detect_divergences_v3, DivParamsV2
from core.profit_mt5_flow_engine import load_daily_magic_walls
B = os.path.join(ROOT, "research", "div_master")
LIVE11 = sys.argv[1] if len(sys.argv) > 1 else None


def m(t):
    h, mm = map(int, t.split(":")); return h * 60 + mm


def effective():
    L = pd.read_csv(os.path.join(B, "labels", "labels.csv"))
    und = set(L[L.action == "UNDO"].undo_of)
    live = L[L.action.isin(["LABEL", "ADD"]) & ~L.action_id.isin(und)]
    e = pd.concat([live[live.action == "LABEL"].sort_values("ts").groupby("cand_id").tail(1), live[live.action == "ADD"]])
    e["tipo"] = e.tipo.fillna("-").astype(str)
    return e


def day_v3(d, D):
    if d == "2026-11-11" and LIVE11:
        bars = [dict(x) for x in json.load(open(LIVE11, encoding="utf-8-sig"))["WIN"]["m5_cvd_series"]]
        for x in bars:
            x["time"] = datetime.fromtimestamp(int(x["time"]), timezone.utc).strftime("%H:%M")
        walls = load_daily_magic_walls("WIN", d); z = np.zeros(len(bars)); nwe = (z, z, z)
    else:
        bars, walls, nwe = D[d]
    fb = compute_flow(bars, "WIN")
    sg = detect_divergences_v3(fb, walls, nwe, DivParamsV2.default("WIN", nwe_filter="none"))
    return fb, [dict(dir=s.direction, f1=fb[s.f1_idx]["time"], f2=fb[s.pivot_idx]["time"], sig=s.time, px=s.pivot_px,
                     kind=s.wall_type, wall=s.wall_px, w1=s.wave_f1, w2=s.wave_f2) for s in sg]


def main():
    eff = effective(); D = load_asset("WIN", "M5"); rows, extra = [], []
    for d in sorted(eff.date.unique()):
        fb, v3 = day_v3(d, D)
        E = eff[eff.date == d].sort_values("f2_time"); used = set()
        print(f"\n==== {d}  (você: {(E.verdict=='VALIDA').sum()} válidas, {(E.verdict=='FALSA').sum()} falsas · v3: {len(v3)} sinais)")
        for r in E.itertuples():
            c = [(abs(m(v["f2"]) - m(r.f2_time)), k) for k, v in enumerate(v3) if k not in used and v["dir"] == r.dir
                 and abs(m(v["f2"]) - m(r.f2_time)) <= 10]
            h = None
            if c:
                k = min(c)[1]; used.add(k); h = v3[k]
            ok = (r.verdict == "VALIDA") == bool(h)
            print(f"  {'OK ' if ok else 'XX '} você {r.verdict:6s} {r.tipo:10s} {'C' if r.dir > 0 else 'V'} F1 {r.f1_time} F2 {r.f2_time} "
                  f"{r.f2_price:g} {r.wall_type} dist {r.wall_dist:g} | v3: {('F1 ' + h['f1'] + ' F2 ' + h['f2'] + ' ' + h['kind']) if h else '-'}")
            rows.append(dict(date=d, verdict=r.verdict, tipo=r.tipo, dir=r.dir, v3=bool(h), wall_dist=r.wall_dist,
                             f1=r.f1_time, f2=r.f2_time, f2_price=r.f2_price, origin=r.origin,
                             v3_f1=h["f1"] if h else "", v3_kind=h["kind"] if h else ""))
        for k, v in enumerate(v3):
            if k not in used:
                print(f"  ??  v3 sem marcação sua: {'C' if v['dir'] > 0 else 'V'} F1 {v['f1']} F2 {v['f2']} {v['px']:g} {v['kind']}")
                extra.append(dict(date=d, **v))
    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(ROOT, "research", "div_v3", "results", "labels_vs_v3.csv"), index=False)
    pd.DataFrame(extra).to_csv(os.path.join(ROOT, "research", "div_v3", "results", "v3_sem_marcacao.csv"), index=False)
    print("\nRESUMO"); print(pd.crosstab(R.verdict, R.v3, margins=True))
    print(pd.crosstab([R.verdict, R.tipo], R.v3)); print("v3 sem marcação:", len(extra))


if __name__ == "__main__":
    main()
