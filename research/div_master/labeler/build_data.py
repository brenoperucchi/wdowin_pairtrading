# -*- coding: utf-8 -*-
"""
Gera os JSON dos pregoes para a ferramenta de rotulagem (Fase 0 do PLANO_MESTRE).
Somente leitura dos dados; grava apenas em research/div_master/labeler/data/.

Fontes:
  - jan-jul: dataset congelado div_wall_v1 (.min do Profit + Walls do historico B3, NWE 100/8/3 aquecida), verificado por hash.
  - 11/11/2026 (gabarito): GET http://localhost:8080/api/compass/etapa2 (motor ao vivo) + mt5/Files/jumba_gex_win_daily.csv.
Onda Smart Money = core.div_wall_signal.compute_flow (mesma formula do painel 5176).

Candidatos = uniao de detectores com recall alto, cada sinal marcado na barra em que ele JA seria conhecido
(fechamento da barra de confirmacao; nada le barra posterior a essa).
Regras de apresentacao (feedback 11/11): sem leque (cada pivo e F1 de no maximo um candidato;
o swing novo casa com o anterior do mesmo lado, ou com o anterior mais relevante);
rejeicao/absorcao a <= 150 pts de Wall/MidWall OU nova maxima (venda) / nova minima (compra) do pregao (causal);
rompimentos a parte, tambem deduplicados; contexto (wall/midwall/day_high/day_low) so em candidate_sources.json;
sinais do mesmo lado a poucas barras viram um so (fica o mais forte); teto de 11 por pregao.
Pregoes ja rotulados nao sao regenerados (ids estáveis).
Uso: C:\\Python313\\python.exe research/div_master/labeler/build_data.py
"""
import ast, csv, json, os, random, shutil, sys, urllib.request
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ROOT)
from core import div_wall_signal as dws          # noqa: E402
from research.div_wall.data import load_asset    # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "data")
BACKUP = os.path.join(os.path.dirname(__file__), "data_v2_backup")
SOURCES_BACKUP = os.path.join(os.path.dirname(__file__), "candidate_sources_v2_backup.json")
LABELS = os.path.join(os.path.dirname(__file__), "..", "labels", "labels.csv")
SOURCES = os.path.join(os.path.dirname(__file__), "candidate_sources.json")
SEED = 20261111
N_DAYS = 15
ASSET = "WIN"
ZONE = 150.0          # "na Wall" (decisao do usuario)
TICK = 5.0
LEVEL_TYPES = ("Wall", "MidWall")
T_END = "17:55"
MAX_CAND = 11
DEDUP_BARS = 3
PIVOT_LOOKBACK = 30


# ----------------------------------------------------------------------------- detectores
def load_visual_detector():
    src = os.path.join(ROOT, "research", "flow_window_asg", "inject_unified_div_opt2.py")
    tree = ast.parse(open(src, encoding="utf-8").read())
    keep = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
            ("compute_causal_3motor_bars", "detect_visual_swing_divergences")]
    ns = {}
    exec(compile(ast.Module(body=keep, type_ignores=[]), src, "exec"), ns)
    return ns["compute_causal_3motor_bars"], ns["detect_visual_swing_divergences"]


C3M, VIS = load_visual_detector()


def det_A_causal(fb):
    """Detector do motor (gex_live_dealer_engine L1795-1915) SEM barra do futuro: o fundo j precisa da barra j+1
    para ser confirmado, entao o sinal so nasce no fechamento de j+1. Sem repintura (todas as divergencias ficam)."""
    out, n = [], len(fb)
    for i in range(5, n):
        j = i - 1
        b = fb[j]
        l, h, c, o = b["low"], b["high"], b["close"], b["open"]
        rng = max(h - l, TICK)
        w = b["wave"]
        is_low = l <= min(fb[j - 1]["low"], fb[j - 2]["low"]) and l <= fb[i]["low"] + TICK
        if is_low and ((c - l) / rng >= 0.40 or c >= o) and (b["force"] > 0 or b["wyckoff_abs"] > 0 or w > 0):
            for k in range(j - 3, max(1, j - 16), -1):
                if fb[k]["low"] <= fb[k - 1]["low"] and fb[k]["low"] <= fb[k + 1]["low"]:
                    sv_j = b["sell_vol"] + fb[j - 1]["sell_vol"]
                    sv_k = fb[k]["sell_vol"] + fb[k - 1]["sell_vol"]
                    if (fb[k]["low"] - 360) <= l <= (fb[k]["low"] + 40) and w > fb[k]["wave"] + 1800 and \
                            (fb[k]["wave"] < 0 or b["wyckoff_abs"] > 0 or sv_j < 0.88 * sv_k):
                        out.append(dict(dir=1, sig=i, f1=k, f2=j, src="A"))
                    break
        is_high = h >= max(fb[j - 1]["high"], fb[j - 2]["high"]) and h >= fb[i]["high"] - TICK
        if is_high and ((h - c) / rng >= 0.40 or c <= o) and (b["force"] < 0 or b["wyckoff_abs"] < 0 or w < 0):
            for k in range(j - 3, max(1, j - 16), -1):
                if fb[k]["high"] >= fb[k - 1]["high"] and fb[k]["high"] >= fb[k + 1]["high"]:
                    bv_j = b["buy_vol"] + fb[j - 1]["buy_vol"]
                    bv_k = fb[k]["buy_vol"] + fb[k - 1]["buy_vol"]
                    if (fb[k]["high"] - 40) <= h <= (fb[k]["high"] + 360) and w < fb[k]["wave"] - 1800 and \
                            (fb[k]["wave"] > 0 or b["wyckoff_abs"] < 0 or bv_j < 0.88 * bv_k):
                        out.append(dict(dir=-1, sig=i, f1=k, f2=j, src="A"))
                    break
    return out


def det_B(bars, levels):
    b3 = C3M([dict(b) for b in bars], True)
    out = []
    for s in VIS(b3, levels, True):
        i = s["sig_idx"]
        key = "low" if s["dir"] == 1 else "high"
        f2 = i if bars[i][key] == s["pivot_px"] else i - 1
        out.append(dict(dir=s["dir"], sig=i, f1=None, f2=f2, src="B"))
    return out


def det_v1(fb, levels, nwe):
    sp = dws.SignalParams.default(ASSET, wave_k=0.25, wall_radius=ZONE, max_dist=40, max_ext=600.0,
                                  entry_start="09:00", entry_end=T_END, cooldown=3)
    return [dict(dir=s.direction, sig=s.idx, f1=s.f1_idx, f2=s.pivot_idx, src="v1")
            for s in dws.detect_signals(fb, levels, nwe, sp)]


def det_v2(fb, levels, nwe):
    p = dws.DivParamsV2.default(ASSET, wave_k=0.5, wall_radius=ZONE, nwe_filter="none", confirm="PIVO")
    return [dict(dir=s.direction, sig=s.idx, f1=s.f1_idx, f2=s.pivot_idx, src="v2")
            for s in dws.detect_divergences_v2(fb, levels, nwe, p)]


def det_D1(fb, levels):
    """D1 frouxo: pivo L1/R1 (a barra de abertura pode ser F1), F1 = qualquer pivo anterior em ate 30 barras,
    F2 <= F1 + 60 (compra), onda no PROPRIO pivo melhor que no F1 por > 0,15 x mediana causal |onda|,
    F2 a <= 150 de Wall/MidWall ou nova extrema do pregao (maxima na venda / minima na compra, causal)."""
    out, n = [], len(fb)
    absw = []
    piv = {1: [], -1: []}
    lv = [w["price"] for w in levels]
    for i in range(n):
        absw.append(abs(fb[i]["wave"]))
        j = i - 1
        if j < 0:
            continue
        thr = 0.15 * float(np.median(absw))
        for d in (1, -1):
            key = "low" if d == 1 else "high"
            pj = fb[j][key]
            left_ok = (j == 0) or ((pj <= fb[j - 1][key]) if d == 1 else (pj >= fb[j - 1][key]))
            right_ok = (pj < fb[i][key]) if d == 1 else (pj > fb[i][key])
            if not (left_ok and right_ok):
                continue
            wj = fb[j]["wave"]
            near = min((abs(pj - x) for x in lv), default=1e9) <= ZONE
            if near or is_new_session_extreme(fb, j, d):
                for (k, pk, wk) in piv[d][::-1]:
                    if j - k > 30:
                        break
                    if j - k < 2:
                        continue
                    price_ok = (pj <= pk + 60) if d == 1 else (pj >= pk - 60)
                    wave_ok = ((wj - wk) if d == 1 else (wk - wj)) > thr
                    if price_ok and wave_ok:
                        out.append(dict(dir=d, sig=i, f1=k, f2=j, src="D1"))
                        break
            piv[d].append((j, pj, wj))
    return out


def det_BRK(fb, levels):
    """Rompimento com aceitacao apos reteste (decisao do usuario: entrada 10:10 em 11/11):
    fechamento alem do nivel em b, reteste em r (b < r <= i) com minima a <= 60 do nivel (compra),
    fechamento de aceitacao em i alem do nivel + 1 tick, i - b <= 8, onda(i) > onda(b) (fluxo a favor)."""
    out, n = [], len(fb)
    used = set()
    for i in range(2, n):
        for w in levels:
            W = w["price"]
            for d in (1, -1):
                if (W, d) in used:
                    continue
                ci = fb[i]["close"]
                if not ((ci > W + TICK) if d == 1 else (ci < W - TICK)):
                    continue
                for b in range(max(1, i - 8), i - 1):
                    cb, cprev = fb[b]["close"], fb[b - 1]["close"]
                    first = (cb > W and cprev <= W) if d == 1 else (cb < W and cprev >= W)
                    if not first:
                        continue
                    ret = any((fb[r]["low"] <= W + 60) if d == 1 else (fb[r]["high"] >= W - 60) for r in range(b + 1, i + 1))
                    flow = (fb[i]["wave"] > fb[b]["wave"]) if d == 1 else (fb[i]["wave"] < fb[b]["wave"])
                    if ret and flow:
                        out.append(dict(dir=d, sig=i, f1=b, f2=i, src="BRK", level=W, level_type=w["type"]))
                        used.add((W, d))
                        break
    return out


# ----------------------------------------------------------------------------- uniao / apresentacao
def is_new_session_extreme(fb, idx, direction):
    """Compra = nova minima do pregao; venda = nova maxima. Causal: so barras 0..idx (sem olhar para a frente).
    Comparacao estrita; a primeira barra conta como extrema."""
    if idx < 0 or idx >= len(fb):
        return False
    if direction == 1:
        px = fb[idx]["low"]
        return idx == 0 or px < min(fb[i]["low"] for i in range(idx))
    px = fb[idx]["high"]
    return idx == 0 or px > max(fb[i]["high"] for i in range(idx))


def _contexts(d, p2_idx, p2_px, near, fb):
    """Rotulos de contexto (vao so para candidate_sources.json). Pode haver mais de um."""
    ctx = []
    if near is not None and abs(p2_px - near["price"]) <= ZONE:
        typ = (near.get("type") or "").lower()
        ctx.append("midwall" if typ == "midwall" else "wall")
    if is_new_session_extreme(fb, p2_idx, d):
        ctx.append("day_low" if d == 1 else "day_high")
    return ctx


def list_pivots(fb):
    """Pivos L1/R1 confirmados: a barra j so e pivo no fechamento de j+1."""
    n = len(fb)
    piv = {1: [], -1: []}
    for i in range(1, n):
        j = i - 1
        for d in (1, -1):
            key = "low" if d == 1 else "high"
            pj = fb[j][key]
            left_ok = (j == 0) or ((pj <= fb[j - 1][key]) if d == 1 else (pj >= fb[j - 1][key]))
            right_ok = (pj < fb[i][key]) if d == 1 else (pj > fb[i][key])
            if left_ok and right_ok:
                piv[d].append(dict(idx=j, px=pj, wave=fb[j]["wave"], sig=i))
    return piv


def _price_ok(d, p1, p2):
    return (p2["px"] <= p1["px"] + 60) if d == 1 else (p2["px"] >= p1["px"] - 60)


def _wave_delta(d, p1, p2):
    return (p2["wave"] - p1["wave"]) if d == 1 else (p1["wave"] - p2["wave"])


def _score(g, fb, med):
    """Forca para desempate e teto: acordo entre fontes + divergencia de onda + proximidade da Wall."""
    n_src = len(g["srcs"])
    f1, f2, d = g["f1"], g["f2"], g["dir"]
    if f1 is None or f2 is None:
        wd = 0.0
    else:
        wd = (fb[f2]["wave"] - fb[f1]["wave"]) * d
    prox = max(0.0, ZONE - abs(g["wall_dist"] if g.get("wall_dist") is not None else 1e9))
    base = 3.0 if g["kind"] == "BRK" else 0.0
    day_bonus = 1.0 if any(x in ("day_high", "day_low") for x in (g.get("context") or [])) else 0.0
    return base + n_src * 2.0 + wd / max(med, 1.0) + prox / ZONE + day_bonus


def _support_map(raw_div, piv):
    """Quais pivos F2 foram apontados por algum detector (casa por f2, sig ou vizinhanca de 2 barras)."""
    supported = {1: {}, -1: {}}
    for s in raw_div:
        d = s["dir"]
        f2 = s.get("f2")
        best = None
        for p in piv[d]:
            if f2 is not None and p["idx"] == f2:
                best = p
                break
        if best is None:
            for p in piv[d]:
                if p["sig"] == s["sig"] or (f2 is not None and abs(p["idx"] - f2) <= 1):
                    best = p
                    break
        if best is None:
            near = [p for p in piv[d] if p["idx"] <= s["sig"] and s["sig"] - p["sig"] <= 2]
            if near:
                best = near[-1]
        if best is None:
            continue
        rec = supported[d].setdefault(best["idx"], {"pivot": best, "srcs": set()})
        rec["srcs"].add(s["src"])
    return supported


def _pick_f1(d, plist, i, used_f1, thr):
    """Casa o swing i com o imediatamente anterior do mesmo lado; se nao servir, o mais relevante livre."""
    p2 = plist[i]
    if i > 0:
        p1 = plist[i - 1]
        if (p2["idx"] - p1["idx"] >= 2 and p1["idx"] not in used_f1
                and _price_ok(d, p1, p2) and _wave_delta(d, p1, p2) > thr):
            return p1
    best, best_sc = None, None
    for p1 in plist[:i]:
        gap = p2["idx"] - p1["idx"]
        if gap > PIVOT_LOOKBACK or gap < 2 or p1["idx"] in used_f1:
            continue
        if not _price_ok(d, p1, p2):
            continue
        wd = _wave_delta(d, p1, p2)
        if wd <= thr:
            continue
        sc = (wd, -gap)
        if best_sc is None or sc > best_sc:
            best, best_sc = p1, sc
    return best


def union(sigs, fb, levels):
    """Reempacota os sinais: sem leque, zona 150 ou extrema do dia nas DIV, dedup por barras proximas, teto 11."""
    raw_div = [s for s in sigs if s["src"] != "BRK"]
    raw_brk = [s for s in sigs if s["src"] == "BRK"]
    piv = list_pivots(fb)
    absw = [abs(b["wave"]) for b in fb]
    supported = _support_map(raw_div, piv)
    groups = []
    used_f1 = {1: set(), -1: set()}

    for d in (1, -1):
        plist = piv[d]
        for i, p2 in enumerate(plist):
            if p2["idx"] not in supported[d]:
                continue
            near = min(levels, key=lambda w: abs(w["price"] - p2["px"])) if levels else None
            ctx = _contexts(d, p2["idx"], p2["px"], near, fb)
            if not ctx:
                continue
            thr = 0.15 * float(np.median(absw[:p2["sig"] + 1] or [1.0]))
            f1 = _pick_f1(d, plist, i, used_f1[d], thr)
            if f1 is None:
                continue
            used_f1[d].add(f1["idx"])
            groups.append(dict(
                dir=d, sig=p2["sig"], last=p2["sig"], f1=f1["idx"], f2=p2["idx"],
                srcs=set(supported[d][p2["idx"]]["srcs"]), kind="DIV",
                level=near["price"] if near else None, level_type=near["type"] if near else None,
                wall_dist=(p2["px"] - near["price"]) if near else None,
                context=ctx,
            ))

    brk_groups = []
    for s in sorted(raw_brk, key=lambda s: (s["dir"], s["sig"])):
        dist = None
        if s.get("level") is not None:
            px = fb[s["f2"]]["close"]
            dist = px - s["level"]
        g = brk_groups[-1] if brk_groups else None
        if g and g["dir"] == s["dir"] and s["sig"] - g["last"] <= DEDUP_BARS:
            g["srcs"].add(s["src"])
            g["last"] = s["sig"]
        else:
            typ = (s.get("level_type") or "").lower()
            brk_ctx = ["midwall" if typ == "midwall" else "wall"] if s.get("level") is not None else []
            brk_groups.append(dict(
                dir=s["dir"], sig=s["sig"], last=s["sig"], f1=s["f1"], f2=s["f2"],
                srcs={s["src"]}, kind="BRK", level=s.get("level"),
                level_type=s.get("level_type"), wall_dist=dist, context=brk_ctx,
            ))
    groups += brk_groups

    med = float(np.median(absw) or 1.0)
    groups.sort(key=lambda g: (g["kind"], g["dir"], g["sig"]))
    merged = []
    for g in groups:
        prev = merged[-1] if merged else None
        if prev and prev["kind"] == g["kind"] and prev["dir"] == g["dir"] and g["sig"] - prev["last"] <= DEDUP_BARS:
            if _score(g, fb, med) > _score(prev, fb, med):
                g["srcs"] |= prev["srcs"]
                g["context"] = sorted(set((g.get("context") or []) + (prev.get("context") or [])))
                merged[-1] = g
            else:
                prev["srcs"] |= g["srcs"]
                prev["context"] = sorted(set((prev.get("context") or []) + (g.get("context") or [])))
                prev["last"] = max(prev["last"], g["sig"])
        else:
            merged.append(g)

    if len(merged) > MAX_CAND:
        ranked = sorted(merged, key=lambda g: _score(g, fb, med), reverse=True)
        keep = {id(g) for g in ranked[:MAX_CAND]}
        merged = [g for g in merged if id(g) in keep]
    merged.sort(key=lambda g: g["sig"])
    return merged


# ----------------------------------------------------------------------------- montagem
def build_day(date, bars, walls, nwe):
    bars = [b for b in bars if b["time"] <= T_END]
    n = len(bars)
    nwe = tuple(np.asarray(x[:n], dtype=float) for x in nwe)
    levels = [{"type": w["type"], "price": float(w["price"])} for w in walls if w.get("type") in LEVEL_TYPES]
    fb = dws.compute_flow([dict(b) for b in bars], ASSET)
    sigs = det_A_causal(fb) + det_B(bars, levels) + det_v1(fb, levels, nwe) + det_v2(fb, levels, nwe) + \
        det_D1(fb, levels) + det_BRK(fb, levels)
    cands, sources = [], {}
    for g_i, g in enumerate(union(sigs, fb, levels)):
        cid = f"{date}_{g_i + 1:02d}"
        d = g["dir"]
        f2 = g["f2"]
        f1 = g["f1"]
        key = "low" if d == 1 else "high"
        px2 = bars[f2]["close"] if g["kind"] == "BRK" else bars[f2][key]
        if g["kind"] == "BRK" and g.get("level") is not None:
            near = {"price": g["level"], "type": g.get("level_type") or "Wall"}
        else:
            near = min(levels, key=lambda w: abs(w["price"] - px2)) if levels else None
        cands.append({
            "id": cid, "dir": d, "kind": g["kind"], "sig_idx": g["sig"], "sig_time": bars[g["sig"]]["time"],
            "f1_idx": f1, "f1_time": bars[f1]["time"] if f1 is not None else None,
            "f1_price": (bars[f1]["close"] if g["kind"] == "BRK" else bars[f1][key]) if f1 is not None else None,
            "f2_idx": f2, "f2_time": bars[f2]["time"], "f2_price": px2,
            "wall_price": near["price"] if near else None, "wall_type": near["type"] if near else None,
            "wall_dist": round(px2 - near["price"], 1) if near else None,
        })
        sources[cid] = {"srcs": sorted(g["srcs"]), "context": list(g.get("context") or [])}
    lo = min(b["low"] for b in bars); hi = max(b["high"] for b in bars)
    vis_levels = [w for w in levels if lo - 600 <= w["price"] <= hi + 600]
    return {
        "date": date, "asset": ASSET,
        "bars": [{k: b[k] for k in ("time", "open", "high", "low", "close")} for b in bars],
        "wave": [float(f["wave"]) for f in fb],
        "nwe": {"c": [round(float(x), 1) for x in nwe[0]], "u": [round(float(x), 1) for x in nwe[1]],
                "l": [round(float(x), 1) for x in nwe[2]]},
        "walls": vis_levels, "zone": ZONE, "candidates": cands,
    }, sources


def pick_days(all_dates):
    rnd = random.Random(SEED)
    by_m = {}
    for d in all_dates:
        if "2026-01" <= d[:7] <= "2026-07":
            by_m.setdefault(d[:7], []).append(d)
    months = sorted(by_m)
    picks = []
    for m in months:
        picks += rnd.sample(by_m[m], 2)
    extra_m = rnd.choice(months)
    picks.append(rnd.choice([d for d in by_m[extra_m] if d not in picks]))
    picks = sorted(picks)[:N_DAYS] if len(picks) > N_DAYS else sorted(picks)
    order = picks[:]
    rnd.shuffle(order)
    return order


def today_live(date="2026-11-11"):
    raw = json.loads(urllib.request.urlopen("http://localhost:8080/api/compass/etapa2", timeout=90).read().decode("utf-8"))
    ser = [b for b in raw[ASSET]["m5_dealer_vs_flow_series"] if not b.get("is_prev_day") and b.get("is_bar_closed", True)]
    bars = [{k: float(b.get(k, 0.0)) if k != "time" else b["time"] for k in
             ("time", "open", "high", "low", "close", "buy_vol", "sell_vol", "avg_buy_lot", "avg_sell_lot",
              "inst_aggr_delta", "inst_pass_delta", "ret_delta_bar")} for b in ser]
    nwe = (np.array([b["nwe_line"] for b in ser]), np.array([b["nwe_upper"] for b in ser]), np.array([b["nwe_lower"] for b in ser]))
    walls = []
    with open(os.path.join(ROOT, "mt5", "Files", "jumba_gex_win_daily.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["session_date"] == date:
                walls.append({"type": r["type"], "price": float(r["price"])})
    return bars, walls, nwe


def labeled_dates():
    path = os.path.abspath(LABELS)
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8", newline="") as f:
        return {r["date"] for r in csv.DictReader(f) if r.get("date")}


def load_kept(date):
    path = os.path.join(OUT, f"{date}.json")
    return json.load(open(path, encoding="utf-8"))


def report_reference(day, tag):
    """Confere se os 4 eventos-gabarito de 11/11 ainda aparecem como candidatos."""
    evs = [
        ("E1 compra F1 09:00 ~173370 MidWall",
         lambda c: c["dir"] == 1 and c["kind"] == "DIV" and c.get("f1_time") == "09:00"
         and abs((c.get("f1_price") or 0) - 173370) <= 50),
        ("E2 rompimento Wall 173902 aceite 10:10",
         lambda c: c["kind"] == "BRK" and c["dir"] == 1 and c.get("sig_time") == "10:10"
         and c.get("wall_price") is not None and abs(c["wall_price"] - 173902.24) <= 5),
        ("E3 venda topo 10:45-11:40 Wall 174913",
         lambda c: c["dir"] == -1 and c["kind"] == "DIV"
         and (c.get("f2_time") or "") >= "10:45" and (c.get("f2_time") or "") <= "11:40"
         and c.get("wall_price") is not None and abs(c["wall_price"] - 174913.3) <= 5),
        ("E4 venda 12:00->12:20 Wall 174913",
         lambda c: c["dir"] == -1 and c["kind"] == "DIV"
         and (c.get("f2_time") or "") >= "12:00" and (c.get("f2_time") or "") <= "12:25"
         and ((c.get("f1_time") or "") >= "11:40" or (c.get("f1_time") or "") == "12:00")
         and c.get("wall_price") is not None and abs(c["wall_price"] - 174913.3) <= 5),
    ]
    print(f"--- gabarito 11/11 [{tag}] n_bars={len(day['bars'])} last={day['bars'][-1]['time'] if day['bars'] else '?'} n_cand={len(day['candidates'])} ---")
    for c in day["candidates"]:
        print(f"  {c['id']} {c['kind']:<3} dir={c['dir']:+d} F1 {c['f1_time']} -> F2 {c['f2_time']} sig {c['sig_time']} "
              f"{c['wall_type']} dist={c['wall_dist']}")
    for name, fn in evs:
        hits = [c["id"] for c in day["candidates"] if fn(c)]
        print(f"  {'OK' if hits else 'PERDIDO'} {name}: {hits or '-'}")


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.isdir(OUT) and not os.path.isdir(BACKUP):
        shutil.copytree(OUT, BACKUP)
        print(f"backup -> {BACKUP}")
    else:
        print(f"backup ja existe em {BACKUP} (nao sobrescrevi)")
    if os.path.exists(SOURCES) and not os.path.exists(SOURCES_BACKUP):
        shutil.copy2(SOURCES, SOURCES_BACKUP)
        print(f"backup fontes -> {SOURCES_BACKUP}")

    keep = labeled_dates()
    print("pregoes ja rotulados (nao regenerar):", sorted(keep) or "-")
    old_src = {}
    if os.path.exists(SOURCES):
        old_src = json.load(open(SOURCES, encoding="utf-8"))

    data = load_asset(ASSET, "M5")
    order = pick_days(sorted(data))
    days, all_src = [], {}
    for d in ["2026-11-11"] + order:
        kept_path = os.path.join(OUT, f"{d}.json")
        if d in keep and os.path.exists(kept_path):
            day = load_kept(d)
            src_note = day.get("source", "")
            for k, v in old_src.items():
                if k.startswith(d):
                    all_src[k] = v
            days.append({"date": d, "role": day.get("role", "gabarito" if d == "2026-11-11" else "IS"),
                         "n_bars": len(day["bars"]), "n_cand": len(day["candidates"])})
            print(f"{d} KEPT    barras {len(day['bars']):>3} candidatos {len(day['candidates']):>3}  ({src_note})")
            continue
        if d == "2026-11-11":
            bars, walls, nwe = today_live(d)
            src_note = "motor ao vivo (API 8080) + walls do dia"
        else:
            bars, walls, nwe = data[d]
            src_note = "div_wall_v1 (.min do Profit, hash verificado)"
        day, srcs = build_day(d, bars, walls, nwe)
        day["source"] = src_note
        day["role"] = "gabarito" if d == "2026-11-11" else "IS"
        json.dump(day, open(os.path.join(OUT, f"{d}.json"), "w", encoding="utf-8"), ensure_ascii=False)
        all_src.update(srcs)
        days.append({"date": d, "role": day["role"], "n_bars": len(day["bars"]), "n_cand": len(day["candidates"])})
        print(f"{d} {day['role']:<8} barras {len(day['bars']):>3} candidatos {len(day['candidates']):>3}")
        if d == "2026-11-11":
            report_reference(day, "gravado")

    json.dump({"seed": SEED, "asset": ASSET, "zone": ZONE, "days": days, "max_cand": MAX_CAND, "dedup_bars": DEDUP_BARS},
              open(os.path.join(OUT, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # origem dos candidatos fica FORA da pasta servida para a pagina (rotulagem cega)
    json.dump(all_src, open(SOURCES, "w", encoding="utf-8"), indent=1)
    over = [x for x in days if x["n_cand"] > MAX_CAND]
    if over:
        print("aviso: ainda acima de 11 (pregoes preservados com rotulos):",
              [(x["date"], x["n_cand"]) for x in over])


if __name__ == "__main__":
    main()
