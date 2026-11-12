# -*- coding: utf-8 -*-
"""
Sensibilidade da regra ESP_DIV_V21_WIN ao formato de contabilização do fluxo (pedido de 12/11/2026).
A regra fica CONGELADA (motor v2.1, gatilho (a)+(b), filtros, saída SL200/sem alvo/12 barras/BE 180→20, um por vez);
só muda a curva "Fluxo Smart Money" que o motor lê. O limiar de onda do v2.1 é relativo (0,15 × mediana |onda|),
então a escala da curva não importa, só a forma.

Fórmulas:
  5176 (core.compute_flow): força = 0,45·Wyckoff + 0,25·porte + 0,30·inst ; inst = 0,55·agr + 1,15·pas − 0,85·var
                            onda = 0,55·(EMA_rápida − EMA_lenta)(acumulado) + 0,45·impulso3 ; α = 0,5 e 2/11
  5174 V5b (flow_filters._session_features): força = 0,12·W + 0,18·P + 0,70·inst ; inst = 0,90·agr + 0,75·pas − 0,25·var
                            onda = 0,92·(EMA4 − EMA20) + 0,08·impulso3 ; α = 2/5 e 2/21
Uso: python fluxo_var.py → results/fluxo_var.csv
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import bt, modulo as M, robust as R
from core.div_wall_signal import compute_flow as core_flow

BASE = dict(w=(0.45, 0.25, 0.30), inst=(0.55, 1.15, -0.85), af=0.50, as_=2.0 / 11.0, mix=(0.55, 0.45), rnd=True)
V5B = dict(w=(0.12, 0.18, 0.70), inst=(0.90, 0.75, -0.25), af=2.0 / 5.0, as_=2.0 / 21.0, mix=(0.92, 0.08), rnd=False)


def make_flow(p):
    W, I, af, as_, (mt, mi), rnd = p["w"], p["inst"], p["af"], p["as_"], p["mix"], p["rnd"]
    r = (lambda x: round(x, 0)) if rnd else (lambda x: x)

    def flow(bars, asset):
        is_win = asset == "WIN"
        tick = bt.X[asset]["tick"]
        out, forces = [], []
        cum = ef = es = 0.0
        for i, b in enumerate(bars):
            o, h, l, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
            rng = max(h - l, tick)
            bv, sv = float(b.get("buy_vol", 0.0)), float(b.get("sell_vol", 0.0))
            tv = max(1.0, bv + sv)
            lw, uw = max(0.0, min(o, c) - l), max(0.0, h - max(o, c))
            wyk = r(sv * ((c - l) / rng) * (0.80 + 1.40 * (lw / rng)) - bv * ((h - c) / rng) * (0.80 + 1.40 * (uw / rng)))
            bl = float(b.get("avg_buy_lot", 3.1 if is_win else 4.0))
            sl = float(b.get("avg_sell_lot", 3.1 if is_win else 4.0))
            porte = r(tv * ((bl - sl) / max(0.5, bl + sl)) * 2.2)
            inst = r(I[0] * float(b.get("inst_aggr_delta", 0.0)) + I[1] * float(b.get("inst_pass_delta", 0.0))
                     + I[2] * float(b.get("ret_delta_bar", 0.0)))
            force = r(W[0] * wyk + W[1] * porte + W[2] * inst)
            forces.append(force)
            f1 = forces[i - 1] if i >= 1 else force
            f2 = forces[i - 2] if i >= 2 else f1
            imp3 = r(0.45 * force + 0.35 * f1 + 0.20 * f2)
            cum += force
            if i == 0:
                ef = es = cum
            else:
                ef = af * cum + (1 - af) * ef
                es = as_ * cum + (1 - as_) * es
            wave = r(mt * (ef - es) + mi * imp3)
            nb = dict(b)
            nb.update(wyckoff_abs=wyk, lot_urgency=porte, smart_inst=inst, force=force, impulse3=imp3, wave=wave)
            out.append(nb)
        return out
    return flow


def renorm(w, i, delta):
    """Soma delta ao motor i e redistribui nos outros dois na proporção deles (soma fica 1)."""
    w = list(w)
    new = min(max(w[i] + delta, 0.0), 1.0)
    rest = sum(w) - w[i]
    others = [k for k in range(3) if k != i]
    for k in others:
        w[k] = w[k] / rest * (1.0 - new) if rest > 0 else (1.0 - new) / 2
    w[i] = new
    return tuple(round(x, 4) for x in w)


def variants():
    V = [("5176 (base)", BASE), ("5174 V5b completo", V5B),
         ("pesos V5b + memória 5176", dict(BASE, w=V5B["w"], inst=V5B["inst"])),
         ("pesos 5176 + memória V5b", dict(V5B, w=BASE["w"], inst=BASE["inst"], rnd=True)),
         ("só institucional V5b na força 5176", dict(BASE, inst=V5B["inst"]))]
    names = ("Wyckoff", "porte", "institucional")
    for i in range(3):
        for dlt in (-0.10, -0.05, 0.05, 0.10):
            V.append((f"5176 · {names[i]} {dlt:+.2f}", dict(BASE, w=renorm(BASE["w"], i, dlt))))
    for i, nm in enumerate(("agressor", "passivo", "varejo")):
        for f in (0.8, 1.2):
            inst = list(BASE["inst"]); inst[i] = round(inst[i] * f, 4)
            V.append((f"5176 · inst {nm} ×{f:g}", dict(BASE, inst=tuple(inst))))
    for lab, kw in (("EMA rápida α 0,4", dict(af=0.4)), ("EMA rápida α 0,6", dict(af=0.6)),
                    ("EMA lenta 8", dict(as_=2 / 9)), ("EMA lenta 12", dict(as_=2 / 13)),
                    ("mistura 0,45/0,55", dict(mix=(0.45, 0.55))), ("mistura 0,65/0,35", dict(mix=(0.65, 0.35)))):
        V.append((f"5176 · {lab}", dict(BASE, **kw)))
    for i in range(3):
        for dlt in (-0.05, 0.05):
            V.append((f"V5b · {names[i]} {dlt:+.2f}", dict(V5B, w=renorm(V5B["w"], i, dlt))))
    return V


def main():
    # 1) a fórmula parametrizada reproduz core.compute_flow com os pesos do 5176
    from research.div_wall.data import load_asset
    data = load_asset("WIN", "M5")
    f0 = make_flow(BASE)
    for d in sorted(data)[:30]:
        a, b = core_flow(data[d][0], "WIN"), f0(data[d][0], "WIN")
        assert all(x["wave"] == y["wave"] for x, y in zip(a, b)), d
    print("fórmula parametrizada == core.compute_flow (30 pregões)")
    DS = bt.market("WIN")
    rows = []
    orig = M.compute_flow
    try:
        for name, p in variants():
            M.compute_flow = make_flow(p)
            S = R.signals_mode("ab")
            T = R.run_exit(bt.simulate("WIN", S, DS, exits=()), DS)
            s, q = R.evaluate(T)
            rows.append(dict(variante=name, w=p["w"], inst=p["inst"], af=round(p["af"], 3), as_=round(p["as_"], 3),
                             mix=p["mix"], sinais=len(S), **s))
            print(f"{name:40s} {s['ops']:4d} tr  PF {s['pf']:.2f}  R$ {s['net']:6.0f}  DD {s['dd']:5.0f}  "
                  f"Ret/DD {s['rdd']:5.2f}  jan–jul {s['rdd_is']:5.2f}  ago–nov {s['rdd_oos']:5.2f}  meses {s['meses']}",
                  flush=True)
    finally:
        M.compute_flow = orig
    F = pd.DataFrame(rows)
    F.to_csv(os.path.join(HERE, "results", "fluxo_var.csv"), index=False)
    small = F[F.variante.str.startswith("5176 ·")]
    print(f"\nvariações pequenas em torno do 5176: n={len(small)} · Ret/DD mediana {small.rdd.median():.2f} · "
          f"mín {small.rdd.min():.2f} · máx {small.rdd.max():.2f} · ≥10: {(small.rdd >= 10).sum()} · PF>1: {(small.pf > 1).sum()}")


if __name__ == "__main__":
    main()
