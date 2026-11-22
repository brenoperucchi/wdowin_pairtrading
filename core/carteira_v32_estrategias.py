# -*- coding: utf-8 -*-
"""
Carteira V3.2 (4 novas estratégias independentes — Opção A no painel 5176).

Regra única compartilhada entre histórico (injeção no JSON) e motor ao vivo
(`core/gex_live_dealer_engine.py`):
  1. C1a_BRK_WIN : WIN (1 ct) · BRK_F1F2 convergência (conv_k1w2 | near&crs | hh!=11 | ext50_trend<0.5) · SL 280 / TP 280 / tmax 24
  2. V1a_DIV_WDO : WDO (1 ct) · V32_OPEN Wall z=3.5/p=6.0 | CONF | d_wall<=3.5 | hh!=11 | ext30>0 · SL 14 / TP ProxWall [4..22] min 2.5 / tmax 24
  3. SYM_DIV_WIN : WIN (1 ct) · V32_OPEN Wall | CONF | seq<=1 | hh!=11 | ext50>-0.5 & slope50>-0.5 · SL 280 / TP 240 / tmax 24
  4. SYM_DIV_WDO : WDO (1 ct) · V32_OPEN Wall | CONF | seq<=1 | hh!=11 | ext50>-0.5 & slope50>-0.5 · SL 14 / TP ProxWall [3.5..20] min 2.0 / tmax 18

Todas são 100% causais (usam apenas barras fechadas para o sinal e `nwe*_` da barra anterior `e-1`)
e operam de forma INDEPENDENTE entre si (`UM_POR_VEZ` apenas contra a própria posição).
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

_ESP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "research",
    "div_master",
    "especialistas",
)
if _ESP not in sys.path:
    sys.path.insert(0, _ESP)

import modulo as _M  # noqa: E402

OPT_OPEN = {**_M.V32, "abertura": _M.V22_ABERTURA}

STRAT_CFGS: Dict[str, dict] = {
    "C1a_BRK_WIN": {
        "asset": "WIN",
        "short": "WIN Brk Conv C1a",
        "contracts": 1,
        "tick": 5.0,
        "cost": 10.0,
        "brl_pt": 0.20,
        "t_start": 545,
        "t_end": 1005,
        "eod": 1045,
        "sl": 280.0,
        "tp_mode": "fix",
        "tp_fix": 280.0,
        "tmax": 24,
        "tp_tag_fmt": "ALVO 280 · 120 MIN",
    },
    "V1a_DIV_WDO": {
        "asset": "WDO",
        "short": "WDO Div V3.2 V1a",
        "contracts": 1,
        "tick": 0.5,
        "cost": 0.5,
        "brl_pt": 10.0,
        "t_start": 540,
        "t_end": 1020,
        "eod": 1045,
        "sl": 14.0,
        "tp_mode": "nw",
        "nw_min": 2.5,
        "nw_lo": 4.0,
        "nw_hi": 22.0,
        "front": 0.5,
        "tmax": 24,
        "tp_tag_fmt": "PROX WALL [4..22]",
    },
    "SYM_DIV_WIN": {
        "asset": "WIN",
        "short": "WIN Simétrica V3.2",
        "contracts": 1,
        "tick": 5.0,
        "cost": 10.0,
        "brl_pt": 0.20,
        "t_start": 545,
        "t_end": 1005,
        "eod": 1045,
        "sl": 280.0,
        "tp_mode": "fix",
        "tp_fix": 240.0,
        "tmax": 24,
        "tp_tag_fmt": "ALVO 240 · 120 MIN",
    },
    "SYM_DIV_WDO": {
        "asset": "WDO",
        "short": "WDO Simétrica V3.2",
        "contracts": 1,
        "tick": 0.5,
        "cost": 0.5,
        "brl_pt": 10.0,
        "t_start": 540,
        "t_end": 1020,
        "eod": 1045,
        "sl": 14.0,
        "tp_mode": "nw",
        "nw_min": 2.0,
        "nw_lo": 3.5,
        "nw_hi": 20.0,
        "front": 0.5,
        "tmax": 18,
        "tp_tag_fmt": "PROX WALL [3.5..20]",
    },
}


def _hm(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


def _round_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 2)


def _next_level(levels: List[float], ep: float, d: int, min_step: float) -> Optional[float]:
    if d == 1:
        for w in levels:
            if w - ep >= min_step:
                return float(w)
    else:
        for w in reversed(levels):
            if ep - w >= min_step:
                return float(w)
    return None


def _norm_bars(bars: List[dict]) -> List[dict]:
    return [
        {
            "time": str(b["time"])[:5],
            "open": float(b["open"]),
            "high": float(b["high"]),
            "low": float(b["low"]),
            "close": float(b["close"]),
            "wave": float(b.get("wave", b.get("smart_swing_wave", 0.0)) or 0.0),
        }
        for b in bars
    ]


def _split_walls(walls: List[dict]) -> tuple[List[float], List[float]]:
    w_all = sorted(
        {
            float(w["price"])
            for w in (walls or [])
            if w.get("type") in _M.LEVEL_TYPES and w.get("price") is not None
        }
    )
    w_wall = sorted(
        {
            float(w["price"])
            for w in (walls or [])
            if w.get("type") == "Wall" and w.get("price") is not None
        }
    )
    return w_all, w_wall


def _extract_pivots_v32(fb: List[dict], atr: List[float], P: dict, open_module: bool = True) -> List[tuple]:
    n = len(fb)
    t_open = _M.hm(_M.COMMON["open_conf_end"])
    t_seed = _M.hm(_M.COMMON["seed_end"])
    ev = [
        (p["conf"], p["idx"], p["side"], True, "zz")
        for p in _M.zigzag(fb, atr, _M.COMMON["r_atr"], P["zz_floor"])
    ]
    if open_module:
        for p in _M.zigzag(fb, atr, _M.COMMON["r_atr_open"], P["zz_floor"]):
            if _hm(fb[p["conf"]]["time"]) <= t_open:
                ev.append((p["conf"], p["idx"], p["side"], True, "zz08"))
        seeded = {1: False, -1: False}
        for j in range(1, n - 1):
            conf = j + 1
            for d in (1, -1):
                if (
                    _hm(fb[conf]["time"]) <= t_open
                    and _M.is_piv(fb, j, d, 2, 1)
                    and d * (fb[conf]["close"] - fb[conf]["open"]) > 0
                ):
                    ev.append((conf, j, d, True, "lr"))
                if not seeded[d] and _hm(fb[j]["time"]) <= t_seed and _M.is_piv(fb, j, d, 1, 1):
                    ev.append((conf, j, d, False, "seed"))
                    seeded[d] = True
        ev.append((0, 0, 1, False, "seed0"))
        ev.append((0, 0, -1, False, "seed0"))
    order = ("seed0", "seed", "zz", "zz08", "lr")
    ev.sort(key=lambda e: (e[0], e[1], order.index(e[4])))
    return ev


def _brk_f1f2_cands(fb: List[dict], w_wall: List[float], P: dict, atr: List[float]) -> List[dict]:
    """Rompimento F1 -> F2 com convergência no fluxo (`busca_convergencia_v32.engine_brk_f1f2`)."""
    n = len(fb)
    if n < 3:
        return []
    ev = _extract_pivots_v32(fb, atr, P, open_module=True)
    by_conf: Dict[int, List[tuple]] = {}
    for conf, j, side, _, _ in ev:
        by_conf.setdefault(conf, []).append((j, side))

    pool = {1: [], -1: []}
    seen = {1: set(), -1: set()}
    broken_k = {1: set(), -1: set()}
    rm = _M.RunMedian()
    out: List[dict] = []

    for t in range(n):
        rm.add(abs(float(fb[t]["wave"])))
        if t - 1 in by_conf:
            for j, side in by_conf[t - 1]:
                if j not in seen[side]:
                    seen[side].add(j)
                    px_piv = fb[j]["low"] if side == 1 else fb[j]["high"]
                    pool[side].append((j, px_piv))
                    pool[side].sort()
        if t < 2:
            continue

        thr = _M.COMMON["k_v31"] * rm.get()
        bt_bar = fb[t]
        prev_bar = fb[t - 1]
        c_t, o_t = float(bt_bar["close"]), float(bt_bar["open"])
        c_prev = float(prev_bar["close"])
        w2 = float(bt_bar["wave"])

        for dr, piv_side in ((1, -1), (-1, 1)):
            if dr * (c_t - o_t) <= 0:
                continue
            cands_k = []
            for k, pk in pool[piv_side]:
                gap = t - k
                if gap < _M.COMMON["min_gap"] or gap > _M.COMMON["max_gap"] or k in broken_k[dr]:
                    continue
                if dr == 1:
                    if not (c_prev <= pk + P["buf"] and c_t > pk):
                        continue
                else:
                    if not (c_prev >= pk - P["buf"] and c_t < pk):
                        continue
                ws_k1 = [float(fb[x]["wave"]) for x in range(max(0, k - 1), min(t, k + 1) + 1)]
                w1_k1 = max(ws_k1) if dr == 1 else min(ws_k1)
                cands_k.append((k, pk, w1_k1))

            if not cands_k:
                continue

            k, pk, w1_k1 = max(cands_k, key=lambda x: x[0])
            broken_k[dr].add(k)

            d_wall_piv = min((abs(pk - w) for w in w_wall), default=99999.0)
            d_wall_brk = min((abs(c_t - w) for w in w_wall), default=99999.0)
            if dr == 1:
                w_crossed = [w for w in w_wall if min(o_t, c_prev, pk - P["zone"]) <= w <= c_t]
            else:
                w_crossed = [w for w in w_wall if c_t <= w <= max(o_t, c_prev, pk + P["zone"])]

            wd_k1 = dr * (w2 - w1_k1)
            out.append(
                {
                    "dir": dr,
                    "k": k,
                    "idx_sig": t,
                    "px1": pk,
                    "w1_k1": w1_k1,
                    "w2": w2,
                    "conv_k1_ok": wd_k1 > thr,
                    "w2_fav": dr * w2 > 0,
                    "near_wall": min(d_wall_piv, d_wall_brk) <= P["zone"],
                    "crossed_wall": bool(w_crossed),
                }
            )
    return out


def _resolve_entry_idx(fb: List[dict], idx_sig: int, ex: List[dict], pos: Dict[str, int]) -> Optional[int]:
    if idx_sig + 1 < len(fb):
        e = pos.get(fb[idx_sig + 1]["time"])
    else:
        p_sig = pos.get(fb[idx_sig]["time"])
        e = (p_sig + 1) if (p_sig is not None and p_sig + 1 < len(ex)) else None
    if e is None or e < 1:
        return None
    return e


def _sim_sl_tp(
    ex: List[dict],
    e: int,
    ep: float,
    d: int,
    sl: float,
    tp_px: float,
    tmax: int,
    tick: float,
    eod: int,
    is_live: bool,
) -> dict:
    """Saída M5 causal: abertura -> extremo desfavorável -> extremo favorável -> fechamento."""
    stop = ep - d * sl
    n = len(ex)
    for k in range(e, n):
        b = ex[k]
        tm = _hm(b["time"])
        if k > e:
            if tm >= eod or k - e > tmax:
                return {
                    "k": k,
                    "px": float(b["open"]),
                    "why": "17:25" if tm >= eod else "TEMPO",
                    "open": False,
                }
        ticks = [
            (float(b["open"]), True),
            (float(b["low"] if d == 1 else b["high"]), False),
            (float(b["high"] if d == 1 else b["low"]), False),
            (float(b["close"]), False),
        ]
        for j, (p, op) in enumerate(ticks):
            if k == e and j == 0:
                continue
            if (p - stop) * d <= 0:
                return {
                    "k": k,
                    "px": p if op else stop - d * tick,
                    "why": "STOP",
                    "open": False,
                }
            if (p - tp_px) * d >= 0:
                return {
                    "k": k,
                    "px": p if op else tp_px,
                    "why": "ALVO",
                    "open": False,
                }
    last = ex[n - 1]
    return {
        "k": n - 1,
        "px": float(last["close"]),
        "why": "ABERTA" if is_live else "FIM",
        "open": is_live,
    }


def _nwe50_ctx(ex: List[dict], e: int, d: int, tick: float) -> Optional[tuple[float, float]]:
    n50 = float(ex[e - 1].get("nwe50_line") or 0.0)
    u50 = float(ex[e - 1].get("nwe50_upper") or 0.0)
    if e <= 6:
        n50_old = float(ex[0].get("nwe50_prev_line") or ex[0].get("nwe50_line") or 0.0)
    else:
        n50_old = float(ex[e - 7].get("nwe50_line") or 0.0)
    if n50 <= 0 or u50 <= 0:
        return None
    half = max(u50 - n50, tick)
    c_prev = float(ex[e - 1]["close"])
    ext_div = -d * (c_prev - n50) / half
    slope50 = d * (n50 - n50_old) / half
    return ext_div, slope50


def _nwe30_ext(ex: List[dict], e: int, d: int, tick: float) -> Optional[float]:
    u30 = float(ex[e - 1].get("nwe30_upper") or 0.0)
    l30 = float(ex[e - 1].get("nwe30_lower") or 0.0)
    if u30 <= 0 or l30 <= 0:
        return None
    mid30 = 0.5 * (u30 + l30)
    half30 = max(0.5 * (u30 - l30), tick)
    return -d * (float(ex[e - 1]["close"]) - mid30) / half30


def _build_trade_row(
    sid: str,
    cfg: dict,
    ex: List[dict],
    e: int,
    ep: float,
    d: int,
    tp_px: float,
    res: dict,
    meta: dict,
) -> dict:
    gross = (res["px"] - ep) * d
    pts_1c = round(gross - (0.0 if res["open"] else cfg["cost"]), 2)
    pts_tot = round(pts_1c * cfg["contracts"], 1)
    tp_pts = round(abs(tp_px - ep), 2)
    k = res["k"]
    return {
        "strategy_id": sid,
        "entry_idx": e,
        "time": ex[e]["time"][:5],
        "exit_idx": k,
        "exit_time": ex[k]["time"][:5],
        "direction": "COMPRA" if d == 1 else "VENDA",
        "dir_num": d,
        "entry_price": round(ep, 2),
        "exit_price": round(res["px"], 2),
        "stop_price": round(ep - d * cfg["sl"], 2),
        "tp_price": round(tp_px, 2),
        "tp_pts": tp_pts,
        "be_trigger_price": None,
        "be_stop_price": None,
        "be_triggered": False,
        "be_time": None,
        "time_limit": ex[min(e + cfg["tmax"] + 1, len(ex) - 1)]["time"][:5],
        "exit_reason": res["why"],
        "is_open": res["open"],
        "pts": pts_tot,
        "brl_1c": round(pts_tot * cfg["brl_pt"], 2),
        "contracts": cfg["contracts"],
        **meta,
    }


def _run_c1a_brk_win(
    fb: List[dict], ex: List[dict], pos: Dict[str, int], w_wall: List[float], is_live: bool
) -> List[dict]:
    sid = "C1a_BRK_WIN"
    cfg = STRAT_CFGS[sid]
    P = _M.PARAMS["WIN"]
    atr = _M.atr_series(fb, P["tick"])
    cands = _brk_f1f2_cands(fb, w_wall, P, atr)

    rows = []
    for c in cands:
        if not (c["conv_k1_ok"] and c["w2_fav"] and c["near_wall"] and c["crossed_wall"]):
            continue
        e = _resolve_entry_idx(fb, c["idx_sig"], ex, pos)
        if e is None:
            continue
        tm = _hm(ex[e]["time"])
        if not (cfg["t_start"] <= tm <= cfg["t_end"]) or (tm // 60) == 11:
            continue
        ctx = _nwe50_ctx(ex, e, c["dir"], cfg["tick"])
        if ctx is None:
            continue
        ext_div, _ = ctx
        ext50_trend = -ext_div
        if not (ext50_trend < 0.5):
            continue
        rows.append((tm, c["idx_sig"], e, c["dir"], ext50_trend, c))

    out, last_exit = [], -1
    for tm, _, e, d, ext50_trend, c in sorted(rows, key=lambda r: (r[0], r[1])):
        if tm <= last_exit:
            continue
        ep = float(ex[e]["open"])
        tp_px = _round_tick(ep + d * cfg["tp_fix"], cfg["tick"])
        res = _sim_sl_tp(ex, e, ep, d, cfg["sl"], tp_px, cfg["tmax"], cfg["tick"], cfg["eod"], is_live)
        sig_time = fb[c["idx_sig"]]["time"][:5]
        f1_time = fb[c["k"]]["time"][:5]
        out.append(
            _build_trade_row(
                sid, cfg, ex, e, ep, d, tp_px, res,
                {
                    "reason_detail": (
                        f"BRK_F1F2 Conv · F1 {f1_time} ({c['px1']:.0f}) → romp {sig_time} · "
                        f"ext50_t={ext50_trend:+.2f} · SL {cfg['sl']:.0f} / TP {cfg['tp_fix']:.0f} / {cfg['tmax']}b"
                    ),
                },
            )
        )
        last_exit = _hm(ex[res["k"]]["time"]) if not res["open"] else 10**6
    return out


def _run_v1a_div_wdo(
    fb: List[dict], ex: List[dict], pos: Dict[str, int], w_all: List[float], w_wall: List[float], is_live: bool
) -> List[dict]:
    sid = "V1a_DIV_WDO"
    cfg = STRAT_CFGS[sid]
    P = {**_M.PARAMS["WDO"], "zone": 3.5, "pierce_max": 6.0}
    atr = _M.atr_series(fb, P["tick"])
    cands = _M.engine_v32(fb, w_wall, P, "common", atr=atr, opt=OPT_OPEN)

    rows = []
    for c in cands:
        d = int(c["dir"])
        d_wall = min((abs(float(c["px2"]) - w) for w in w_wall), default=999.0)
        if d_wall > 3.5:
            continue
        e = _resolve_entry_idx(fb, int(c["conf"]), ex, pos)
        if e is None:
            continue
        tm = _hm(ex[e]["time"])
        if not (cfg["t_start"] <= tm <= cfg["t_end"]) or (tm // 60) == 11:
            continue
        ext30 = _nwe30_ext(ex, e, d, cfg["tick"])
        if ext30 is None or not (ext30 > 0.0):
            continue
        rows.append((tm, int(c["j"]), e, d, d_wall, ext30, c))

    out, last_exit = [], -1
    for tm, _, e, d, d_wall, ext30, c in sorted(rows, key=lambda r: (r[0], r[1])):
        ep = float(ex[e]["open"])
        nw = _next_level(w_all, ep, d, 2.0 + cfg["front"])
        nwd = d * (nw - ep) - cfg["front"] if nw is not None else None
        if nwd is None or nwd < cfg["nw_min"]:
            continue
        if tm <= last_exit:
            continue
        tp_pts = min(max(nwd, cfg["nw_lo"]), cfg["nw_hi"])
        tp_px = _round_tick(ep + d * tp_pts, cfg["tick"])
        res = _sim_sl_tp(ex, e, ep, d, cfg["sl"], tp_px, cfg["tmax"], cfg["tick"], cfg["eod"], is_live)
        f1_t = fb[c["k"]]["time"][:5]
        f2_t = fb[c["j"]]["time"][:5]
        out.append(
            _build_trade_row(
                sid, cfg, ex, e, ep, d, tp_px, res,
                {
                    "reason_detail": (
                        f"V1a Div V3.2 · {f1_t}→{f2_t} · dW={d_wall:.1f}p · ext30={ext30:+.2f} · "
                        f"SL {cfg['sl']:.1f} / TP ProxWall {tp_pts:.1f}p / {cfg['tmax']}b"
                    ),
                },
            )
        )
        last_exit = _hm(ex[res["k"]]["time"]) if not res["open"] else 10**6
    return out


def _run_sym_top1(
    sid: str,
    fb: List[dict],
    ex: List[dict],
    pos: Dict[str, int],
    w_all: List[float],
    w_wall: List[float],
    is_live: bool,
) -> List[dict]:
    cfg = STRAT_CFGS[sid]
    asset = cfg["asset"]
    P = _M.PARAMS[asset]
    atr = _M.atr_series(fb, P["tick"])
    cands = _M.engine_v32(fb, w_wall, P, "common", atr=atr, opt=OPT_OPEN)

    seq = {1: 0, -1: 0}
    rows = []
    for c in cands:
        conf = int(c["conf"])
        d = int(c["dir"])
        if conf + 1 >= len(fb) and not is_live:
            continue
        s = seq[d]
        seq[d] += 1
        if s > 1:
            continue
        e = _resolve_entry_idx(fb, conf, ex, pos)
        if e is None:
            continue
        tm = _hm(ex[e]["time"])
        if not (cfg["t_start"] <= tm <= cfg["t_end"]) or (tm // 60) == 11:
            continue
        ctx = _nwe50_ctx(ex, e, d, cfg["tick"])
        if ctx is None:
            continue
        ext50, slope50 = ctx
        if not (ext50 > -0.5 and slope50 > -0.5):
            continue
        rows.append((tm, int(c["j"]), e, d, s, ext50, slope50, c))

    out, last_exit = [], -1
    for tm, _, e, d, s, ext50, slope50, c in sorted(rows, key=lambda r: (r[0], r[1])):
        ep = float(ex[e]["open"])
        if cfg["tp_mode"] == "nw":
            nw = _next_level(w_all, ep, d, 2.0 + cfg["front"])
            nwd = d * (nw - ep) - cfg["front"] if nw is not None else None
            if nwd is None or nwd < cfg["nw_min"]:
                continue
            tp_pts = min(max(nwd, cfg["nw_lo"]), cfg["nw_hi"])
            tp_px = _round_tick(ep + d * tp_pts, cfg["tick"])
            tp_desc = f"ProxWall {tp_pts:.1f}p"
        else:
            tp_pts = cfg["tp_fix"]
            tp_px = _round_tick(ep + d * tp_pts, cfg["tick"])
            tp_desc = f"{tp_pts:.0f}p"
        if tm <= last_exit:
            continue
        res = _sim_sl_tp(ex, e, ep, d, cfg["sl"], tp_px, cfg["tmax"], cfg["tick"], cfg["eod"], is_live)
        f1_t = fb[c["k"]]["time"][:5]
        f2_t = fb[c["j"]]["time"][:5]
        out.append(
            _build_trade_row(
                sid, cfg, ex, e, ep, d, tp_px, res,
                {
                    "reason_detail": (
                        f"SYM_TOP1 Div V3.2 · seq={s + 1} · {f1_t}→{f2_t} · ext50={ext50:+.2f} sl={slope50:+.2f} · "
                        f"SL {cfg['sl']:.0f} / TP {tp_desc} / {cfg['tmax']}b"
                    ),
                },
            )
        )
        last_exit = _hm(ex[res["k"]]["time"]) if not res["open"] else 10**6
    return out


def run_strategy(
    strategy_id: str,
    sig_bars: List[dict],
    walls: List[dict],
    exec_bars: Optional[List[dict]] = None,
    is_live: bool = False,
) -> List[dict]:
    ex = exec_bars if exec_bars is not None else sig_bars
    if len(sig_bars) < 5 or not ex:
        return []
    fb = _norm_bars(sig_bars)
    w_all, w_wall = _split_walls(walls)
    pos = {str(b["time"])[:5]: i for i, b in enumerate(ex)}

    if strategy_id == "C1a_BRK_WIN":
        return _run_c1a_brk_win(fb, ex, pos, w_wall, is_live)
    if strategy_id == "V1a_DIV_WDO":
        return _run_v1a_div_wdo(fb, ex, pos, w_all, w_wall, is_live)
    if strategy_id in ("SYM_DIV_WIN", "SYM_DIV_WDO"):
        return _run_sym_top1(strategy_id, fb, ex, pos, w_all, w_wall, is_live)
    raise ValueError(f"Estratégia desconhecida: {strategy_id}")


def run_all_for_asset(
    asset: str,
    sig_bars: List[dict],
    walls: List[dict],
    exec_bars: Optional[List[dict]] = None,
    is_live: bool = False,
) -> List[dict]:
    """Executa todas as estratégias da Carteira V3.2 para o ativo (`WIN` ou `WDO`), de forma independente."""
    a = asset.upper()
    sids = [sid for sid, cfg in STRAT_CFGS.items() if cfg["asset"] == a]
    trades: List[dict] = []
    for sid in sids:
        trades.extend(run_strategy(sid, sig_bars, walls, exec_bars=exec_bars, is_live=is_live))
    trades.sort(key=lambda t: (t["entry_idx"], t["strategy_id"]))
    return trades
