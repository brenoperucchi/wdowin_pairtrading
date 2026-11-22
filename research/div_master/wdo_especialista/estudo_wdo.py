# -*- coding: utf-8 -*-
"""
Estudo de evento de divergências + Walls no WDO (02/01 a 11/11/2026, 213 pregões).
Testa todos os motores causais (v2.1, v2.2, v3.1, v3.2 prod, v3.2 abertura, v3)
em dois momentos de entrada (CONF imediato na barra seguinte à confirmação vs Opção C),
e separa todas as âncoras (Wall, MidWall, Furo, Extremo do dia, Super, Sem âncora).
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas")]

import numpy as np
import pandas as pd
import bt
import modulo as M
from research.div_wall.data import load_asset


def build_candidates(DS, data):
    P = M.PARAMS["WDO"]
    rows = []
    for d in sorted(data):
        if d > bt.END or d not in DS:
            continue
        bars, walls, _ = data[d]
        fb = M.compute_flow([dict(b) for b in bars], "WDO")
        atr = M.atr_series(fb, P["tick"])
        D = DS[d]
        pos_m = D["pos"]

        # Separa Wall pura vs MidWall para análise granular
        all_levels = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES and w.get("price") is not None)
        wall_only = sorted(float(w["price"]) for w in walls if w.get("type") == "Wall" and w.get("price") is not None)
        mid_only = sorted(float(w["price"]) for w in walls if w.get("type") == "MidWall" and w.get("price") is not None)

        eng_map = {
            "v2.1": M.engine_v21(fb, all_levels, P, "all", atr=atr),
            "v2.2": M.engine_v22(fb, all_levels, P, "all", atr=atr, opt=M.V22_ABERTURA),
            "v3.1": M.engine_v31(fb, all_levels, P, "all", require_micro=False, atr=atr),
            "v3.2": M.engine_v32(fb, all_levels, P, "all", atr=atr, opt=M.V32_PROD),
            "v3.2_ab": M.engine_v32(fb, all_levels, P, "all", atr=atr, opt=M.V32),
            "v3": M.engine_v3(fb, all_levels, P, "all"),
        }

        for ename, cands in eng_map.items():
            trig, _ = M.triggers(fb, cands, P)
            first_trig = {}
            for x in trig:
                key = (x["dir"], x["j"])
                if key not in first_trig or x["idx"] < first_trig[key]["idx"]:
                    first_trig[key] = x

            seq_conf = {1: 0, -1: 0}
            for c in cands:
                dir_ = int(c["dir"])
                j = int(c["j"])
                conf = int(c["conf"])
                if conf + 1 >= len(fb):
                    continue
                t_in_conf = fb[conf + 1]["time"]
                e_conf = pos_m.get(bt.hm(t_in_conf))
                if e_conf is None or e_conf < 1:
                    continue

                ep = float(D["o5"][e_conf])
                tm_conf = int(D["tm5"][e_conf])
                seq_c = seq_conf[dir_]
                seq_conf[dir_] += 1

                # Distância até Wall pura e MidWall no pivô F2
                px2 = float(c["px2"])
                d_wall = min((abs(px2 - lv) for lv in wall_only), default=999.0)
                d_mid = min((abs(px2 - lv) for lv in mid_only), default=999.0)
                has_wall = (c["c1"] is not None) or (c["c2"] is not None)
                has_day = c["day"] is not None
                anc_kind = (
                    "SUPER" if (has_wall and has_day)
                    else ("FURO_WALL" if c["c1"] is not None else ("WALL_ZONA" if c["c2"] is not None else ("EXTREMO" if has_day else "SEM_ANC")))
                )
                near_kind = "WALL" if d_wall <= P["zone"] else ("MID" if d_mid <= P["zone"] else "NENHUMA")

                # Contexto causal na barra e_conf - 1 (via D["c50"][e_conf] que já é barra e_conf-1)
                c50 = float(D["c50"][e_conf])
                u50 = float(D["u50"][e_conf])
                l50 = float(D["l50"][e_conf])
                half50 = max(u50 - c50, 0.5)
                c50_old = float(D["c50"][max(0, e_conf - 6)])
                cl_prev = float(D["c5"][e_conf - 1])
                ext50 = -dir_ * (cl_prev - c50) / half50
                slope50 = dir_ * (c50 - c50_old) / half50

                u30 = float(D["u30"][e_conf])
                l30 = float(D["l30"][e_conf])
                c30 = 0.5 * (u30 + l30)
                half30 = max(u30 - c30, 0.5)
                ext30 = -dir_ * (cl_prev - c30) / half30

                day_open = float(D["o5"][0])
                dmov = dir_ * (cl_prev - day_open) / half50

                # Retornos futuros líquidos de custo (0.5 pt)
                n5 = len(D["c5"])
                retn = {}
                for k in (3, 6, 12, 18, 24):
                    idx_k = min(e_conf + k - 1, n5 - 1)
                    retn[f"r{k}"] = dir_ * (float(D["c5"][idx_k]) - ep) - 0.5

                # Opção C se existir
                tr = first_trig.get((dir_, j))
                e_opc = None
                retn_opc = {f"o_r{k}": np.nan for k in (3, 6, 12, 18, 24)}
                if tr is not None and tr["idx"] + 1 < len(fb):
                    e_opc = pos_m.get(bt.hm(fb[tr["idx"] + 1]["time"]))
                    if e_opc is not None and e_opc >= 1:
                        ep_o = float(D["o5"][e_opc])
                        for k in (3, 6, 12, 18, 24):
                            idx_k = min(e_opc + k - 1, n5 - 1)
                            retn_opc[f"o_r{k}"] = dir_ * (float(D["c5"][idx_k]) - ep_o) - 0.5

                b_j = fb[j]
                b_conf = fb[conf]
                micro_ok = bool(c.get("micro"))
                wyck_dir = dir_ * float(b_conf.get("wyckoff_abs", 0.0))
                pass_dir = dir_ * float(b_conf.get("inst_pass_delta", 0.0))
                aggr_dir = dir_ * float(b_conf.get("inst_aggr_delta", 0.0))

                rows.append(dict(
                    date=d, engine=ename, dir=dir_, j=j, k=int(c["k"]), conf=conf,
                    e_conf=e_conf, tm=tm_conf, seq_c=seq_c, lag=conf - j,
                    anc=anc_kind, has_wall=has_wall, has_day=has_day, near_kind=near_kind,
                    d_wall=d_wall, d_mid=d_mid, micro=micro_ok, ext=bool(c.get("ext")),
                    wd_ratio=float(c["wd"]) / max(float(c["thr"]), 1e-6),
                    ext50=ext50, slope50=slope50, ext30=ext30, dmov=dmov,
                    wyck_dir=wyck_dir, pass_dir=pass_dir, aggr_dir=aggr_dir,
                    has_opc=tr is not None, opc_sub=(tr["sub"] if tr else "NONE"),
                    opc_esp=(tr["esp"] if tr else "NONE"), e_opc=e_opc,
                    **retn, **retn_opc,
                ))
    return pd.DataFrame(rows)


def main():
    DS = bt.market("WDO")
    data = load_asset("WDO", "M5")
    df = build_candidates(DS, data)
    out_pkl = os.path.join(HERE, "wdo_cands.pkl")
    df.to_pickle(out_pkl)

    df["period"] = np.where(df.date <= bt.H1_END, "H1_jan_abr",
                    np.where(df.date <= bt.IS_END, "H2_mai_jul", "OOS_ago_nov"))

    pd.set_option("display.width", 220)
    print(f"Total candidatos WDO: {len(df)} em {df.date.nunique()} pregões")

    print("\n=== 1. POR MOTOR (todos os candidatos CONF, r12 médio líquido em pts) ===")
    g1 = df.groupby(["engine", "period"]).r12.agg(["size", "mean"]).unstack("period").round(2)
    g1["ALL_mean"] = df.groupby("engine").r12.mean().round(2)
    print(g1.to_string())

    print("\n=== 2. POR MOTOR × ÂNCORA (CONF, r12 líquido em pts) ===")
    g2 = df.groupby(["engine", "anc", "period"]).r12.agg(["size", "mean"]).unstack("period").round(2)
    g2["ALL_mean"] = df.groupby(["engine", "anc"]).r12.mean().round(2)
    print(g2.to_string())

    print("\n=== 3. OPÇÃO C POR MOTOR × ESP (o_r12 líquido em pts) ===")
    dfo = df[df.o_r12.notna()]
    g3 = dfo.groupby(["engine", "opc_esp", "period"]).o_r12.agg(["size", "mean"]).unstack("period").round(2)
    g3["ALL_mean"] = dfo.groupby(["engine", "opc_esp"]).o_r12.mean().round(2)
    print(g3.to_string())

    print("\n=== 4. FATORES DE CONTEXTO NO CONF (todos motores combinados e v3.2 / v2.1) ===")
    for ename in ("v3.2", "v3.2_ab", "v2.1", "v2.2"):
        sub = df[df.engine == ename].copy()
        print(f"\n--- Motor {ename} (n={len(sub)}) ---")
        sub["hora"] = (sub.tm // 60).astype(int)
        sub["ext_b"] = pd.cut(sub.ext50, [-99, -0.5, 0.0, 0.5, 1.0, 99])
        sub["slp_b"] = pd.cut(sub.slope50, [-99, -0.5, 0.0, 0.5, 99])
        sub["dmov_b"] = pd.cut(sub.dmov, [-99, -1.0, 0.0, 1.0, 99])
        sub["lag_b"] = sub.lag.clip(upper=3)
        sub["seq_b"] = sub.seq_c.clip(upper=3)
        for col in ("dir", "anc", "near_kind", "hora", "ext_b", "slp_b", "dmov_b", "lag_b", "seq_b", "micro", "ext"):
            gg = sub.groupby([col, "period"], observed=True).r12.agg(["size", "mean"]).unstack("period").round(2)
            gg["ALL"] = sub.groupby(col, observed=True).r12.mean().round(2)
            print(f"  [{col}]\n{gg.to_string()}")


if __name__ == "__main__":
    main()
