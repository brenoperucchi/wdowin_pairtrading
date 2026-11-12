"""
Divergência Preço × Fluxo Smart Money na Wall — módulo ÚNICO de sinal e simulação.

Este módulo é a fonte de verdade para o setup de divergência na Wall. O backtest
(`research/div_wall/`) e o motor ao vivo devem chamar exatamente as mesmas funções daqui,
para que a paridade ao vivo × BT valha por construção.

Regras de causalidade (verificadas pelo teste de paridade `research/div_wall/parity_test.py`):
  - Toda função que avalia a barra `i` só lê barras `<= i`.
  - O sinal nasce no FECHAMENTO da barra de confirmação `i`; a entrada é na ABERTURA de `i+1`.
  - Alvos dinâmicos usados durante a barra `k` só leem a NWE da barra `k-1`.

Dados de entrada por barra M5 (mesma decomposição `.min` do Profit no BT e no ao vivo):
  time ("HH:MM"), open, high, low, close, buy_vol, sell_vol, avg_buy_lot, avg_sell_lot,
  inst_aggr_delta, inst_pass_delta, ret_delta_bar
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Sequence, Tuple

import numpy as np

# ─────────────────────────────── Constantes por ativo ───────────────────────────────

ASSET_SPECS = {
    # tick, R$ por ponto por contrato, custo ida+volta em pontos por contrato, slippage em stop
    "WIN": {"tick": 5.0, "brl_per_pt": 0.20, "cost_pts": 10.0, "stop_slip_pts": 5.0},
    "WDO": {"tick": 0.5, "brl_per_pt": 10.0, "cost_pts": 0.5, "stop_slip_pts": 0.5},
}

NWE_LOOKBACK = 100
NWE_BW = 8.0
NWE_MULT = 3.0


def round_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 4)


def hhmm_to_min(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


# ─────────────────────────────── NWE 100 / bw 8 (causal) ───────────────────────────────

def nwe_series(closes: np.ndarray, lookback: int = NWE_LOOKBACK, bw: float = NWE_BW, mult: float = NWE_MULT):
    """Envelope Nadaraya-Watson causal (idêntico a `compute_nwe_series` / UpdateNWE do MQL5)."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    center = np.zeros(n)
    mae = np.zeros(n)
    if n == 0:
        return center, center.copy(), center.copy()
    w_full = np.exp(-np.arange(lookback, dtype=float) ** 2 / (2.0 * bw * bw))
    for t in range(n):
        l_idx = min(t, lookback - 1)
        w_t = w_full[: l_idx + 1]
        p_t = closes[t - l_idx: t + 1][::-1]
        center[t] = float(np.dot(w_t, p_t) / np.sum(w_t))
    err = np.abs(closes - center)
    for t in range(n):
        l_idx = min(t, lookback - 1)
        mae[t] = float(np.mean(err[t - l_idx: t + 1]))
    return center, center + mult * mae, center - mult * mae


def nwe_for_session(warmup_closes: Sequence[float], today_closes: Sequence[float]):
    """NWE 100/8/3 para as barras do dia, aquecida com as barras anteriores do MESMO contrato."""
    warm = np.asarray(list(warmup_closes)[-(NWE_LOOKBACK * 2):], dtype=float)
    allc = np.concatenate([warm, np.asarray(today_closes, dtype=float)])
    c, u, l = nwe_series(allc)
    k = len(warm)
    return c[k:], u[k:], l[k:]


# ─────────────────────────────── Fluxo Smart Money (onda) ───────────────────────────────

def compute_flow(bars: List[dict], asset: str) -> List[dict]:
    """
    Força efetiva por barra (Wyckoff 45% + porte 25% + institucional 30%) e onda sem deriva
    (`0,55·(EMA2 − EMA10)` do acumulado + `0,45·` impulso de 3 barras). Mesma fórmula do
    painel 5176 (`gex_live_dealer_engine.py`, passo 2.5). Reinicia a cada sessão.
    Retorna uma lista nova de dicts (não altera a entrada).
    """
    is_win = asset == "WIN"
    tick = ASSET_SPECS[asset]["tick"]
    out = []
    cum = ema_f = ema_s = 0.0
    forces: List[float] = []
    for i, b in enumerate(bars):
        o, h, l, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
        rng = max(h - l, tick)
        bv = float(b.get("buy_vol", 0.0))
        sv = float(b.get("sell_vol", 0.0))
        tv = max(1.0, bv + sv)
        lw = max(0.0, min(o, c) - l)
        uw = max(0.0, h - max(o, c))
        abs_buy = sv * ((c - l) / rng) * (0.80 + 1.40 * (lw / rng))
        abs_sell = bv * ((h - c) / rng) * (0.80 + 1.40 * (uw / rng))
        phi_wyk = round(abs_buy - abs_sell, 0)
        bl = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0))
        sl = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0))
        phi_porte = round(tv * ((bl - sl) / max(0.5, bl + sl)) * 2.2, 0)
        phi_inst = round(
            0.55 * float(b.get("inst_aggr_delta", 0.0))
            + 1.15 * float(b.get("inst_pass_delta", 0.0))
            - 0.85 * float(b.get("ret_delta_bar", 0.0)),
            0,
        )
        force = round(0.45 * phi_wyk + 0.25 * phi_porte + 0.30 * phi_inst, 0)
        forces.append(force)
        f1 = forces[i - 1] if i >= 1 else force
        f2 = forces[i - 2] if i >= 2 else f1
        imp3 = round(0.45 * force + 0.35 * f1 + 0.20 * f2, 0)
        cum += force
        if i == 0:
            ema_f = ema_s = cum
        else:
            ema_f = 0.50 * cum + 0.50 * ema_f
            ema_s = (2.0 / 11.0) * cum + (1.0 - 2.0 / 11.0) * ema_s
        wave = round(0.55 * (ema_f - ema_s) + 0.45 * imp3, 0)
        nb = dict(b)
        nb.update({"wyckoff_abs": phi_wyk, "lot_urgency": phi_porte, "smart_inst": phi_inst,
                   "force": force, "impulse3": imp3, "wave": wave})
        out.append(nb)
    return out


# ─────────────────────────────── Parâmetros ───────────────────────────────

@dataclass(frozen=True)
class SignalParams:
    asset: str
    pivot_left: int = 2          # barras à esquerda que o pivô precisa dominar
    pivot_right: int = 1         # barras à direita para confirmar o pivô (atraso do sinal)
    min_dist: int = 3            # distância mínima F1→F2 (barras)
    max_dist: int = 20           # distância máxima F1→F2 (barras)
    price_tol: float = 50.0      # F2 pode ficar até `tol` acima de F1 (fundo duplo)
    max_ext: float = 400.0       # F2 no máximo `ext` abaixo de F1
    wave_k: float = 0.5          # melhora mínima da onda = k × mediana causal de |onda| no dia
    wall_radius: float = 100.0   # pivô F2 a no máx. `radius` de uma Wall/MidWall
    wall_types: Tuple[str, ...] = ("Wall", "MidWall")
    nwe_filter: str = "none"     # none | extreme | slope_with | slope_against
    entry_start: str = "09:15"
    entry_end: str = "17:00"
    skip_windows: Tuple[Tuple[str, str], ...] = ()
    cooldown: int = 6            # barras mínimas entre sinais da mesma direção

    @staticmethod
    def default(asset: str, **kw) -> "SignalParams":
        base = dict(price_tol=50.0, max_ext=400.0, wall_radius=100.0) if asset == "WIN" else \
            dict(price_tol=1.5, max_ext=10.0, wall_radius=3.0)
        base.update(kw)
        return SignalParams(asset=asset, **base)


@dataclass(frozen=True)
class ExitParams:
    sl_mode: str = "pivot"       # pivot (atrás do F2) | wall (atrás da Wall defendida)
    sl_buf: float = 30.0
    sl_min: float = 100.0
    sl_max: float = 300.0        # se o stop técnico exigir mais, o trade é DESCARTADO (nunca truncado)
    tp_mode: str = "rr"          # rr | next_wall | nwe_center | nwe_band
    rr: float = 1.5
    tp_min: float = 100.0        # alvo mínimo (pts); abaixo disso o trade é descartado
    be_trigger_r: Optional[float] = None   # move stop para entrada+offset ao andar X·R
    be_offset: float = 10.0
    max_bars: int = 24
    eod: str = "17:30"

    @staticmethod
    def default(asset: str, **kw) -> "ExitParams":
        base = dict(sl_buf=30.0, sl_min=100.0, sl_max=300.0, tp_min=100.0, be_offset=10.0) if asset == "WIN" else \
            dict(sl_buf=1.0, sl_min=3.0, sl_max=10.0, tp_min=3.0, be_offset=0.5)
        base.update(kw)
        return ExitParams(**base)


@dataclass
class Signal:
    idx: int            # barra de confirmação (sinal no fechamento dela)
    time: str
    direction: int      # +1 compra (F1→F2), -1 venda (T1→T2)
    pivot_idx: int
    pivot_px: float
    f1_idx: int
    f1_px: float
    wave_f1: float
    wave_f2: float
    wall_px: float
    wall_type: str


@dataclass
class Trade:
    date: str
    asset: str
    signal: Signal
    entry_idx: int
    entry_time: str
    entry_px: float
    stop_px: float
    tp_px: Optional[float]
    exit_idx: Optional[int] = None
    exit_time: Optional[str] = None
    exit_px: Optional[float] = None
    exit_reason: str = "OPEN"
    be_on: bool = False
    pts_net: Optional[float] = None
    brl: Optional[float] = None
    mfe: float = 0.0
    mae: float = 0.0

    def as_row(self) -> dict:
        d = asdict(self)
        s = d.pop("signal")
        d.update({f"sig_{k}": v for k, v in s.items()})
        return d


# ─────────────────────────────── Detecção causal ───────────────────────────────

def _is_pivot_low(bars, j, L, R):
    lj = bars[j]["low"]
    return all(lj <= bars[k]["low"] for k in range(j - L, j)) and all(lj < bars[k]["low"] for k in range(j + 1, j + R + 1))


def _is_pivot_high(bars, j, L, R):
    hj = bars[j]["high"]
    return all(hj >= bars[k]["high"] for k in range(j - L, j)) and all(hj > bars[k]["high"] for k in range(j + 1, j + R + 1))


def _nearest_wall(px: float, walls: Sequence[dict], types: Tuple[str, ...]):
    best = None
    for w in walls:
        if w.get("type") not in types:
            continue
        d = abs(px - float(w["price"]))
        if best is None or d < best[0]:
            best = (d, float(w["price"]), w.get("type"))
    return best


def detect_signals(fbars: List[dict], walls: Sequence[dict], nwe: Tuple[np.ndarray, np.ndarray, np.ndarray],
                   p: SignalParams, upto: Optional[int] = None) -> List[Signal]:
    """
    Varre as barras `0..upto` (inclusive) e devolve os sinais confirmados. Na barra `i`,
    o pivô candidato F2 é `j = i - pivot_right`; F1 é o pivô mais extremo entre
    `j - max_dist` e `j - min_dist`. Só lê barras `<= i`.
    """
    n = len(fbars) if upto is None else min(len(fbars), upto + 1)
    L, R = p.pivot_left, p.pivot_right
    c_arr, u_arr, l_arr = nwe
    sigs: List[Signal] = []
    last = {1: -999, -1: -999}
    abs_waves: List[float] = []
    skip = [(hhmm_to_min(a), hhmm_to_min(b)) for a, b in p.skip_windows]
    t0, t1 = hhmm_to_min(p.entry_start), hhmm_to_min(p.entry_end)
    for i in range(n):
        abs_waves.append(abs(float(fbars[i]["wave"])))
        j = i - R
        if j - L < 0:
            continue
        tm = hhmm_to_min(fbars[i]["time"])
        if tm < t0 or tm > t1 or any(a <= tm <= b for a, b in skip):
            continue
        wave_thr = p.wave_k * float(np.median(abs_waves))
        for d in (1, -1):
            if i - last[d] < p.cooldown:
                continue
            is_piv = _is_pivot_low if d == 1 else _is_pivot_high
            key = "low" if d == 1 else "high"
            if not is_piv(fbars, j, L, R):
                continue
            px2 = float(fbars[j][key])
            # onda no F2: pior valor entre j-1..j (mais conservador)
            w2 = min(fbars[j]["wave"], fbars[j - 1]["wave"]) if d == 1 else max(fbars[j]["wave"], fbars[j - 1]["wave"])
            # F1: pivô mais extremo na janela
            best = None
            for k in range(max(L, j - p.max_dist), j - p.min_dist + 1):
                if not is_piv(fbars, k, L, R):
                    continue
                pk = float(fbars[k][key])
                if best is None or (pk < best[1] if d == 1 else pk > best[1]):
                    best = (k, pk)
            if best is None:
                continue
            k, px1 = best
            w1 = min(fbars[k]["wave"], fbars[k - 1]["wave"]) if d == 1 else max(fbars[k]["wave"], fbars[k - 1]["wave"])
            if d == 1:
                price_ok = (px1 - p.max_ext) <= px2 <= (px1 + p.price_tol)
                wave_ok = (w2 - w1) > wave_thr
            else:
                price_ok = (px1 - p.price_tol) <= px2 <= (px1 + p.max_ext)
                wave_ok = (w1 - w2) > wave_thr
            if not (price_ok and wave_ok):
                continue
            nw = _nearest_wall(px2, walls, p.wall_types)
            if nw is None or nw[0] > p.wall_radius:
                continue
            # filtros NWE (valores da barra i, já fechada)
            if p.nwe_filter != "none":
                ci, ui, li = float(c_arr[i]), float(u_arr[i]), float(l_arr[i])
                if p.nwe_filter == "extreme":
                    ok = px2 <= li + 0.5 * (ci - li) if d == 1 else px2 >= ui - 0.5 * (ui - ci)
                else:
                    slope = ci - float(c_arr[max(0, i - 3)])
                    with_trend = (slope > 0) if d == 1 else (slope < 0)
                    ok = with_trend if p.nwe_filter == "slope_with" else not with_trend
                if not ok:
                    continue
            sigs.append(Signal(idx=i, time=fbars[i]["time"], direction=d, pivot_idx=j, pivot_px=px2,
                               f1_idx=k, f1_px=px1, wave_f1=float(w1), wave_f2=float(w2),
                               wall_px=nw[1], wall_type=str(nw[2])))
            last[d] = i
    return sigs


# ─────────────────────────────── Divergência v2 (definição de 11/11/2026) ───────────────────────────────

@dataclass(frozen=True)
class DivParamsV2:
    """
    Definição revisada com o usuário em 11/11/2026 (caso de referência: WIN 10/11, fundos 11:45 → 15:20):
      - F1 pode ser QUALQUER fundo (topo) anterior do mesmo pregão (sem limite de distância);
      - F2 pode estar qualquer distância abaixo de F1 (sem limite de extensão), ou até `price_tol` acima;
      - F1 = entre esses fundos, o de onda mais negativa (venda: mais positiva) — a mínima do fluxo;
      - Wall: F2 a até `wall_radius` de uma Wall/MidWall ("perto") OU F2 furou o nível mais próximo acima
        dele (venda: abaixo) e um fechamento voltou além do nível em até `reclaim_bars` barras ("furou e voltou");
      - confirmação: "PIVO" (perto: na confirmação do pivô; furou e voltou: no fechamento de retomada) ou
        "FECHA_WALL" (sempre no primeiro fechamento além do nível, até `reclaim_bars` após F2).
    """
    asset: str
    wave_k: float = 0.5
    wall_radius: float = 100.0
    confirm: str = "PIVO"
    nwe_filter: str = "extreme"
    pivot_left: int = 2
    pivot_right: int = 1
    min_dist: int = 3
    price_tol: float = 50.0
    reclaim_bars: int = 12
    wall_types: Tuple[str, ...] = ("Wall", "MidWall")

    @staticmethod
    def default(asset: str, **kw) -> "DivParamsV2":
        base = dict(price_tol=50.0, wall_radius=100.0) if asset == "WIN" else dict(price_tol=1.5, wall_radius=3.0)
        base.update(kw)
        return DivParamsV2(asset=asset, **base)


def detect_divergences_v2(fbars: List[dict], walls: Sequence[dict], nwe, p: DivParamsV2,
                          upto: Optional[int] = None) -> List[Signal]:
    """
    Devolve os sinais na barra em que a divergência passa a valer (`Signal.idx`). Só lê barras `<= i`:
    o pivô F2 = i − pivot_right é avaliado na barra i; a retomada da Wall é procurada barra a barra depois.
    """
    n = len(fbars) if upto is None else min(len(fbars), upto + 1)
    L, R = p.pivot_left, p.pivot_right
    c_arr, u_arr, l_arr = nwe
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in p.wall_types)
    piv = {1: [], -1: []}           # pivôs confirmados: (idx, preço, onda)
    pending: List[dict] = []         # divergências esperando o fechamento além do nível
    sigs: List[Signal] = []
    abs_waves: List[float] = []
    for i in range(n):
        abs_waves.append(abs(float(fbars[i]["wave"])))
        close_i = float(fbars[i]["close"])
        # 1) pendências: fechamento além do nível dentro do prazo
        keep = []
        for pd_ in pending:
            if i > pd_["j"] + p.reclaim_bars:
                continue
            if (close_i > pd_["level"]) if pd_["d"] == 1 else (close_i < pd_["level"]):
                sigs.append(Signal(idx=i, time=fbars[i]["time"], direction=pd_["d"], pivot_idx=pd_["j"],
                                   pivot_px=pd_["px2"], f1_idx=pd_["k"], f1_px=pd_["px1"], wave_f1=pd_["w1"],
                                   wave_f2=pd_["w2"], wall_px=pd_["level"], wall_type=pd_["kind"]))
            else:
                keep.append(pd_)
        pending = keep
        # 2) novo pivô F2 = i − R
        j = i - R
        if j - L < 0:
            continue
        wave_thr = p.wave_k * float(np.median(abs_waves))
        for d in (1, -1):
            is_piv = _is_pivot_low if d == 1 else _is_pivot_high
            if not is_piv(fbars, j, L, R):
                continue
            key = "low" if d == 1 else "high"
            px2 = float(fbars[j][key])
            w2 = min(fbars[j]["wave"], fbars[j - 1]["wave"]) if d == 1 else max(fbars[j]["wave"], fbars[j - 1]["wave"])
            prev = piv[d]
            piv[d] = prev + [(j, px2, float(w2))]
            cands = [(k, pk, wk) for (k, pk, wk) in prev if k <= j - p.min_dist and
                     ((px2 <= pk + p.price_tol) if d == 1 else (px2 >= pk - p.price_tol))]
            if not cands:
                continue
            k, px1, w1 = (min if d == 1 else max)(cands, key=lambda x: x[2])
            if not (((w2 - w1) if d == 1 else (w1 - w2)) > wave_thr):
                continue
            if p.nwe_filter == "extreme":
                ci, ui, li = float(c_arr[i]), float(u_arr[i]), float(l_arr[i])
                if not (px2 <= li + 0.5 * (ci - li) if d == 1 else px2 >= ui - 0.5 * (ui - ci)):
                    continue
            if not levels:
                continue
            near = min(levels, key=lambda lv: abs(lv - px2))
            if abs(near - px2) <= p.wall_radius:
                kind, level = "perto", near
            else:
                beyond = [lv for lv in levels if (lv > px2 if d == 1 else lv < px2)]
                if not beyond:
                    continue
                kind, level = "furou", (min(beyond) if d == 1 else max(beyond))
            rec = dict(d=d, j=j, k=k, px1=px1, px2=px2, w1=w1, w2=float(w2), level=level, kind=kind)
            if kind == "perto" and p.confirm == "PIVO":
                sigs.append(Signal(idx=i, time=fbars[i]["time"], direction=d, pivot_idx=j, pivot_px=px2,
                                   f1_idx=k, f1_px=px1, wave_f1=w1, wave_f2=float(w2), wall_px=level,
                                   wall_type=kind))
            elif (close_i > level) if d == 1 else (close_i < level):
                sigs.append(Signal(idx=i, time=fbars[i]["time"], direction=d, pivot_idx=j, pivot_px=px2,
                                   f1_idx=k, f1_px=px1, wave_f1=w1, wave_f2=float(w2), wall_px=level,
                                   wall_type=kind))
            else:
                pending.append(rec)
    return sigs


# ─────────────────────────────── Divergência v3 (ajuste de 11/11/2026, casos WIN/WDO 11/11) ───────────────────────────────

def detect_divergences_v3(fbars: List[dict], walls: Sequence[dict], nwe, p: DivParamsV2,
                          upto: Optional[int] = None, f1_win: int = 1, rep_tol: Optional[float] = None,
                          reset_f1: bool = True) -> List[Signal]:
    """
    v2 ajustado com o usuário em 11/11/2026 (casos WIN/WDO 10/11 e 11/11):
      - a barra das 09:00 (índice 0) sempre pode ser F1/T1, mesmo sem ser pivô;
      - fluxo no F1 = extremo da onda entre k−f1_win e k+f1_win (o fundo do fluxo pode vir uma barra antes/depois
        do fundo do preço); fluxo no F2 = onda da própria barra do pivô;
      - repetição no mesmo sentido só com rompimento: com o mesmo F1 do sinal anterior, o F2 tem que fazer
        mínima nova (venda: máxima nova); com outro F1, vale até `rep_tol` (padrão `price_tol`) do F2 anterior
        (reteste do fundo). Um sinal por barra e sentido;
      - `reset_f1`: depois de um sinal, o F1 do próximo sinal no mesmo sentido só pode ser o F2 desse sinal ou
        um fundo (topo) posterior — a referência reinicia e não fica presa no F1 de origem.
    Resto igual ao v2: F1 = onda mais extrema entre os fundos/topos anteriores com preço até `price_tol` do F2,
    sem limite de distância; Wall perto ou furou e voltou; enfraquecimento > `wave_k` × mediana de |onda| do dia.
    """
    n = len(fbars) if upto is None else min(len(fbars), upto + 1)
    if n == 0:
        return []
    L, R = p.pivot_left, p.pivot_right
    c_arr, u_arr, l_arr = nwe
    tol_rep = p.price_tol if rep_tol is None else rep_tol
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in p.wall_types)
    piv = {1: [(0, float(fbars[0]["low"]))], -1: [(0, float(fbars[0]["high"]))]}
    pending: List[dict] = []
    sigs: List[Signal] = []
    last = {1: None, -1: None}          # (preço F2, índice F1) do último sinal do sentido
    anchor = {1: 0, -1: 0}              # menor índice permitido para o F1 (reinicia no F2 do último sinal)
    abs_waves: List[float] = []

    def _w1(k, d, i):
        ws = [float(fbars[x]["wave"]) for x in range(max(0, k - f1_win), min(i, k + f1_win) + 1)]
        return min(ws) if d == 1 else max(ws)

    def _emit(i, cands):
        for d in (1, -1):
            cs = [c for c in cands if c["d"] == d]
            if not cs:
                continue
            c = (min if d == 1 else max)(cs, key=lambda x: x["px2"])
            if last[d] is not None:
                lp, lk = last[d]
                tol = 0.0 if c["k"] == lk else tol_rep
                if not (c["px2"] < lp + tol if d == 1 else c["px2"] > lp - tol):
                    continue
                c_px = min(lp, c["px2"]) if d == 1 else max(lp, c["px2"])
            else:
                c_px = c["px2"]
            last[d] = (c_px, c["k"])
            if reset_f1:
                anchor[d] = c["j"]
            sigs.append(Signal(idx=i, time=fbars[i]["time"], direction=d, pivot_idx=c["j"], pivot_px=c["px2"],
                               f1_idx=c["k"], f1_px=c["px1"], wave_f1=c["w1"], wave_f2=c["w2"],
                               wall_px=c["level"], wall_type=c["kind"]))

    for i in range(n):
        abs_waves.append(abs(float(fbars[i]["wave"])))
        close_i = float(fbars[i]["close"])
        ready, keep = [], []
        for pd_ in pending:
            if i > pd_["j"] + p.reclaim_bars:
                continue
            if (close_i > pd_["level"]) if pd_["d"] == 1 else (close_i < pd_["level"]):
                ready.append(pd_)
            else:
                keep.append(pd_)
        pending = keep
        j = i - R
        if j - L >= 0:
            wave_thr = p.wave_k * float(np.median(abs_waves))
            for d in (1, -1):
                is_piv = _is_pivot_low if d == 1 else _is_pivot_high
                if not is_piv(fbars, j, L, R):
                    continue
                key = "low" if d == 1 else "high"
                px2 = float(fbars[j][key])
                w2 = float(fbars[j]["wave"])
                prev = piv[d]
                piv[d] = prev + [(j, px2)]
                cands = [(k, pk, _w1(k, d, i)) for (k, pk) in prev if anchor[d] <= k <= j - p.min_dist and
                         ((px2 <= pk + p.price_tol) if d == 1 else (px2 >= pk - p.price_tol))]
                if not cands:
                    continue
                k, px1, w1 = (min if d == 1 else max)(cands, key=lambda x: x[2])
                if not (((w2 - w1) if d == 1 else (w1 - w2)) > wave_thr):
                    continue
                if p.nwe_filter == "extreme":
                    ci, ui, li = float(c_arr[i]), float(u_arr[i]), float(l_arr[i])
                    if not (px2 <= li + 0.5 * (ci - li) if d == 1 else px2 >= ui - 0.5 * (ui - ci)):
                        continue
                if not levels:
                    continue
                near = min(levels, key=lambda lv: abs(lv - px2))
                if abs(near - px2) <= p.wall_radius:
                    kind, level = "perto", near
                else:
                    beyond = [lv for lv in levels if (lv > px2 if d == 1 else lv < px2)]
                    if not beyond:
                        continue
                    kind, level = "furou", (min(beyond) if d == 1 else max(beyond))
                rec = dict(d=d, j=j, k=k, px1=px1, px2=px2, w1=float(w1), w2=w2, level=level, kind=kind)
                if (kind == "perto" and p.confirm == "PIVO") or ((close_i > level) if d == 1 else (close_i < level)):
                    ready.append(rec)
                else:
                    pending.append(rec)
        _emit(i, ready)
    return sigs


# ─────────────────────────────── Divergência v4 (v3 + marcações do rotulador, 11/11/2026) ───────────────────────────────

def detect_divergences_v4(fbars: List[dict], walls: Sequence[dict], nwe, p: DivParamsV2,
                          upto: Optional[int] = None, f1_win: int = 1, rep_tol: Optional[float] = None,
                          reset_f1: bool = True, rompimento: bool = True, rom_max: Optional[float] = None,
                          zone: Optional[float] = None, furou: bool = True) -> List[Signal]:
    """
    v4 = v3 + ajustes tirados das marcações do rotulador (research/div_v3/LABELS_VS_V3.md, 11/11/2026):
      - `rompimento`: também vale o F2 que NÃO passa do F1 (compra: fundo mais alto; venda: topo mais baixo), até
        `rom_max` além dele, com o fluxo melhorando acima do limiar — tipo "rompimento" (wall_type="rompimento"),
        exige F2 dentro da zona da Wall; não segue a regra de repetição por extremo novo (só um por barra/sentido);
      - `zone`: raio da Wall (padrão p.wall_radius); `furou`: aceita ou não o "furou e voltou";
      - pivôs: use p.pivot_left para afrouxar (1 = só 1 barra à esquerda).
    Regras herdadas do v3 (definição de 11/11/2026, casos WIN/WDO 10/11 e 11/11):
      - a barra das 09:00 (índice 0) sempre pode ser F1/T1, mesmo sem ser pivô;
      - fluxo no F1 = extremo da onda entre k−f1_win e k+f1_win (o fundo do fluxo pode vir uma barra antes/depois
        do fundo do preço); fluxo no F2 = onda da própria barra do pivô;
      - repetição no mesmo sentido só com rompimento: com o mesmo F1 do sinal anterior, o F2 tem que fazer
        mínima nova (venda: máxima nova); com outro F1, vale até `rep_tol` (padrão `price_tol`) do F2 anterior
        (reteste do fundo). Um sinal por barra e sentido;
      - `reset_f1`: depois de um sinal, o F1 do próximo sinal no mesmo sentido só pode ser o F2 desse sinal ou
        um fundo (topo) posterior — a referência reinicia e não fica presa no F1 de origem.
    Resto igual ao v2: F1 = onda mais extrema entre os fundos/topos anteriores com preço até `price_tol` do F2,
    sem limite de distância; Wall perto ou furou e voltou; enfraquecimento > `wave_k` × mediana de |onda| do dia.
    """
    n = len(fbars) if upto is None else min(len(fbars), upto + 1)
    if n == 0:
        return []
    L, R = p.pivot_left, p.pivot_right
    c_arr, u_arr, l_arr = nwe
    tol_rep = p.price_tol if rep_tol is None else rep_tol
    radius = p.wall_radius if zone is None else zone
    rmax = (800.0 if p.asset == "WIN" else 16.0) if rom_max is None else rom_max
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in p.wall_types)
    piv = {1: [(0, float(fbars[0]["low"]))], -1: [(0, float(fbars[0]["high"]))]}
    pending: List[dict] = []
    sigs: List[Signal] = []
    last = {1: None, -1: None}          # (preço F2, índice F1) do último sinal do sentido
    anchor = {1: 0, -1: 0}              # menor índice permitido para o F1 (reinicia no F2 do último sinal)
    abs_waves: List[float] = []

    def _w1(k, d, i):
        ws = [float(fbars[x]["wave"]) for x in range(max(0, k - f1_win), min(i, k + f1_win) + 1)]
        return min(ws) if d == 1 else max(ws)

    def _emit(i, cands):
        for d in (1, -1):
            cs = [c for c in cands if c["d"] == d]
            if not cs:
                continue
            rom = [c for c in cs if c["kind"] == "rompimento"]
            cs = [c for c in cs if c["kind"] != "rompimento"]
            if not cs:
                c = rom[0]
                if reset_f1:
                    anchor[d] = c["j"]
                sigs.append(Signal(idx=i, time=fbars[i]["time"], direction=d, pivot_idx=c["j"], pivot_px=c["px2"],
                                   f1_idx=c["k"], f1_px=c["px1"], wave_f1=c["w1"], wave_f2=c["w2"],
                                   wall_px=c["level"], wall_type=c["kind"]))
                continue
            c = (min if d == 1 else max)(cs, key=lambda x: x["px2"])
            if last[d] is not None:
                lp, lk = last[d]
                tol = 0.0 if c["k"] == lk else tol_rep
                if not (c["px2"] < lp + tol if d == 1 else c["px2"] > lp - tol):
                    continue
                c_px = min(lp, c["px2"]) if d == 1 else max(lp, c["px2"])
            else:
                c_px = c["px2"]
            last[d] = (c_px, c["k"])
            if reset_f1:
                anchor[d] = c["j"]
            sigs.append(Signal(idx=i, time=fbars[i]["time"], direction=d, pivot_idx=c["j"], pivot_px=c["px2"],
                               f1_idx=c["k"], f1_px=c["px1"], wave_f1=c["w1"], wave_f2=c["w2"],
                               wall_px=c["level"], wall_type=c["kind"]))

    for i in range(n):
        abs_waves.append(abs(float(fbars[i]["wave"])))
        close_i = float(fbars[i]["close"])
        ready, keep = [], []
        for pd_ in pending:
            if i > pd_["j"] + p.reclaim_bars:
                continue
            if (close_i > pd_["level"]) if pd_["d"] == 1 else (close_i < pd_["level"]):
                ready.append(pd_)
            else:
                keep.append(pd_)
        pending = keep
        j = i - R
        if j - L >= 0:
            wave_thr = p.wave_k * float(np.median(abs_waves))
            for d in (1, -1):
                is_piv = _is_pivot_low if d == 1 else _is_pivot_high
                if not is_piv(fbars, j, L, R):
                    continue
                key = "low" if d == 1 else "high"
                px2 = float(fbars[j][key])
                w2 = float(fbars[j]["wave"])
                prev = piv[d]
                piv[d] = prev + [(j, px2)]
                elig = [(k, pk) for (k, pk) in prev if anchor[d] <= k <= j - p.min_dist]
                cands = [(k, pk, _w1(k, d, i)) for (k, pk) in elig
                         if ((px2 <= pk + p.price_tol) if d == 1 else (px2 >= pk - p.price_tol))]
                is_rom = False
                if not cands and rompimento:
                    cands = [(k, pk, _w1(k, d, i)) for (k, pk) in elig
                             if (0 < d * (px2 - pk) - p.price_tol <= rmax)]
                    is_rom = bool(cands)
                if not cands:
                    continue
                k, px1, w1 = (min if d == 1 else max)(cands, key=lambda x: x[2])
                if not (((w2 - w1) if d == 1 else (w1 - w2)) > wave_thr):
                    continue
                if is_rom:
                    if not levels:
                        continue
                    near = min(levels, key=lambda lv: abs(lv - px2))
                    if abs(near - px2) <= radius:
                        ready.append(dict(d=d, j=j, k=k, px1=px1, px2=px2, w1=float(w1), w2=w2, level=near,
                                          kind="rompimento"))
                    continue
                if p.nwe_filter == "extreme":
                    ci, ui, li = float(c_arr[i]), float(u_arr[i]), float(l_arr[i])
                    if not (px2 <= li + 0.5 * (ci - li) if d == 1 else px2 >= ui - 0.5 * (ui - ci)):
                        continue
                if not levels:
                    continue
                near = min(levels, key=lambda lv: abs(lv - px2))
                if abs(near - px2) <= radius:
                    kind, level = "perto", near
                elif not furou:
                    continue
                else:
                    beyond = [lv for lv in levels if (lv > px2 if d == 1 else lv < px2)]
                    if not beyond:
                        continue
                    kind, level = "furou", (min(beyond) if d == 1 else max(beyond))
                rec = dict(d=d, j=j, k=k, px1=px1, px2=px2, w1=float(w1), w2=w2, level=level, kind=kind)
                if (kind == "perto" and p.confirm == "PIVO") or ((close_i > level) if d == 1 else (close_i < level)):
                    ready.append(rec)
                else:
                    pending.append(rec)
        _emit(i, ready)
    return sigs


# ─────────────────────────────── Spring / Upthrust na Wall (M1) ───────────────────────────────

@dataclass(frozen=True)
class SpringParams:
    asset: str
    n_back: int = 3              # violinada em até N barras (incluindo a de retomada)
    pierce_min: float = 15.0     # quanto o preço furou a Wall (mín.)
    pierce_max: float = 120.0    # furo maior que isso = rompimento real, não violinada
    reclaim_buf: float = 0.0     # fechamento da barra i precisa voltar `buf` para dentro
    wall_types: Tuple[str, ...] = ("Wall", "MidWall")
    flow_mode: str = "none"      # none | force | absorb | wave_up | anti_force (placebo)
    nwe_filter: str = "none"     # none | extreme | slope_with | slope_against
    entry_start: str = "09:15"
    entry_end: str = "17:00"
    skip_windows: Tuple[Tuple[str, str], ...] = ()
    cooldown: int = 10

    @staticmethod
    def default(asset: str, **kw) -> "SpringParams":
        base = dict(pierce_min=15.0, pierce_max=120.0) if asset == "WIN" else dict(pierce_min=0.5, pierce_max=4.0)
        base.update(kw)
        return SpringParams(asset=asset, **base)


def detect_springs(fbars: List[dict], walls: Sequence[dict], nwe, p: SpringParams,
                   upto: Optional[int] = None) -> List[Signal]:
    """
    Compra (spring): a barra antes da janela fechou ACIMA da Wall, alguma barra da janela furou a Wall
    entre `pierce_min` e `pierce_max`, e a barra `i` fecha de volta acima dela. Venda (upthrust) simétrica.
    Só lê barras `<= i`.
    """
    n = len(fbars) if upto is None else min(len(fbars), upto + 1)
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in p.wall_types)
    wtype = {float(w["price"]): w.get("type") for w in walls if w.get("type") in p.wall_types}
    c_arr, u_arr, l_arr = nwe
    t0, t1 = hhmm_to_min(p.entry_start), hhmm_to_min(p.entry_end)
    skip = [(hhmm_to_min(a), hhmm_to_min(b)) for a, b in p.skip_windows]
    last = {1: -999, -1: -999}
    sigs: List[Signal] = []
    for i in range(p.n_back, n):
        tm = hhmm_to_min(fbars[i]["time"])
        if tm < t0 or tm > t1 or any(a <= tm <= b for a, b in skip):
            continue
        win = range(i - p.n_back + 1, i + 1)
        pre = fbars[i - p.n_back]
        ci = float(fbars[i]["close"])
        for d in (1, -1):
            if i - last[d] < p.cooldown:
                continue
            if d == 1:
                k_ext = min(win, key=lambda k: fbars[k]["low"])
                ext = float(fbars[k_ext]["low"])
                cands = [w for w in levels if float(pre["close"]) > w and ext < w and ci > w + p.reclaim_buf]
                lvl = max(cands) if cands else None
                pierce = (lvl - ext) if lvl is not None else None
            else:
                k_ext = max(win, key=lambda k: fbars[k]["high"])
                ext = float(fbars[k_ext]["high"])
                cands = [w for w in levels if float(pre["close"]) < w and ext > w and ci < w - p.reclaim_buf]
                lvl = min(cands) if cands else None
                pierce = (ext - lvl) if lvl is not None else None
            if lvl is None or not (p.pierce_min <= pierce <= p.pierce_max):
                continue
            b = fbars[i]
            if p.flow_mode != "none":
                if p.flow_mode == "force":
                    ok = b["force"] * d > 0
                elif p.flow_mode == "anti_force":
                    ok = b["force"] * d < 0
                elif p.flow_mode == "absorb":
                    ok = sum(fbars[k]["wyckoff_abs"] for k in win) * d > 0
                else:  # wave_up
                    ok = (b["wave"] - fbars[i - 1]["wave"]) * d > 0
                if not ok:
                    continue
            if p.nwe_filter != "none":
                cc, uu, ll = float(c_arr[i]), float(u_arr[i]), float(l_arr[i])
                if p.nwe_filter == "extreme":
                    ok = ext <= ll + 0.5 * (cc - ll) if d == 1 else ext >= uu - 0.5 * (uu - cc)
                else:
                    slope = cc - float(c_arr[max(0, i - 3)])
                    wt = (slope > 0) if d == 1 else (slope < 0)
                    ok = wt if p.nwe_filter == "slope_with" else not wt
                if not ok:
                    continue
            sigs.append(Signal(idx=i, time=b["time"], direction=d, pivot_idx=k_ext, pivot_px=ext,
                               f1_idx=k_ext, f1_px=ext, wave_f1=float(fbars[k_ext]["wave"]),
                               wave_f2=float(b["wave"]), wall_px=lvl, wall_type=str(wtype.get(lvl))))
            last[d] = i
    return sigs


# ─────────────────────────────── Simulação de saída ───────────────────────────────

def _next_wall_target(entry: float, d: int, walls, min_dist: float):
    cands = [float(w["price"]) for w in walls if w.get("type") in ("Wall", "MidWall")]
    cands = [x for x in cands if (x - entry) * d >= min_dist]
    if not cands:
        return None
    return min(cands) if d == 1 else max(cands)


def build_trade(date: str, asset: str, sig: Signal, fbars: List[dict], walls, nwe, e: ExitParams) -> Optional[Trade]:
    """Cria o trade (entrada na abertura de idx+1). Retorna None se o risco/alvo não passar nas regras."""
    spec = ASSET_SPECS[asset]
    tick = spec["tick"]
    ei = sig.idx + 1
    if ei >= len(fbars):
        return None  # ao vivo: entrada pendente para a próxima barra
    d = sig.direction
    ep = float(fbars[ei]["open"])
    if e.sl_mode == "wall":
        raw_sl = sig.wall_px - d * e.sl_buf
        raw_sl = min(raw_sl, sig.pivot_px - d * tick) if d == 1 else max(raw_sl, sig.pivot_px - d * tick)
    else:
        raw_sl = sig.pivot_px - d * e.sl_buf
    risk = (ep - raw_sl) * d
    if risk < e.sl_min:
        raw_sl = ep - d * e.sl_min
        risk = e.sl_min
    if risk > e.sl_max:
        return None
    sl = round_tick(raw_sl, tick)
    if e.tp_mode == "rr":
        tp = round_tick(ep + d * e.rr * risk, tick)
    elif e.tp_mode == "next_wall":
        w = _next_wall_target(ep, d, walls, e.tp_min)
        if w is None:
            return None
        tp = round_tick(w - d * tick, tick)
    else:
        tp = None  # dinâmico (NWE), calculado barra a barra
        ref = _nwe_tp(nwe, sig.idx, d, e.tp_mode)
        if (ref - ep) * d < e.tp_min:
            return None
    return Trade(date=date, asset=asset, signal=sig, entry_idx=ei, entry_time=fbars[ei]["time"],
                 entry_px=ep, stop_px=sl, tp_px=tp)


def _nwe_tp(nwe, ref_idx: int, d: int, mode: str) -> float:
    c, u, l = nwe
    if mode == "nwe_center":
        return float(c[ref_idx])
    return float(u[ref_idx]) if d == 1 else float(l[ref_idx])


def simulate_trade(tr: Trade, fbars: List[dict], nwe, e: ExitParams, upto: Optional[int] = None) -> Trade:
    """
    Avança o trade barra a barra até `upto` (inclusive). Regras alinhadas ao MT5:
    stop antes do alvo na mesma barra; gap além do stop/alvo preenche na abertura;
    BE só é aplicado se a abertura da barra seguinte estiver além do novo stop.
    """
    spec = ASSET_SPECS[tr.asset]
    tick = spec["tick"]
    d = tr.signal.direction
    ep = tr.entry_px
    risk = (ep - tr.stop_px) * d
    n = len(fbars) if upto is None else min(len(fbars), upto + 1)
    eod = hhmm_to_min(e.eod)
    sl = tr.stop_px
    pending_be = False
    for k in range(tr.entry_idx, n):
        b = fbars[k]
        o, h, l, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
        if pending_be:
            cand = ep + d * e.be_offset
            if (o - cand) * d > 0:
                sl = round_tick(cand, tick)
                tr.be_on = True
            pending_be = False
        if hhmm_to_min(b["time"]) >= eod:
            _close(tr, k, b["time"], o, "EOD", spec)
            return tr
        tp = tr.tp_px if e.tp_mode in ("rr", "next_wall") else round_tick(_nwe_tp(nwe, k - 1, d, e.tp_mode), tick)
        # stop primeiro
        if (d == 1 and l <= sl) or (d == -1 and h >= sl):
            fill = o if (o - sl) * d <= 0 else sl
            _close(tr, k, b["time"], fill - d * spec["stop_slip_pts"], "BE" if tr.be_on else "SL", spec)
            return tr
        if (tp - ep) * d > 0 and ((d == 1 and h >= tp) or (d == -1 and l <= tp)):
            fill = o if (o - tp) * d >= 0 else tp
            _close(tr, k, b["time"], fill, "TP", spec)
            return tr
        fav = (h - ep) * d if d == 1 else (ep - l)
        adv = (ep - l) if d == 1 else (h - ep)
        tr.mfe = max(tr.mfe, fav)
        tr.mae = max(tr.mae, adv)
        if e.be_trigger_r is not None and not tr.be_on and tr.mfe >= e.be_trigger_r * risk:
            pending_be = True
        if k - tr.entry_idx + 1 >= e.max_bars:
            _close(tr, k, b["time"], c, "TEMPO", spec)
            return tr
    tr.stop_px = sl
    if upto is None and tr.exit_reason == "OPEN" and n > 0:
        _close(tr, n - 1, fbars[n - 1]["time"], float(fbars[n - 1]["close"]), "FIM_DADOS", spec)
    return tr


def _close(tr: Trade, k: int, t: str, px: float, reason: str, spec: dict) -> None:
    d = tr.signal.direction
    tr.exit_idx, tr.exit_time, tr.exit_px, tr.exit_reason = k, t, round(px, 2), reason
    tr.pts_net = round((px - tr.entry_px) * d - spec["cost_pts"], 2)
    tr.brl = round(tr.pts_net * spec["brl_per_pt"], 2)


def run_session(date: str, asset: str, bars: List[dict], walls, nwe, sp, ep: ExitParams,
                upto: Optional[int] = None, fbars: Optional[List[dict]] = None) -> Tuple[List[Signal], List[Trade]]:
    """
    Ponto de entrada único (BT e ao vivo). `upto` = índice da última barra FECHADA disponível.
    Ao vivo: chamar com as barras fechadas do dia; trades sem saída ficam com exit_reason 'OPEN'.
    """
    if fbars is None:
        fbars = compute_flow(bars, asset)
    detector = detect_springs if isinstance(sp, SpringParams) else detect_signals
    sigs = detector(fbars, walls, nwe, sp, upto=upto)
    view = fbars if upto is None else fbars[: upto + 1]
    trades = []
    for s in sigs:
        tr = build_trade(date, asset, s, view, walls, nwe, ep)
        if tr is None:
            continue
        trades.append(simulate_trade(tr, view, nwe, ep, upto=None if upto is None else upto))
    return sigs, trades
