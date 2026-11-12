# -*- coding: utf-8 -*-
"""
Frente 3 do PLANO_UNIFICACAO_ROMPIMENTO_LIMITE.md — entradas com ordens LIMITE / STOP ancoradas em níveis
(barra de gatilho, pivô F2, Wall, MidWall, NWE50 centro/banda, NWE30 banda, confluência Wall+NWE), com deslocamento
antes/depois do nível, validade e stop no preço executado ou atrás do nível. Também: o nível como filtro (3.3).

Estratégias:
  - ESP  : especialista ESP_DIV_V21_WIN (sinais e filtros de contexto congelados; saída sem alvo, 12 barras, BE 180→20;
           um trade por vez);
  - SNP  : Sniper 5176 (candidatos depois do filtro de divergência atual e das janelas de horário; meta diária
           aplicada depois da nova simulação; saída A: WIN 2 lotes NWE30+750 / WDO próxima Wall, SL 10, BE 3,5→1).
Execução tick a tick em M1. LIMITE executa só quando o preço passa 1 tick além (modo "toque" reportado à parte);
STOP executa no preço + 1 tick (gap: abertura). Cancelamento: novo extremo além do F2 (ESP) ou 15:55.
Uso: python research/div_master/frente3/ordens.py → frente3/results/
"""
import itertools, json, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ESPD = os.path.join(ROOT, "research", "div_master", "especialistas")
F1D = os.path.join(ROOT, "research", "div_master", "frente1")
sys.path[:0] = [ROOT, ESPD, F1D]
import numba as nb
import numpy as np, pandas as pd
import bt, modulo as M, robust as R
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
H1, IS_END = "2026-04-30", "2026-07-31"
LEVELS = ("BAR", "PIV", "WALL", "MID", "N50c", "N50b", "N30b", "CONF")
KINDS = ("LMT", "STP")
DELTA = {"WIN": (-30.0, -15.0, 0.0, 15.0, 30.0), "WDO": (-1.0, -0.5, 0.0, 0.5, 1.0)}   # negativo = antes do nível
VALID = (1, 3, 6)
STOPM = ("fill200", "nivel")
P = {"WIN": dict(tick=5.0, maxd=250.0, conf=50.0, sl=200.0, buf=60.0, slmin=80.0, slmax=300.0, cost=10.0, brl=0.2),
     "WDO": dict(tick=0.5, maxd=6.0, conf=1.5, sl=10.0, buf=2.0, slmin=2.5, slmax=10.5, cost=0.5, brl=10.0)}


# ───────────────────────── numba: execução da ordem e saída a partir do tick ─────────────────────────

@nb.njit(cache=True)
def _tk(px, isop, off, fb, o5, h5, l5, c5, k, j, d):
    if fb[k] == 0:
        return px[off[k] + j], isop[off[k] + j]
    if j == 0:
        return o5[k], True
    if j == 1:
        return (l5[k] if d == 1 else h5[k]), False
    if j == 2:
        return (h5[k] if d == 1 else l5[k]), False
    return c5[k], False


@nb.njit(cache=True)
def fill(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, oprice, e, nbars, d, kind, tick, touch, cancel_px, t_end):
    """oprice[k] = preço da ordem durante a barra k (NaN = sem ordem). kind 0 = LIMITE, 1 = STOP.
    Retorna (barra, tick, preço) ou (-1, -1, 0)."""
    n5 = len(o5)
    for k in range(e, min(e + nbars, n5)):
        if tm5[k] > t_end:
            return -1, -1, 0.0
        op_ = oprice[k]
        if op_ != op_:
            continue
        nt = nn[k] if fb[k] == 0 else 4
        for j in range(nt):
            p, isopen = _tk(px, isop, off, fb, o5, h5, l5, c5, k, j, d)
            if cancel_px == cancel_px and (p - cancel_px) * d < 0:
                return -1, -1, 0.0
            if kind == 0:
                if isopen and (op_ - p) * d >= 0:
                    return k, j, p
                thr = op_ - d * (0.0 if touch else tick)
                if (thr - p) * d >= 0:
                    return k, j, op_
            else:
                if isopen and (p - op_) * d >= 0:
                    return k, j, p + d * tick
                if (p - op_) * d >= 0:
                    return k, j, op_ + d * tick
    return -1, -1, 0.0


@nb.njit(cache=True)
def sim2(px, isop, off, nn, fb, o5, h5, l5, c5, tm5, band, e, j0, ep, d, sl, tp_fix, use_band, front, tp_lo, tp_hi,
         be_trig, be_lock, tmax, tick):
    """bt.sim começando no tick j0+1 da barra e (a entrada aconteceu no tick j0)."""
    n5 = len(o5)
    stop = ep - d * sl
    mfe = 0.0
    for k in range(e, n5):
        if k > e:
            if tm5[k] >= 1045 or k - e > tmax:
                return (o5[k] - ep) * d, tm5[k]
            if be_trig > 0 and mfe >= be_trig:
                cand = ep + d * be_lock
                if (o5[k] - cand) * d > 0 and (cand - stop) * d > 0:
                    stop = cand
        if use_band:
            raw = band[k] - d * front
            lo = ep + d * tp_lo
            hi = ep + d * tp_hi
            tp = min(max(raw, lo), hi) if d == 1 else max(min(raw, lo), hi)
            tp = np.round(tp / tick) * tick
        else:
            tp = tp_fix
        nt = nn[k] if fb[k] == 0 else 4
        for j in range((j0 + 1) if k == e else 0, nt):
            p, op = _tk(px, isop, off, fb, o5, h5, l5, c5, k, j, d)
            if (p - stop) * d <= 0:
                return ((p if op else stop - d * tick) - ep) * d, tm5[k]
            if (p - tp) * d >= 0:
                return ((p if op else tp) - ep) * d, tm5[k]
            if (p - ep) * d > mfe:
                mfe = (p - ep) * d
    return (c5[n5 - 1] - ep) * d, tm5[n5 - 1]


def A_(D):
    return (D["px"], D["op"], D["off"], D["nn"], D["fb"], D["o5"], D["h5"], D["l5"], D["c5"], D["tm5"])


# ───────────────────────── níveis e preço da ordem ─────────────────────────

def level_series(asset, lvl, kind, D, e, d, sig, typed):
    """Série (por barra) do nível de referência L ativo para a ordem, ou None se não há nível elegível.
    sig: dict com ref (fechamento da barra de sinal), bar_hi, bar_lo, piv. typed: {'Wall': [...], 'MidWall': [...]}"""
    pp = P[asset]
    n5 = len(D["o5"])
    ref = sig["ref"]
    side_ok = (lambda L: (L <= ref) if d == 1 else (L >= ref)) if kind == "LMT" else \
        (lambda L: (L >= ref) if d == 1 else (L <= ref))
    near = lambda L: abs(L - ref) <= pp["maxd"]
    const = lambda L: np.full(n5, L, float)
    if lvl == "BAR":
        L = (sig["bar_lo"] if d == 1 else sig["bar_hi"]) if kind == "LMT" else (sig["bar_hi"] if d == 1 else sig["bar_lo"])
        return const(L)
    if lvl == "PIV":
        L = sig["piv"]
        return const(L) if (side_ok(L) and near(L)) else None
    if lvl in ("WALL", "MID", "CONF"):
        pool = typed["Wall"] if lvl == "WALL" else typed["MidWall"] if lvl == "MID" else typed["Wall"] + typed["MidWall"]
        cand = [L for L in pool if side_ok(L) and near(L)]
        if lvl == "CONF":
            bands = [D["c50"][e], D["l50"][e], D["u50"][e], D["l30"][e], D["u30"][e]]
            cand = [L for L in cand if any(abs(L - b) <= pp["conf"] for b in bands)]
        if not cand:
            return None
        L = min(cand, key=lambda x: abs(x - ref))
        return const(L)
    # NWE: dinâmica, valor da barra anterior em cada barra (causal)
    if lvl == "N50c":
        s = D["c50"].astype(float)
    elif lvl == "N50b":
        s = (D["l50"] if (d == 1) == (kind == "LMT") else D["u50"]).astype(float)
    else:
        s = (D["l30"] if (d == 1) == (kind == "LMT") else D["u30"]).astype(float)
    L0 = s[e]
    return s.copy() if (side_ok(L0) and near(L0)) else None


def order_price(Ls, kind, d, delta):
    """LIMITE compra = L − δ ; STOP compra = L + δ (δ>0 = depois do nível; δ<0 = antes). Venda espelhada."""
    return Ls - d * delta if kind == "LMT" else Ls + d * delta


# ───────────────────────── sinais ─────────────────────────

def esp_signals(DS):
    T = bt.simulate("WIN", bt.signals("WIN", "v2.1"), DS, exits=())
    T = T[R.filt(T)].copy()
    data = load_asset("WIN", "M5")
    out = []
    for r in T.itertuples():
        D = DS[r.date]
        e = int(r.e)
        walls = data[r.date][1]
        out.append(dict(strat="ESP", asset="WIN", date=r.date, e=e, d=int(r.dir), ref=float(D["c5"][e - 1]),
                        bar_hi=float(D["h5"][e - 1]), bar_lo=float(D["l5"][e - 1]), piv=float(r.piv), cancel=float(r.piv),
                        typed={t: [float(w["price"]) for w in walls if w.get("type") == t] for t in ("Wall", "MidWall")},
                        levels=list(r.levels), mkt_ep=float(r.ep)))
    return out


def snp_signals(DSS):
    """Candidatos do Sniper atual (detector B do cache, janela 2, janelas de horário) antes da meta diária."""
    import motores as F1
    pool, vis = F1.sniper_pool()
    out = []
    for a in ("WIN", "WDO"):
        start, end, skip, _ = F1.SN[a]
        trs = F1.sniper_filter(pool[a], vis[a], ("tol", 2), a)  # já aplica a meta; refazemos sem ela abaixo
        F1.SN[a] = (start, end, skip, 1e12)
        trs = F1.sniper_filter(pool[a], vis[a], ("tol", 2), a)
        F1.SN[a] = (start, end, skip, 180.0 if a == "WIN" else 120.0)
        data = load_asset(a, "M5")
        for t in trs:
            D = DSS[a].get(t["date"])
            tm = bt.hm(t["time"])
            if D is None or tm not in D["pos"] or t["date"] not in data:
                continue
            e = D["pos"][tm]
            if e < 1:
                continue
            d = 1 if t["direction"] == "COMPRA" else -1
            walls = data[t["date"]][1]
            out.append(dict(strat="SNP", asset=a, date=t["date"], e=e, d=d, ref=float(D["c5"][e - 1]),
                            bar_hi=float(D["h5"][e - 1]), bar_lo=float(D["l5"][e - 1]),
                            piv=float(D["l5"][e - 1] if d == 1 else D["h5"][e - 1]), cancel=np.nan,
                            typed={tt: [float(w["price"]) for w in walls if w.get("type") == tt] for tt in ("Wall", "MidWall")},
                            levels=sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES),
                            mkt_ep=float(D["o5"][e]), orig_brl=float(t["brl_1c"]), orig_time=t["time"],
                            orig_exit=t.get("exit_time", "17:55")))
    return out


# ───────────────────────── saídas ─────────────────────────

def run_exit(s, D, k, j, ep, stopmode, L):
    a, pp = s["asset"], P[s["asset"]]
    d = s["d"]
    if stopmode == "fill200" or L is None:
        sl = pp["sl"]
    else:
        sl = float(np.clip(d * (ep - (L - d * pp["buf"])), pp["slmin"], pp["slmax"]))
    if s["strat"] == "ESP":
        pts, t = sim2(*A_(D), D["u30"], k, j, ep, d, sl, ep + d * 1e9, False, 0.0, 0.0, 0.0, 180.0, 20.0, 12, pp["tick"])
        return (pts - pp["cost"]) * pp["brl"] * 2.0, t      # 2 contratos, como no portfólio
    if a == "WIN":
        band = D["u30"] if d == 1 else D["l30"]
        sl2 = sl + 20.0 if stopmode == "fill200" else sl
        sl1 = 240.0 if stopmode == "fill200" else sl
        p1, t1 = sim2(*A_(D), band, k, j, ep, d, sl1, 0.0, True, 15.0, 260.0, 750.0, 180.0, 20.0, 24, pp["tick"])
        p2, t2 = sim2(*A_(D), band, k, j, ep, d, sl2, ep + d * 750.0, False, 0.0, 0.0, 0.0, 180.0, 20.0, 24, pp["tick"])
        return (p1 + p2 - 2 * pp["cost"]) * pp["brl"], max(t1, t2)
    lv = [v for v in s["levels"] if (v - ep) * d >= 6.0]
    w = (min(lv) if d == 1 else max(lv)) if lv else None
    tp = ep + d * 14.0 if w is None else ep + d * min(max(d * (w - 0.5 - ep), 5.5), 14.0)
    pts, t = sim2(*A_(D), D["u30"], k, j, ep, d, sl, tp, False, 0.0, 0.0, 0.0, 3.5, 1.0, 24, pp["tick"])
    return (pts - pp["cost"]) * pp["brl"], t


# ───────────────────────── gestão e métricas ─────────────────────────

def manage(rows, strat):
    """rows: dicts com date, asset, t_in, t_out, brl. ESP: um por vez. SNP: horários já aplicados + meta diária."""
    rows = sorted(rows, key=lambda r: (r["date"], r["t_in"]))
    acc, cur, last, done = [], None, -1, []
    for r in rows:
        if r["date"] != cur:
            cur, last, done = r["date"], -1, []
        if strat == "ESP":
            if r["t_in"] <= last:
                continue
            last = r["t_out"]
        else:
            cap = 180.0 if r["asset"] == "WIN" else 120.0
            if sum(x["brl"] for x in done if x["asset"] == r["asset"] and x["t_out"] < r["t_in"]) >= cap:
                continue
        acc.append(r)
        done.append(r)
    return acc


def stats(rows):
    if not rows:
        return dict(ops=0, pf=0.0, net=0.0, dd=0.0, rdd=0.0, meses="0/0", net_h1=0, net_h2=0, net_oos=0, pf_h1=0, pf_h2=0, pf_oos=0)
    rows = sorted(rows, key=lambda r: (r["date"], r["t_out"], r["t_in"]))
    p = np.array([r["brl"] for r in rows])
    eq = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, eq])[1:] - eq))
    pf = lambda q: round(float(q[q > 0].sum() / -q[q < 0].sum()), 2) if (q < 0).any() else 99.0
    dts = np.array([r["date"] for r in rows])
    h1, h2, oo = dts <= H1, (dts > H1) & (dts <= IS_END), dts > IS_END
    mon = pd.Series(p).groupby([x[:7] for x in dts]).sum()
    return dict(ops=len(p), pf=pf(p), net=round(float(eq[-1])), dd=round(dd), rdd=round(float(eq[-1]) / dd, 2) if dd else 99.0,
                meses=f"{int((mon > 0).sum())}/{len(mon)}", net_h1=round(float(p[h1].sum())), net_h2=round(float(p[h2].sum())),
                net_oos=round(float(p[oo].sum())), pf_h1=pf(p[h1]), pf_h2=pf(p[h2]), pf_oos=pf(p[oo]))


# ───────────────────────── grade ─────────────────────────

def run_grid(sigs, DSS, label):
    res, detail = [], {}
    # referência: mercado na abertura (mesma saída), e Sniper original quando houver
    base = []
    for s in sigs:
        D = DSS[s["asset"]][s["date"]]
        brl, t = run_exit(s, D, s["e"], -1, s["mkt_ep"], "fill200", None)
        base.append(dict(date=s["date"], asset=s["asset"], t_in=int(D["tm5"][s["e"]]), t_out=int(t), brl=brl))
    mb = {(r["date"], r["asset"], r["t_in"]): r["brl"] for r in base}
    detail["MKT"] = manage(base, label)
    res.append(dict(cfg="MKT", nivel="—", tipo="MKT", delta=0, validade=0, stop="fill200", fill_rate=100.0, **stats(detail["MKT"])))
    if label == "SNP":
        orig = [dict(date=s["date"], asset=s["asset"], t_in=bt.hm(s["orig_time"]), t_out=bt.hm(s["orig_exit"]),
                     brl=s["orig_brl"]) for s in sigs]
        res.append(dict(cfg="ORIGINAL (ordem do setup)", nivel="—", tipo="setup", delta=0, validade=0, stop="setup",
                        fill_rate=100.0, **stats(manage(orig, label))))
    for lvl, kind, vi in itertools.product(LEVELS, KINDS, VALID):
        for dl_i in range(5):
            for touch in (False, True):
                for sm in STOPM:
                    if touch and (kind == "STP" or sm != "fill200"):
                        continue
                    rows, n_fill, miss_mkt, fill_mkt = [], 0, [], []
                    for s in sigs:
                        D = DSS[s["asset"]][s["date"]]
                        delta = DELTA[s["asset"]][dl_i]
                        Ls = level_series(s["asset"], lvl, kind, D, s["e"], s["d"], s, s["typed"])
                        key = (s["date"], s["asset"], int(D["tm5"][s["e"]]))
                        if Ls is None:
                            miss_mkt.append(mb[key])
                            continue
                        op = order_price(Ls, kind, s["d"], delta)
                        k, j, ep = fill(*A_(D), op, s["e"], vi, s["d"], 0 if kind == "LMT" else 1, P[s["asset"]]["tick"],
                                        touch, s["cancel"], 955 if label == "ESP" else (1005 if s["asset"] == "WIN" else 1020))
                        if k < 0:
                            miss_mkt.append(mb[key])
                            continue
                        n_fill += 1
                        fill_mkt.append(mb[key])
                        brl, t = run_exit(s, D, k, j, ep, sm, float(Ls[s["e"]]))
                        rows.append(dict(date=s["date"], asset=s["asset"], t_in=int(D["tm5"][k]), t_out=int(t), brl=brl))
                    cfg = f"{lvl}|{kind}|{'tq' if touch else 'px'}|d{dl_i}|v{vi}|{sm}"
                    st = stats(manage(rows, label))
                    res.append(dict(cfg=cfg, nivel=lvl, tipo=kind + ("-toque" if touch else ""), delta=DELTA["WIN"][dl_i],
                                    validade=vi, stop=sm, fill_rate=round(100 * n_fill / len(sigs), 1),
                                    mkt_dos_executados=round(float(np.mean(fill_mkt)), 1) if fill_mkt else 0.0,
                                    mkt_dos_perdidos=round(float(np.mean(miss_mkt)), 1) if miss_mkt else 0.0, **st))
        print(label, lvl, kind, vi, "ok", flush=True)
    G = pd.DataFrame(res)
    # platô: mediana do Ret/DD da config e das vizinhas (δ ±1 passo, validade ±1 passo), só configs válidas
    G["valida"] = (G.ops >= 100) & (G.pf_h1 > 1.0) & (G.pf_h2 > 1.0) & (G.pf_oos > 1.0)
    idx = {r.cfg: (r.rdd if r.valida else 0.0) for r in G.itertuples()}
    plat = []
    for r in G.itertuples():
        if "|" not in r.cfg:
            plat.append(np.nan)
            continue
        lv, kd, tq, dd_, vv, sm = r.cfg.split("|")
        di, vi = int(dd_[1:]), int(vv[1:])
        vals = [idx[r.cfg]]
        for nd in (di - 1, di + 1):
            if 0 <= nd < 5:
                vals.append(idx.get(f"{lv}|{kd}|{tq}|d{nd}|v{vi}|{sm}", 0.0))
        vpos = VALID.index(vi)
        for nv in (vpos - 1, vpos + 1):
            if 0 <= nv < 3:
                vals.append(idx.get(f"{lv}|{kd}|{tq}|d{di}|v{VALID[nv]}|{sm}", 0.0))
        plat.append(float(np.median(vals)))
    G["plato"] = plat
    return G


# ───────────────────────── filtros por nível (3.3), entrada a mercado ─────────────────────────

def level_filters(sigs, DSS):
    out = []
    base = {}
    for s in sigs:
        D = DSS[s["asset"]][s["date"]]
        base[id(s)] = run_exit(s, D, s["e"], -1, s["mkt_ep"], "fill200", None)
    def emit(name, keep):
        rows = []
        for s in sigs:
            if not keep(s):
                continue
            D = DSS[s["asset"]][s["date"]]
            brl, t = base[id(s)]
            rows.append(dict(date=s["date"], asset=s["asset"], t_in=int(D["tm5"][s["e"]]), t_out=int(t), brl=brl))
        out.append(dict(filtro=name, n_sinais=sum(1 for s in sigs if keep(s)), **stats(manage(rows, sigs[0]["strat"]))))
    pp = P[sigs[0]["asset"]] if sigs[0]["strat"] == "ESP" else None

    def sup_between(s, kinds):
        D = DSSD(s)
        e, d, ep = s["e"], s["d"], s["mkt_ep"]
        slv = P[s["asset"]]["sl"]
        cand = []
        if "W" in kinds:
            cand += s["typed"]["Wall"] + s["typed"]["MidWall"]
        if "N" in kinds:
            cand += [D["c50"][e], D["l50"][e] if d == 1 else D["u50"][e], D["l30"][e] if d == 1 else D["u30"][e]]
        return any(0 < d * (ep - L) <= slv for L in cand)

    def space(s, X):
        e, d, ep = s["e"], s["d"], s["mkt_ep"]
        opp = [L for L in s["typed"]["Wall"] + s["typed"]["MidWall"] if d * (L - ep) > 0]
        return (min(d * (L - ep) for L in opp) if opp else 1e9) >= X

    DSSD = lambda s: DSS[s["asset"]][s["date"]]
    emit("nenhum (mercado)", lambda s: True)
    emit("F-dist: Wall/MidWall entre entrada e stop", lambda s: sup_between(s, "W"))
    emit("F-dist: banda NWE entre entrada e stop", lambda s: sup_between(s, "N"))
    emit("F-dist: qualquer suporte entre entrada e stop", lambda s: sup_between(s, "WN"))
    for xw, xd in ((150.0, 4.0), (250.0, 6.0), (400.0, 10.0)):
        emit(f"F-espaço: resistência a ≥ {xw:g} pts WIN / {xd:g} pts WDO",
             lambda s, xw=xw, xd=xd: space(s, xw if s["asset"] == "WIN" else xd))
    return pd.DataFrame(out)


def f_touch(sigs, DSS, N):
    """F-toque: em até N barras o preço testa o suporte (Wall/MidWall/NWE50 banda/NWE30 banda) e fecha do lado certo;
    entrada na abertura seguinte."""
    rows, n = [], 0
    for s in sigs:
        D = DSS[s["asset"]][s["date"]]
        e, d = s["e"], s["d"]
        tol = 15.0 if s["asset"] == "WIN" else 0.5
        for k in range(e, min(e + N, len(D["o5"]) - 1)):
            sup = s["typed"]["Wall"] + s["typed"]["MidWall"] + [D["l50"][k] if d == 1 else D["u50"][k], D["l30"][k] if d == 1 else D["u30"][k]]
            ext = D["l5"][k] if d == 1 else D["h5"][k]
            touched = any(d * (ext - L) <= tol and d * (D["c5"][k] - L) > 0 for L in sup)
            if touched and D["tm5"][k + 1] <= 955:
                n += 1
                ep = float(D["o5"][k + 1])
                brl, t = run_exit(s, D, k + 1, -1, ep, "fill200", None)
                rows.append(dict(date=s["date"], asset=s["asset"], t_in=int(D["tm5"][k + 1]), t_out=int(t), brl=brl))
                break
            if (D["l5"][k] < s["cancel"] if d == 1 else D["h5"][k] > s["cancel"]) if s["cancel"] == s["cancel"] else False:
                break
    return dict(filtro=f"F-toque: testa suporte em ≤ {N} barras e fecha a favor", n_sinais=n,
                **stats(manage(rows, sigs[0]["strat"])))


def main():
    os.makedirs(OUT, exist_ok=True)
    DSS = {a: bt.market(a) for a in ("WIN", "WDO")}
    pd.set_option("display.width", 260)
    cols = ["cfg", "fill_rate", "ops", "pf", "net", "dd", "rdd", "plato", "meses", "pf_h1", "pf_h2", "pf_oos",
            "mkt_dos_executados", "mkt_dos_perdidos"]
    for label, sigs in (("ESP", esp_signals(DSS["WIN"])), ("SNP", snp_signals(DSS))):
        print(label, "sinais:", len(sigs), flush=True)
        G = run_grid(sigs, DSS, label)
        G.to_csv(os.path.join(OUT, f"grade_{label}.csv"), index=False)
        print(f"\n===== {label} — referências")
        print(G[G.cfg.isin(["MKT", "ORIGINAL (ordem do setup)"])][cols].to_string(index=False))
        print(f"\n===== {label} — top 20 por platô (válidas: ≥100 trades, PF>1 em jan–abr, mai–jul, ago–nov)")
        print(G[G.valida].sort_values(["plato", "rdd"], ascending=False)[cols].head(20).to_string(index=False))
        print(f"\n===== {label} — melhor platô por nível × tipo")
        best = G[G.valida & G.plato.notna()].sort_values("plato", ascending=False).groupby(["nivel", "tipo"]).head(1)
        print(best.sort_values(["nivel", "tipo"])[["nivel", "tipo"] + cols].to_string(index=False))
        F = level_filters(sigs, DSS)
        F = pd.concat([F, pd.DataFrame([f_touch(sigs, DSS, 3), f_touch(sigs, DSS, 6)])], ignore_index=True)
        F.to_csv(os.path.join(OUT, f"filtros_{label}.csv"), index=False)
        print(f"\n===== {label} — nível como filtro (entrada a mercado)")
        print(F[["filtro", "n_sinais", "ops", "pf", "net", "dd", "rdd", "meses", "pf_h1", "pf_h2", "pf_oos"]].to_string(index=False))


if __name__ == "__main__":
    main()
