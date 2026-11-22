"""Platôs de vizinhos de I3 e I5 e comparação de carteiras 3 pontas (E22 WIN + novo WIN + V1a WDO)."""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import get_e22_signals, eval_e22
from research.div_master.win_especialista.robustez_win_v32 import run_win_v32, eval_win, make_PW, OPT_WIN_OPEN
from research.div_master.wdo_especialista.robustez_final import make_P as make_P_wdo
from research.div_master.wdo_especialista.robustez_v32_100 import run_v32 as run_v32_wdo, eval_v32 as eval_wdo, OPT_OPEN


def fmt_grid(rows, sl_vals, tp_vals, tmax):
    for sl in sl_vals:
        parts = []
        for tp in tp_vals:
            s, _ = eval_win(rows, sl, tp, tmax)
            parts.append(f"TP{tp:.0f}:{s['rdd']:.2f}({s['meses']})")
        print(f"  SL={sl:.0f}: " + " | ".join(parts))


if __name__ == "__main__":
    print("=== PLATÔ I3 (V32_PROD | OPC | ALL | tm<660 | ext50>0 | t=24) ===")
    r_i3 = run_win_v32(make_PW(150, 220), "all", M.V32_PROD, "OPC", None, lambda r: r["tm"] < 660, lambda r: r["ext50"] > 0.0)
    fmt_grid(r_i3, (200.0, 220.0, 250.0, 280.0, 300.0), (200.0, 220.0, 250.0, 280.0, 300.0), 24)
    print("  Janelas I3 (250/250 t24):")
    for lbl, tend in [("09h-10h (tm<600)", 600), ("09h-10h30 (tm<630)", 630), ("09h-11h (tm<660)", 660),
                      ("09h-11h30 (tm<690)", 690), ("09h-12h (tm<=720)", 721)]:
        rr = run_win_v32(make_PW(150, 220), "all", M.V32_PROD, "OPC", None, lambda r, te=tend: r["tm"] < te, lambda r: r["ext50"] > 0.0)
        print(f"    {lbl:20s}:", eval_win(rr, 250.0, 250.0, 24)[0])
    print("  Zona I3 (250/250 t24):")
    for z, p in [(100, 150), (150, 220), (200, 300)]:
        rr = run_win_v32(make_PW(z, p), "all", M.V32_PROD, "OPC", None, lambda r: r["tm"] < 660, lambda r: r["ext50"] > 0.0)
        print(f"    z={z}/p={p}:", eval_win(rr, 250.0, 250.0, 24)[0])

    print("\n=== PLATÔ I5 (V32 open=True | CONF | d_wall<=150 | 09h-12h | pass>0 | t=24) ===")
    r_i5 = run_win_v32(make_PW(150, 220), "all", OPT_WIN_OPEN, "CONF",
                       lambda r: r["d_wall"] <= 150.0, lambda r: r["tm"] <= 720, lambda r: r["pass_"] > 0.0)
    fmt_grid(r_i5, (180.0, 200.0, 220.0, 250.0), (200.0, 250.0, 300.0, 350.0), 24)
    print("  Janelas/Níveis I5 (200/300 t24):")
    for lbl, lv, tend, zp in [
        ("all tm<=690 z150", "all", 690, (150, 220)),
        ("all tm<=720 z150", "all", 720, (150, 220)),
        ("all tm<=780 z150", "all", 780, (150, 220)),
        ("wall tm<=720 z150", "wall", 720, (150, 220)),
        ("all tm<=720 z100", "all", 720, (100, 150)),
        ("all tm<=720 z200", "all", 720, (200, 300)),
    ]:
        rr = run_win_v32(make_PW(*zp), lv, OPT_WIN_OPEN, "CONF",
                         lambda r, dz=zp[0]: r["d_wall"] <= dz, lambda r, te=tend: r["tm"] <= te, lambda r: r["pass_"] > 0.0)
        print(f"    {lbl:20s}:", eval_win(rr, 200.0, 300.0, 24)[0])

    print("\n=== Carteiras completas (WIN E22 2ct + WIN novo 1ct + WDO V1a 1ct) ===")
    _, df_e22 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=2.0)
    P_wdo = make_P_wdo(zone=3.5, pierce_max=6.0)
    r_wdo = run_v32_wdo(P_wdo, "wall", "common", OPT_OPEN, "CONF",
                        lambda r: r["d_wall"] <= 3.5, lambda r: r["hh"] != 11, lambda r: r["ext30"] > 0.0)
    _, df_wdo = eval_wdo(r_wdo, 14.0, "nw", 0.0, 24, "UM")

    r_i2 = run_win_v32(make_PW(150, 220), "all", M.V32_PROD, "OPC",
                       lambda r: r["esp"] == "WALL", lambda r: r["tm"] <= 720, lambda r: r["ext50"] > -0.5 and r["slope50"] > -0.5)
    _, df_i2 = eval_win(r_i2, 200.0, 300.0, 24)
    _, df_i3 = eval_win(r_i3, 250.0, 250.0, 24)
    _, df_i5 = eval_win(r_i5, 200.0, 300.0, 24)

    for name, df_c in [("Sem extra (E22+WDO)", None), ("E22+I2+WDO", df_i2), ("E22+I3+WDO", df_i3), ("E22+I5+WDO", df_i5)]:
        df_win_tot = df_e22 if df_c is None else pd.concat([df_e22, df_c], ignore_index=True).sort_values(["date", "xt"])
        p = bt.portfolio(df_win_tot, df_wdo, "pnl", "pnl", "xt", "xt")
        print(f"  {name:22s}:", p)
