"""
Teste de paridade ao vivo × BT para `core/div_wall_signal.py`.

Simula o ao vivo de forma estrita: para cada barra t do dia, recalcula TUDO a partir de
`bars[:t+1]` (fluxo, sinais e trades), exatamente como o motor faria a cada fechamento de M5,
e compara com a execução em lote (BT) do dia inteiro:
  1. Sinais com idx <= t devem ser idênticos (nenhum sinal aparece/some/repinta).
  2. Trades já encerrados até t devem ter saída idêntica (preço, motivo, barra).
  3. Trades abertos em t devem estar abertos também no BT nesse instante.
Qualquer diferença = leitura do futuro. Uso: python -m research.div_wall.parity_test [WIN|WDO] [n_dias] [M5|M1]
"""
from __future__ import annotations

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.div_wall_signal import ExitParams, SignalParams, SpringParams, run_session  # noqa: E402
from research.div_wall.data import load_asset  # noqa: E402


def sig_key(s):
    return (s.idx, s.direction, s.pivot_idx, s.f1_idx, round(s.wall_px, 2))


def check_day(date, asset, bars, walls, nwe, sp, ep):
    errors = []
    b_sigs, b_trades = run_session(date, asset, bars, walls, nwe, sp, ep)
    b_by_sig = {sig_key(t.signal): t for t in b_trades}
    for t in range(len(bars)):
        nwe_t = tuple(x[: t + 1] for x in nwe)
        l_sigs, l_trades = run_session(date, asset, bars[: t + 1], walls, nwe_t, sp, ep, upto=t)
        exp = [sig_key(s) for s in b_sigs if s.idx <= t]
        got = [sig_key(s) for s in l_sigs]
        if exp != got:
            errors.append(f"{date} t={t}: sinais BT {exp} != ao vivo {got}")
            break
        for lt in l_trades:
            bt = b_by_sig.get(sig_key(lt.signal))
            if bt is None:
                errors.append(f"{date} t={t}: trade ao vivo {sig_key(lt.signal)} não existe no BT")
                continue
            if lt.exit_reason != "OPEN":
                if (lt.exit_idx, lt.exit_px, lt.exit_reason) != (bt.exit_idx, bt.exit_px, bt.exit_reason):
                    errors.append(f"{date} t={t}: saída ao vivo {(lt.exit_idx, lt.exit_px, lt.exit_reason)} "
                                  f"!= BT {(bt.exit_idx, bt.exit_px, bt.exit_reason)}")
            elif bt.exit_idx is not None and bt.exit_idx <= t:
                errors.append(f"{date} t={t}: aberto ao vivo mas BT já saiu em {bt.exit_idx}")
        # trades do BT com entrada <= t devem existir ao vivo
        live_keys = {sig_key(x.signal) for x in l_trades}
        for bt in b_trades:
            if bt.entry_idx <= t and sig_key(bt.signal) not in live_keys:
                errors.append(f"{date} t={t}: trade do BT {sig_key(bt.signal)} ausente ao vivo")
        if errors:
            break
    return errors, len(b_sigs), len(b_trades)


def m1_configs(asset):
    win = asset == "WIN"
    ex = dict(sl_buf=15.0, sl_min=40.0, sl_max=150.0, tp_min=40.0) if win else dict(sl_buf=0.5, sl_min=1.5, sl_max=5.0, tp_min=1.5)
    base = dict(max_ext=200.0, price_tol=25.0, wall_radius=40.0) if win else dict(max_ext=6.0, price_tol=1.0, wall_radius=1.5)
    return [
        (SignalParams.default(asset, wave_k=1.0, cooldown=10, **base), ExitParams.default(asset, max_bars=30, **ex)),
        (SignalParams.default(asset, wave_k=0.5, pivot_right=2, nwe_filter="extreme", **base),
         ExitParams.default(asset, sl_mode="wall", tp_mode="nwe_band", be_trigger_r=1.0, max_bars=60, **ex)),
        (SpringParams.default(asset, flow_mode="force"), ExitParams.default(asset, tp_mode="next_wall", **ex)),
        (SpringParams.default(asset, n_back=5, flow_mode="absorb", nwe_filter="slope_with"),
         ExitParams.default(asset, sl_mode="wall", tp_mode="nwe_center", be_trigger_r=1.0, **ex)),
    ]


def main(asset="WIN", n_days=25, seed=7, tf="M5"):
    data = load_asset(asset, tf)
    days = sorted(data)
    random.Random(seed).shuffle(days)
    configs = m1_configs(asset) if tf == "M1" else [
        (SignalParams.default(asset), ExitParams.default(asset)),
        (SignalParams.default(asset, wave_k=0.25, pivot_right=2, nwe_filter="extreme"),
         ExitParams.default(asset, sl_mode="wall", tp_mode="nwe_band", be_trigger_r=1.0)),
        (SignalParams.default(asset, wave_k=0.25, nwe_filter="slope_with"),
         ExitParams.default(asset, tp_mode="next_wall", be_trigger_r=1.0)),
        (SignalParams.default(asset, wave_k=0.25),
         ExitParams.default(asset, tp_mode="nwe_center")),
    ]
    tot_err, tot_sig, tot_tr = [], 0, 0
    for sp, ep in configs:
        for d in days[:n_days]:
            bars, walls, nwe = data[d]
            errs, ns, nt = check_day(d, asset, bars, walls, nwe, sp, ep)
            tot_err += errs
            tot_sig += ns
            tot_tr += nt
    print(f"{asset} {tf}: {len(configs)} configs × {n_days} dias · {tot_sig} sinais · {tot_tr} trades · "
          f"{'OK — paridade 100%' if not tot_err else f'{len(tot_err)} FALHAS'}")
    for e in tot_err[:10]:
        print("  ", e)
    return not tot_err


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "WIN"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    tf = sys.argv[3] if len(sys.argv) > 3 else "M5"
    sys.exit(0 if main(a, n, tf=tf) else 1)
