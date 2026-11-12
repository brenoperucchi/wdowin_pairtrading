# -*- coding: utf-8 -*-
"""
Avalia o motor v2.1 contra os rotulos (labels.csv) e, quando possivel, contra
os detectores antigos A (causal), B (visual) e o gerador da rotulagem.
Uso (na raiz do projeto):
  C:\\Python313\\python.exe research/div_master/engine_v2_1/evaluate.py
Nao grava em labels.csv nem em core/.
"""
from __future__ import annotations

import csv, json, os, sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LABELER_DATA = ROOT / "research" / "div_master" / "labeler" / "data"
LABELS = ROOT / "research" / "div_master" / "labels" / "labels.csv"
OUT_DET = HERE / "detections.json"
OUT_MET = HERE / "metrics.json"

sys.path.insert(0, str(HERE))
from detect import detect, DEFAULTS  # noqa: E402

TRAIN = ["2026-11-11", "2026-02-09", "2026-06-02", "2026-01-14", "2026-03-20", "2026-06-23"]
HOLD = ["2026-02-20", "2026-04-07", "2026-07-13"]
DIV_TIPOS = {"REJEICAO", "ABSORCAO"}


def load_labels():
    rows = list(csv.DictReader(open(LABELS, encoding="utf-8", newline="")))
    undone = {r["undo_of"] for r in rows if r["action"] == "UNDO"}
    pre, manual = {}, defaultdict(list)
    for r in rows:
        if r["action"] not in ("LABEL", "ADD") or r["action_id"] in undone:
            continue
        if r["action"] == "LABEL":
            pre[r["cand_id"]] = r
        else:
            manual[r["date"]].append(r)
    return pre, manual, rows


def time_idx(bars, t):
    if not t:
        return None
    for i, b in enumerate(bars):
        if b["time"] == t:
            return i
    return None


def ground_truth(days, pre, manual):
    """Eventos validos de divergencia (rejeicao/absorcao), inclusive manuais."""
    gts = []
    for date, day in days.items():
        bars = day["bars"]
        cand = {c["id"]: c for c in day["candidates"]}
        items = []
        for c in day["candidates"]:
            r = pre.get(c["id"])
            if r:
                items.append(("pre", c["id"], r, c))
        for r in manual.get(date, []):
            items.append(("manual", r["cand_id"], r, None))
        for origin, cid, r, c in items:
            if r["verdict"] != "VALIDA" or (r.get("tipo") or "") not in DIV_TIPOS:
                continue
            side = int(r["dir"] or (c["dir"] if c else 0) or 0)
            f2t = r["f2_time"] or (c["f2_time"] if c else None)
            f1t = r["f1_time"] or (c["f1_time"] if c else None)
            f2 = time_idx(bars, f2t)
            f1 = time_idx(bars, f1t)
            gts.append(dict(
                date=date, cid=cid, origin=origin, tipo=r["tipo"], side=side,
                f1=f1, f2=f2, f1_time=f1t, f2_time=f2t,
            ))
    return gts


def falses(days, pre):
    out = []
    for date, day in days.items():
        bars = day["bars"]
        for c in day["candidates"]:
            r = pre.get(c["id"])
            if not r or r["verdict"] != "FALSA":
                continue
            f2 = time_idx(bars, r["f2_time"] or c["f2_time"])
            out.append(dict(date=date, cid=c["id"], side=int(r["dir"] or c["dir"]), f2=f2, kind=c["kind"]))
    return out


def match(dets, gts, tol=2):
    used_d, used_g, pairs = set(), set(), []
    cands = []
    for gi, g in enumerate(gts):
        if g.get("f2") is None:
            continue
        for di, d in enumerate(dets):
            if d["dir"] != g["side"]:
                continue
            dist = abs(d["f2_idx"] - g["f2"])
            if dist <= tol:
                cands.append((dist, gi, di))
    cands.sort()
    for dist, gi, di in cands:
        if gi in used_g or di in used_d:
            continue
        used_g.add(gi)
        used_d.add(di)
        pairs.append((gi, di, dist))
    return pairs, used_g, used_d


def eval_dets(dets_by_date, gts, dates=None, falses_list=None, tol=2):
    if dates is not None:
        dates = set(dates)
        gts = [g for g in gts if g["date"] in dates]
    else:
        dates = {g["date"] for g in gts}
    all_dets = []
    for d, dets in dets_by_date.items():
        if d not in dates:
            continue
        for x in dets:
            y = dict(x)
            y["date"] = d
            all_dets.append(y)
    TP = FP = FN = 0
    man_h = man_t = 0
    misses, fps, per = [], [], {}
    reviewed_fp = 0
    unreviewed_fp = 0
    for date in sorted(dates):
        gs = [g for g in gts if g["date"] == date]
        ds = [d for d in all_dets if d["date"] == date]
        pairs, ug, ud = match(ds, gs, tol)
        TP += len(pairs)
        FN += len(gs) - len(pairs)
        FP += len(ds) - len(pairs)
        for i, g in enumerate(gs):
            if g["origin"] == "manual":
                man_t += 1
                if i in ug:
                    man_h += 1
            if i not in ug:
                misses.append(g)
        for j, d in enumerate(ds):
            if j in ud:
                continue
            fps.append(d)
            hit_f = False
            if falses_list:
                hit_f = any(
                    f["date"] == d["date"] and f["side"] == d["dir"] and f["f2"] is not None
                    and abs(f["f2"] - d["f2_idx"]) <= tol
                    for f in falses_list
                )
            if hit_f:
                reviewed_fp += 1
            else:
                unreviewed_fp += 1
        rec_s = len(pairs) / len(gs) if gs else 0
        prec_s = len(pairs) / len(ds) if ds else 0
        per[date] = dict(gt=len(gs), det=len(ds), TP=len(pairs), FP=len(ds) - len(pairs),
                         FN=len(gs) - len(pairs), rec=rec_s, prec=prec_s)
    rec = TP / (TP + FN) if TP + FN else 0.0
    prec = TP / (TP + FP) if TP + FP else 0.0
    prec_rev = TP / (TP + reviewed_fp) if TP + reviewed_fp else 0.0
    f1 = (2 * rec * prec / (rec + prec)) if rec + prec else 0.0
    return dict(
        TP=TP, FP=FP, FN=FN, rec=rec, prec=prec, f1=f1, n_det=TP + FP, n_gt=TP + FN,
        manual_hit=man_h, manual_tot=man_t, prec_reviewed=prec_rev,
        reviewed_fp=reviewed_fp, unreviewed_fp=unreviewed_fp,
        misses=misses, fps=fps, per_session=per,
    )


def run_v2(days, params=None):
    out = {}
    for date, day in days.items():
        dets, _ = detect(day["bars"], day["wave"], day["walls"], params)
        out[date] = dets
    return out


def load_days():
    days = {}
    for p in sorted(LABELER_DATA.glob("2026-*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        days[d["date"]] = d
    return days


def run_old_detectors(labeled_dates):
    """Roda A causal e B nos pregoes historicos (jan-jul) via build_data. 11/11 fica de fora (sem .min)."""
    result = {"A": {}, "B": {}}
    try:
        sys.path.insert(0, str(ROOT))
        from research.div_master.labeler import build_data as bd
        from core import div_wall_signal as dws
        from research.div_wall.data import load_asset
    except Exception as e:
        print("aviso: nao deu para importar detectores antigos:", type(e).__name__, e)
        return result
    hist = [d for d in labeled_dates if d != "2026-11-11"]
    if not hist:
        return result
    data = load_asset("WIN", "M5")
    for date in hist:
        if date not in data:
            print("aviso: load_asset nao tem", date)
            continue
        bars, walls, nwe = data[date]
        bars = [b for b in bars if b["time"] <= getattr(bd, "T_END", "17:55")]
        n = len(bars)
        nwe = tuple(__import__("numpy").asarray(x[:n], dtype=float) for x in nwe)
        levels = [{"type": w["type"], "price": float(w["price"])} for w in walls if w.get("type") in ("Wall", "MidWall")]
        fb = dws.compute_flow([dict(b) for b in bars], "WIN")
        a = bd.det_A_causal(fb)
        b = bd.det_B(bars, levels)
        def to_dets(raw):
            dets = []
            for s in raw:
                f2 = s.get("f2")
                if f2 is None:
                    continue
                dets.append({
                    "dir": s["dir"], "f1_idx": s.get("f1"), "f2_idx": f2,
                    "sig_idx": s.get("sig", f2),
                    "f1_time": bars[s["f1"]]["time"] if s.get("f1") is not None else None,
                    "f2_time": bars[f2]["time"],
                })
            return dets
        result["A"][date] = to_dets(a)
        result["B"][date] = to_dets(b)
    return result


def labeler_dets(days):
    """Candidatos DIV do gerador da rotulagem (nao inclui BRK)."""
    out = {}
    for date, day in days.items():
        dets = []
        for c in day["candidates"]:
            if c.get("kind") == "BRK":
                continue
            dets.append({
                "dir": c["dir"], "f1_idx": c.get("f1_idx"), "f2_idx": c["f2_idx"],
                "sig_idx": c.get("sig_idx"), "f1_time": c.get("f1_time"), "f2_time": c["f2_time"],
            })
        out[date] = dets
    return out


def compact(ev):
    keys = ["TP", "FP", "FN", "rec", "prec", "f1", "prec_reviewed", "reviewed_fp",
            "unreviewed_fp", "manual_hit", "manual_tot", "n_gt", "n_det"]
    return {k: ev[k] for k in keys}


def main():
    days = load_days()
    pre, manual, raw = load_labels()
    gts = ground_truth(days, pre, manual)
    fal = falses(days, pre)
    labeled = sorted({r["date"] for r in raw})
    print("pregoes rotulados:", labeled)
    print("GT divergencias validas:", len(gts), "manuais:", sum(1 for g in gts if g["origin"] == "manual"))
    print("params v2.1:", DEFAULTS)

    v2_all = run_v2(days)
    # persist detections for every session in labeler/data (overlay)
    dump = {d: v2_all[d] for d in v2_all}
    OUT_DET.write_text(json.dumps(dump, ensure_ascii=False, indent=1), encoding="utf-8")
    print("escreveu", OUT_DET, "sessoes", len(dump))

    def report(name, dets, dates):
        ev = eval_dets(dets, gts, dates=dates, falses_list=fal)
        ev_c = compact(ev)
        print(f"\n=== {name} ===")
        print("  rec={rec:.3f} prec={prec:.3f} F1={f1:.3f} TP={TP} FP={FP} FN={FN} "
              "man={manual_hit}/{manual_tot} prec_revisada={prec_reviewed:.3f} "
              "(FP rotuladas falsas={reviewed_fp}, FP nao revisadas={unreviewed_fp})".format(**ev_c))
        for d in dates:
            s = ev["per_session"].get(d)
            if s:
                print(f"    {d} gt={s['gt']} det={s['det']} TP={s['TP']} FP={s['FP']} FN={s['FN']} rec={s['rec']:.2f} prec={s['prec']:.2f}")
        if ev["misses"] and name.startswith("v2"):
            print("  misses:")
            for g in ev["misses"]:
                print(f"    {g['date']} {g['cid']} {g['origin']} {g['tipo']} dir={g['side']} F1 {g['f1_time']} -> F2 {g['f2_time']}")
        return ev

    ev_tr = report("v2.1 TREINO", v2_all, TRAIN)
    ev_ho = report("v2.1 HOLD-OUT", v2_all, HOLD)
    ev_all = report("v2.1 TODOS os 9 pregoes", v2_all, labeled)

    print("\n=== v2.1 LOSO (parametros fixos, um pregao de cada vez) ===")
    recs, precs = [], []
    loso = {}
    for d in labeled:
        ev = eval_dets(v2_all, gts, dates=[d], falses_list=fal)
        recs.append(ev["rec"])
        precs.append(ev["prec"])
        loso[d] = compact(ev)
        print(f"  {d} rec={ev['rec']:.3f} prec={ev['prec']:.3f} TP={ev['TP']} FP={ev['FP']} FN={ev['FN']} man={ev['manual_hit']}/{ev['manual_tot']}")
    print(f"  media LOSO rec={sum(recs)/len(recs):.3f} prec={sum(precs)/len(precs):.3f}")

    ev_lab = report("gerador da rotulagem (candidatos DIV, 9 pregoes)", labeler_dets(days), labeled)

    old = run_old_detectors(labeled)
    ev_a = ev_b = None
    hist = [d for d in labeled if d != "2026-11-11"]
    if any(old["A"].values()):
        ev_a = report("detector A causal (jan-jul rotulados, sem 11/11)", old["A"], hist)
        ev_b = report("detector B visual (jan-jul rotulados, sem 11/11)", old["B"], hist)
        ev_v2_hist = report("v2.1 no mesmo recorte jan-jul (sem 11/11)", v2_all, hist)

    # 11/11 reference
    print("\n=== gabarito 11/11 (v2.1) ===")
    refs = [
        ("E1 compra 09:00-09:15 MidWall", 1, "09:15"),
        ("E3a venda 10:25-10:40 Wall 174913 (193 pts)", -1, "10:40"),
        ("E3b venda 11:10-11:25 Wall 174913", -1, "11:25"),
        ("E4 venda 12:00-12:20 Wall 174913", -1, "12:20"),
    ]
    dets = v2_all.get("2026-11-11", [])
    for d in dets:
        print(f"  dir={d['dir']:+d} F1 {d['f1_time']} -> F2 {d['f2_time']} sig {d['sig_time']} "
              f"{'day_ext' if d['day_ext'] else ''} {'wall' if d['near_wall'] else ''}")

    def tmin(t):
        return int(t[:2]) * 60 + int(t[3:])

    for name, side, f2 in refs:
        hit = any(d["dir"] == side and abs(tmin(d["f2_time"]) - tmin(f2)) <= 10 for d in dets)
        print(f"  {'OK' if hit else 'PERDIDO'} {name}")

    met = {
        "params": DEFAULTS,
        "train_dates": TRAIN,
        "hold_dates": HOLD,
        "n_gt_div": len(gts),
        "v21_train": compact(ev_tr),
        "v21_hold": compact(ev_ho),
        "v21_all": compact(ev_all),
        "v21_loso": loso,
        "v21_loso_mean_rec": sum(recs) / len(recs),
        "v21_loso_mean_prec": sum(precs) / len(precs),
        "labeler_div": compact(ev_lab),
        "A": compact(ev_a) if ev_a else None,
        "B": compact(ev_b) if ev_b else None,
        "v21_hist": compact(ev_v2_hist) if ev_a else None,
        "misses_all": ev_all["misses"],
    }
    OUT_MET.write_text(json.dumps(met, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\nescreveu", OUT_MET)


if __name__ == "__main__":
    main()
