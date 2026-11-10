import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import research.optimizers.wdo_mt5_sim as wdo_sim

print("=" * 105)
print("  AVALIAÇÃO DE TODOS OS 16 SLOTS NATIVOS DE WDO (Jumba_WDO_GEX_NWE_Core)")
print("=" * 105)

for s in range(1, 17):
    tr = wdo_sim.simulate_single_wdo_slot(s)
    m = wdo_sim.calc_wdo_stats(tr)
    n = wdo_sim.WDO_SLOT_NAMES.get(s, "")
    print(f"Slot {s:02d} ({n[:35]:<35}): {m['trades']:>3d} tr | WR {m['wr']:>4.1f}% | PF {m['pf']:>4.2f} | Net R$ {m['net_brl']:>8.0f} | DD R$ {m['max_dd_brl']:>6.0f} | Ret/DD {m['ret_dd']:>5.2f}x")

