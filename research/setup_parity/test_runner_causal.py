"""
Causalidade / paridade ao vivo × BT do runner único (`core/setups_runner.py`).

Para cada dia sorteado, roda o BT do dia inteiro e depois o "ao vivo" com corte T a cada `step` minutos
(só barras fechadas até T, aquecimento de 7 dias, igual ao motor). Exige:
  1. Todo trade visto em T existe no BT com mesma estratégia, horário, direção e preço de entrada.
  2. Todo trade FECHADO em T tem a mesma saída (preço e horário) do BT.
  3. Todo trade do BT cuja entrada ocorreu até T − 15 min já aparece em T (ordens limite valem até 2 barras).
Uso: python -m research.setup_parity.test_runner_causal [n_dias] [step_min]
"""
from __future__ import annotations

import os
import random
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.setups_runner import run_setups  # noqa: E402
from research.flow_window_asg.flow_filters import load_flow_tables  # noqa: E402

WARMUP = 7


def flat(res):
    return [dict(t, sid=sid) for sid, v in res.items() for t in v]


def k_in(t):
    return (t["sid"], t["time"], t["direction"], t["entry_price"])


def check_day(day, ft, step):
    errs = []
    full = {k_in(t): t for t in flat(run_setups(day, day, flow_tables=ft, warmup_days=WARMUP))}
    for m in range(9 * 60 + 10, 18 * 60 + 1, step):
        T = pd.Timestamp(day) + pd.Timedelta(minutes=m)
        live = flat(run_setups(day, day, flow_tables=ft, warmup_days=WARMUP, cutoff=T))
        lk = {k_in(t) for t in live}
        lk_noprice = {k[:3] for k in lk}
        full_noprice = {k[:3]: v for k, v in full.items()}
        for t in live:
            # trade aberto: o preço médio pode mudar se a 2ª perna (SmartGrid) ainda vai encher
            b = full.get(k_in(t)) if t["status"] == "FECHADA" else full_noprice.get(k_in(t)[:3])
            if b is None:
                errs.append(f"{day} {T:%H:%M}: {k_in(t)} aparece ao vivo mas não no BT")
            elif t["status"] == "FECHADA" and (t["exit_price"], t["exit_time"]) != (b["exit_price"], b["exit_time"]):
                errs.append(f"{day} {T:%H:%M}: {k_in(t)} saída ao vivo {(t['exit_time'], t['exit_price'])} "
                            f"≠ BT {(b['exit_time'], b['exit_price'])}")
        for k, b in full.items():
            hh, mm = map(int, b["time"].split(":"))
            if hh * 60 + mm + 15 <= m and k not in lk and k[:3] not in lk_noprice:
                eh, em = map(int, b["exit_time"].split(":"))
                kind = "ABERTO_OMITIDO" if eh * 60 + em + 5 > m else "FECHADO_AUSENTE"
                errs.append(f"{day} {T:%H:%M}: [{kind}] trade do BT {k} (saída {b['exit_time']}) não aparece ao vivo")
    return errs, len(full)


def main(n_days=6, step=15, seed=11):
    ft, covered = load_flow_tables("min")
    days = [d for d in covered if "2026-01-15" <= d <= "2026-11-06"]
    random.Random(seed).shuffle(days)
    all_errs, n_tr = [], 0
    for d in sorted(days[:n_days]):
        e, n = check_day(d, ft, step)
        n_tr += n
        all_errs += e
        print(f"{d}: {n} trades no BT · {'OK' if not e else f'{len(e)} falhas'}", flush=True)
    print(f"TOTAL: {n_days} dias, {n_tr} trades, {'paridade 100%' if not all_errs else f'{len(all_errs)} falhas'}")
    import collections, re
    kinds = collections.Counter()
    for e in all_errs:
        m_ = re.search(r"\[(\w+)\] trade do BT \('(\w+)'", e)
        kinds[(m_.group(1), m_.group(2)) if m_ else ("OUTRO", e.split(":")[2][:30])] += 1
    for k, v in sorted(kinds.items()):
        print(f"   {k}: {v}")
    for e in [e for e in all_errs if "ABERTO_OMITIDO" not in e][:15]:
        print("  ", e)
    return not all_errs


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    s = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    sys.exit(0 if main(n, s) else 1)
