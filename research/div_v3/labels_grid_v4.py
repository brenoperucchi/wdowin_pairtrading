"""Variantes do v4 contra as marcações do rotulador (WIN). Uso: python research/div_v3/labels_grid_v4.py <micro.json de 11/11>"""
import itertools, json, os, sys
import numpy as np, pandas as pd
from datetime import datetime, timezone
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, ROOT)
from research.div_wall.data import load_asset
from core.div_wall_signal import compute_flow, detect_divergences_v3, detect_divergences_v4, DivParamsV2
from core.profit_mt5_flow_engine import load_daily_magic_walls
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from labels_vs_v3 import effective, m

LIVE11 = sys.argv[1] if len(sys.argv) > 1 else None


def days(eff):
    D = load_asset("WIN", "M5"); out = {}
    for d in sorted(eff.date.unique()):
        if d == "2026-11-11":
            if not LIVE11:
                continue
            bars = [dict(x) for x in json.load(open(LIVE11, encoding="utf-8-sig"))["WIN"]["m5_cvd_series"]]
            for x in bars:
                x["time"] = datetime.fromtimestamp(int(x["time"]), timezone.utc).strftime("%H:%M")
            walls = load_daily_magic_walls("WIN", d); z = np.zeros(len(bars)); nwe = (z, z, z)
        else:
            bars, walls, nwe = D[d]
        out[d] = (compute_flow(bars, "WIN"), walls, nwe)
    return out


def score(eff, DD, fn):
    tv = fv = extra = tot = 0; by = {}
    for d, (fb, walls, nwe) in DD.items():
        sg = fn(fb, walls, nwe); tot += len(sg)
        v = [(s.direction, fb[s.pivot_idx]["time"], s.wall_type) for s in sg]
        used = set()
        for r in eff[eff.date == d].sort_values("f2_time").itertuples():
            c = [(abs(m(t) - m(r.f2_time)), k) for k, (dr, t, _) in enumerate(v) if k not in used and dr == r.dir and abs(m(t) - m(r.f2_time)) <= 10]
            hit = bool(c)
            if hit:
                used.add(min(c)[1])
            if r.verdict == "VALIDA":
                tv += hit; by[r.tipo] = by.get(r.tipo, 0) + hit
            else:
                fv += hit
        extra += len(v) - len(used)
    nv, nf = (eff.verdict == "VALIDA").sum(), (eff.verdict == "FALSA").sum()
    return dict(validas=f"{tv}/{nv}", falsas=f"{fv}/{nf}", recall=round(tv / nv, 2), fp=round(fv / nf, 2),
                saldo=tv - fv, extras=extra, sinais_dia=round(tot / len(DD), 1),
                rej=by.get("REJEICAO", 0), abs_=by.get("ABSORCAO", 0), rom=by.get("ROMPIMENTO", 0))


def main():
    eff = effective(); eff = eff[eff.date.isin(["2026-11-11"] if False else eff.date.unique())]
    DD = days(eff); eff = eff[eff.date.isin(DD)]
    rows = []
    p3 = DivParamsV2.default("WIN", nwe_filter="none")
    rows.append(dict(variante="v3", **score(eff, DD, lambda fb, w, n: detect_divergences_v3(fb, w, n, p3))))
    for rom, zone, L, fu, rmax in itertools.product((False, True), (100.0, 150.0, 200.0), (1, 2), (True, False), (400.0, 800.0)):
        if not rom and rmax == 800.0:
            continue
        p = DivParamsV2.default("WIN", nwe_filter="none", pivot_left=L)
        f = lambda fb, w, n, p=p, rom=rom, zone=zone, fu=fu, rmax=rmax: detect_divergences_v4(
            fb, w, n, p, rompimento=rom, zone=zone, furou=fu, rom_max=rmax)
        rows.append(dict(variante=f"rompimento={'sim' if rom else 'não'} zona={zone:g} pivô_esq={L} furou={'sim' if fu else 'não'}"
                         + (f" rom_max={rmax:g}" if rom else ""), **score(eff, DD, f)))
    R = pd.DataFrame(rows).sort_values(["saldo", "recall"], ascending=False)
    R.to_csv(os.path.join(ROOT, "research", "div_v3", "results", "labels_grid_v4.csv"), index=False)
    print(R.to_string(index=False))


if __name__ == "__main__":
    main()
