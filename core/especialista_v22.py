"""
Especialista de divergência ESP_DIV_V22_WIN (painel 5176) — regra única usada pelo histórico e pelo motor ao vivo.

O ID ficou ESP_DIV_V22_WIN por compatibilidade (logs, calendário, painel); o motor é o v3.2 desde 12/11/2026.

Regra (pesquisa em research/div_master/especialistas, motor v3.2 em research/div_master/v32):
  - sinal: motor de divergência v3.2 sem módulo de abertura (`modulo.engine_v32` com `V32_PROD`), âncora Wall/MidWall
    ou extremo do dia,
    gatilho Opção C (a)+(b); descarta super-confluência; no máximo o 2º gatilho do dia em cada direção;
  - contexto: entrada entre 10:00 e 15:55; ext50 > −0,5 e slope50 > −0,5 (NWE 50 · bw 8 · mult 3);
  - entrada: a mercado na abertura da barra seguinte ao gatilho; um trade por vez;
  - saída: SL 200 pts, sem alvo, BE +180 → +20, máximo 12 barras (sai na abertura da 13ª) ou 17:25;
  - 2 contratos; custo 10 pts por contrato; stop sem gap preenche 1 tick pior.

`run()` é pura e causal: só usa as barras recebidas. No BT recebe as barras do Profit (sinal) e as do MT5 (execução);
ao vivo recebe as barras do motor nos dois papéis.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

_ESP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "div_master", "especialistas")
if _ESP not in sys.path:
    sys.path.insert(0, _ESP)

import modulo as _M  # noqa: E402

STRATEGY_ID = "ESP_DIV_V22_WIN"
CFG = dict(sl=200.0, be_trig=180.0, be_lock=20.0, tmax=12, t_start=600, t_end=960, ext_min=-0.5, slope_min=-0.5,
           cost=10.0, brl_pt=0.20, contracts=2, tick=5.0, eod=1045)


def _hm(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


def _fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _sim(ex: List[dict], e: int, ep: float, d: int, is_live: bool) -> dict:
    """Saída em barras M5 (ordem O → extremo contra → extremo a favor → C). Igual ao bt.sim sem alvo."""
    c = CFG
    stop = ep - d * c["sl"]
    mfe = 0.0
    be_k = None
    n = len(ex)
    for k in range(e, n):
        b = ex[k]
        tm = _hm(b["time"])
        if k > e:
            if tm >= c["eod"] or k - e > c["tmax"]:
                return dict(k=k, px=float(b["open"]), why="17:25" if tm >= c["eod"] else "TEMPO", be_k=be_k, open=False)
            if mfe >= c["be_trig"]:
                cand = ep + d * c["be_lock"]
                if (float(b["open"]) - cand) * d > 0 and (cand - stop) * d > 0:
                    stop, be_k = cand, k
        ticks = [(float(b["open"]), True), (float(b["low"] if d == 1 else b["high"]), False),
                 (float(b["high"] if d == 1 else b["low"]), False), (float(b["close"]), False)]
        for j, (p, op) in enumerate(ticks):
            if k == e and j == 0:
                continue          # a entrada é a própria abertura
            if (p - stop) * d <= 0:
                return dict(k=k, px=(p if op else stop - d * c["tick"]), why="BE" if be_k is not None else "STOP",
                            be_k=be_k, open=False)
            mfe = max(mfe, (p - ep) * d)
    last = ex[n - 1]
    return dict(k=n - 1, px=float(last["close"]), why="ABERTA" if is_live else "FIM", be_k=be_k, open=is_live)


def run(sig_bars: List[dict], walls: List[dict], exec_bars: Optional[List[dict]] = None, is_live: bool = False) -> List[Dict]:
    """
    sig_bars : barras M5 do pregão [{time, open, high, low, close, wave}] (sem barras do dia anterior).
    exec_bars: barras M5 de execução [{time, open, high, low, close, nwe50_line, nwe50_upper}]; padrão = sig_bars.
    walls    : [{type, price}] do dia.
    Retorna os trades do dia (em ordem), cada um com preços, saída e resultado.
    """
    c = CFG
    ex = exec_bars if exec_bars is not None else sig_bars
    if len(sig_bars) < 5 or not ex:
        return []
    P = _M.PARAMS["WIN"]
    fb = [dict(time=str(b["time"])[:5], open=float(b["open"]), high=float(b["high"]), low=float(b["low"]),
               close=float(b["close"]), wave=float(b.get("wave", b.get("smart_swing_wave", 0.0)) or 0.0)) for b in sig_bars]
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in _M.LEVEL_TYPES and w.get("price") is not None)
    atr = _M.atr_series(fb, P["tick"])
    cands = _M.engine_v32(fb, levels, P, "common", atr=atr, opt=_M.V32_PROD)
    trig, _ = _M.triggers(fb, cands, P)
    by = {(x["dir"], x["j"]): x for x in cands}
    pos = {str(b["time"])[:5]: i for i, b in enumerate(ex)}
    seq = {1: 0, -1: 0}
    rows = []
    for x in trig:
        t = x["idx"]
        if t + 1 >= len(fb):
            continue
        cd = by[(x["dir"], x["j"])]
        s = seq[x["dir"]]
        seq[x["dir"]] += 1
        t_in = fb[t + 1]["time"]
        e = pos.get(t_in)
        if e is None or e < 1:
            continue
        rows.append(dict(e=e, tm=_hm(t_in), d=int(x["dir"]), seq=s, super=bool(x["super"]), esp=x["esp"], sub=x["sub"],
                         f1=fb[cd["k"]]["time"], f2=fb[cd["j"]]["time"], trig=fb[t]["time"]))
    out, last_exit = [], -1
    for r in sorted(rows, key=lambda z: z["tm"]):
        e, d = r["e"], r["d"]
        if r["super"] or r["seq"] > 1 or not (c["t_start"] <= r["tm"] < c["t_end"]):
            continue
        n50 = float(ex[e - 1].get("nwe50_line") or 0.0)
        u50 = float(ex[e - 1].get("nwe50_upper") or 0.0)
        n50_old = float(ex[max(0, e - 7)].get("nwe50_line") or 0.0)
        if n50 <= 0 or u50 <= 0:
            continue
        half = max(u50 - n50, c["tick"])
        ext = -d * (float(ex[e - 1]["close"]) - n50) / half
        slope = d * (n50 - n50_old) / half
        if not (ext > c["ext_min"] and slope > c["slope_min"]):
            continue
        if r["tm"] <= last_exit:
            continue
        ep = float(ex[e]["open"])
        res = _sim(ex, e, ep, d, is_live)
        gross = (res["px"] - ep) * d
        pts_tot = round((gross - (0.0 if res["open"] else c["cost"])) * c["contracts"], 1)
        k = res["k"]
        out.append(dict(
            strategy_id=STRATEGY_ID, entry_idx=e, time=ex[e]["time"][:5], exit_idx=k, exit_time=ex[k]["time"][:5],
            direction="COMPRA" if d == 1 else "VENDA", dir_num=d, entry_price=round(ep, 2), exit_price=round(res["px"], 2),
            stop_price=round(ep - d * c["sl"], 2), be_trigger_price=round(ep + d * c["be_trig"], 2),
            be_stop_price=round(ep + d * c["be_lock"], 2), be_triggered=res["be_k"] is not None,
            be_time=ex[res["be_k"]]["time"][:5] if res["be_k"] is not None else None,
            time_limit=ex[min(e + c["tmax"] + 1, len(ex) - 1)]["time"][:5], exit_reason=res["why"], is_open=res["open"],
            pts=pts_tot, brl_1c=round(pts_tot * c["brl_pt"], 2), contracts=c["contracts"],
            f1_time=r["f1"], f2_time=r["f2"], trigger_time=r["trig"], anchor=r["esp"], trigger_kind=r["sub"],
            ext50=round(ext, 2), slope50=round(slope, 2),
        ))
        last_exit = _hm(ex[k]["time"]) if not res["open"] else 10 ** 6
    return out
