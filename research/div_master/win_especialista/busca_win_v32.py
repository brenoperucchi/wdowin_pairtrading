"""Busca sistemática no WIN (índice) com foco exclusivo em v3.2 + >= 100 trades (bt.sim M1)."""
import sys
import time
import pickle
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from research.div_wall.data import load_asset
from research.div_master.especialistas import bt, modulo as M
from research.div_master.win_especialista.audit_e22_win import win_cache, XW, get_e22_signals, eval_e22

DS_WIN = bt.market("WIN")
lo_w, hi_w = bt.WINDOW["WIN"]
OPT_WIN_OPEN = {**M.V32, "abertura": M.V22_ABERTURA}


def make_PW(zone=150.0, pierce_max=220.0):
    P = dict(M.PARAMS["WIN"])
    P["zone"] = zone
    P["pierce_max"] = pierce_max
    return P


def collect_base(P_cfg, lv_mode, opt, mode):
    """Coleta candidatos base WIN (CONF ou OPC) com features causais para filtragem rápida."""
    rows = []
    for d in sorted(win_cache):
        fb, w_all, w_wall, D = win_cache[d]
        levels = w_all if lv_mode == "all" else w_wall
        atr = M.atr_series(fb, P_cfg["tick"])
        cands = M.engine_v32(fb, levels, P_cfg, "common", atr=atr, opt=opt)

        if mode == "OPC":
            trigs, _ = M.triggers(fb, cands, P_cfg)
            by = {(c["dir"], c["j"]): c for c in cands}
            seq = {1: 0, -1: 0}
            for tr in trigs:
                if tr.get("dup"):
                    continue
                s = seq[tr["dir"]]
                seq[tr["dir"]] += 1
                t = tr["idx"]
                if t + 1 >= len(fb):
                    continue
                c = by[(tr["dir"], tr["j"])]
                idx_sig, idx_in = t, t + 1
                rows.append((d, D, fb, w_all, w_wall, c, idx_sig, idx_in, s, bool(tr.get("super")), tr.get("esp", ""), tr.get("sub", "")))
        else:
            for c in cands:
                conf = c["conf"]
                if conf + 1 >= len(fb):
                    continue
                rows.append((d, D, fb, w_all, w_wall, c, conf, conf + 1, 0, False, "CONF", c.get("src", "")))

    recs = []
    for d, D, fb, w_all, w_wall, c, idx_sig, idx_in, seq_n, is_super, esp, sub in rows:
        tm = bt.hm(fb[idx_in]["time"])
        if not (lo_w <= tm <= hi_w) or tm not in D["pos"]:
            continue
        e = D["pos"][tm]
        if e < 1:
            continue
        ep = float(D["o5"][e])
        dr = int(c["dir"])
        half50 = max(float(D["u50"][e] - D["c50"][e]), XW["tick"])
        half30 = max(0.5 * float(D["u30"][e] - D["l30"][e]), XW["tick"])
        ext50 = -dr * float(D["c5"][e - 1] - D["c50"][e]) / half50
        slope50 = dr * float(D["c50"][e] - D["c50"][max(0, e - 6)]) / half50
        ext30 = -dr * float(D["c5"][e - 1] - 0.5 * (D["u30"][e] + D["l30"][e])) / half30
        px2 = float(c["px2"])
        d_wall = min((abs(px2 - w) for w in w_wall), default=99999.0)
        pass_s = dr * sum(float(fb[x].get("inst_pass_delta", 0.0)) for x in range(c["j"], idx_sig + 1))
        candle_fav = dr * (float(fb[idx_sig]["close"]) - float(fb[idx_sig]["open"])) > 0
        nw = bt.next_level(w_all, ep, dr, 50.0 + XW["front"])
        nw_d = dr * (nw - ep) - XW["front"] if nw is not None else np.nan

        recs.append(dict(
            date=d, e=e, ep=ep, dir=dr, j=c["j"], tm=tm, hh=tm // 60, seq=seq_n, is_super=is_super,
            esp=esp, sub=sub, has_w=(c["c1"] is not None or c["c2"] is not None),
            has_c1=(c["c1"] is not None), has_d=(c["day"] is not None), d_wall=d_wall,
            ext50=ext50, slope50=slope50, ext30=ext30, pass_=pass_s, candle_fav=candle_fav,
            nw_d=nw_d, src=c.get("src", ""),
        ))
    return pd.DataFrame(recs).sort_values(["date", "tm", "j"]).reset_index(drop=True)


EXITS = [
    ("SL200_NOB_BE180_t12", dict(sl=200.0, tp_kind="none", tp_val=0.0, be_t=180.0, be_l=20.0, tmax=12)),
    ("SL200_TP200_t12", dict(sl=200.0, tp_kind="fix", tp_val=200.0, be_t=0.0, be_l=0.0, tmax=12)),
    ("SL200_TP250_t18", dict(sl=200.0, tp_kind="fix", tp_val=250.0, be_t=0.0, be_l=0.0, tmax=18)),
    ("SL200_TP300_t24", dict(sl=200.0, tp_kind="fix", tp_val=300.0, be_t=0.0, be_l=0.0, tmax=24)),
    ("SL250_TP200_t18", dict(sl=250.0, tp_kind="fix", tp_val=200.0, be_t=0.0, be_l=0.0, tmax=18)),
    ("SL250_TP250_t24", dict(sl=250.0, tp_kind="fix", tp_val=250.0, be_t=0.0, be_l=0.0, tmax=24)),
    ("SL250_TP350_t24", dict(sl=250.0, tp_kind="fix", tp_val=350.0, be_t=0.0, be_l=0.0, tmax=24)),
    ("SL300_TP250_t24", dict(sl=300.0, tp_kind="fix", tp_val=250.0, be_t=0.0, be_l=0.0, tmax=24)),
    ("SL200_NW_t18", dict(sl=200.0, tp_kind="nw", tp_val=0.0, be_t=0.0, be_l=0.0, tmax=18)),
    ("SL250_NW_t24", dict(sl=250.0, tp_kind="nw", tp_val=0.0, be_t=0.0, be_l=0.0, tmax=24)),
    ("SL220_NWE30_t18", dict(sl=220.0, tp_kind="nwe30", tp_val=0.0, be_t=180.0, be_l=20.0, tmax=18)),
]


def presim_exit(df, ex_cfg):
    """Pré-simula uma regra de saída sobre todos os sinais de df usando bt.sim."""
    n = len(df)
    pnl = np.full(n, np.nan)
    xt = np.zeros(n, dtype=np.int64)
    sl = ex_cfg["sl"]
    tk = ex_cfg["tp_kind"]
    tv = ex_cfg["tp_val"]
    bt_t, bt_l, tmax = ex_cfg["be_t"], ex_cfg["be_l"], ex_cfg["tmax"]
    for i, r in enumerate(df.itertuples()):
        D = DS_WIN[r.date]
        use_band = False
        band = D["u30"]
        tp_fix = r.ep + r.dir * 999999.0
        lo, hi = 0.0, 0.0
        if tk == "fix":
            tp_fix = r.ep + r.dir * tv
        elif tk == "nw":
            if np.isnan(r.nw_d) or r.nw_d < 50.0:
                continue
            tp_pts = min(max(r.nw_d, 100.0), 600.0)
            tp_fix = r.ep + r.dir * tp_pts
        elif tk == "nwe30":
            use_band = True
            band = D["u30"] if r.dir == 1 else D["l30"]
            lo, hi = 150.0, 600.0
        p, x = bt.sim(*bt._args(D), band, r.e, r.ep, r.dir, sl, tp_fix, use_band,
                      XW["front"], lo, hi, bt_t, bt_l, tmax, XW["tick"])
        pnl[i] = (p - XW["cost"]) * XW["brl"]
        xt[i] = x
    return pnl, xt


if __name__ == "__main__":
    t0 = time.time()
    # Baseline E22 WIN diário para checar correlação
    _, df_e22 = eval_e22(get_e22_signals("all", M.V32_PROD), mult=1.0)
    all_dates = pd.Index(sorted(win_cache.keys()))
    s_e22 = df_e22.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)

    configs = [
        ("V32_PROD_all_z150", make_PW(150, 220), "all", M.V32_PROD, "CONF"),
        ("V32_PROD_all_z150", make_PW(150, 220), "all", M.V32_PROD, "OPC"),
        ("V32_PROD_wall_z150", make_PW(150, 220), "wall", M.V32_PROD, "CONF"),
        ("V32_PROD_wall_z150", make_PW(150, 220), "wall", M.V32_PROD, "OPC"),
        ("V32_OPEN_all_z150", make_PW(150, 220), "all", OPT_WIN_OPEN, "CONF"),
        ("V32_OPEN_all_z150", make_PW(150, 220), "all", OPT_WIN_OPEN, "OPC"),
        ("V32_OPEN_wall_z150", make_PW(150, 220), "wall", OPT_WIN_OPEN, "CONF"),
        ("V32_OPEN_wall_z150", make_PW(150, 220), "wall", OPT_WIN_OPEN, "OPC"),
        ("V32_PROD_wall_z100", make_PW(100, 150), "wall", M.V32_PROD, "CONF"),
        ("V32_OPEN_wall_z100", make_PW(100, 150), "wall", OPT_WIN_OPEN, "CONF"),
    ]

    hits = []
    for cfg_name, P_cfg, lv_mode, opt, mode in configs:
        df = collect_base(P_cfg, lv_mode, opt, mode)
        if df.empty:
            continue
        presims = {ex_name: presim_exit(df, ex_cfg) for ex_name, ex_cfg in EXITS}

        if mode == "OPC":
            anc_masks = {
                "ALL": np.ones(len(df), dtype=bool),
                "WALL_ESP": (df["esp"] == "WALL").values,
                "EXT_ESP": (df["esp"] == "EXTREMO").values,
                "NO_SUP_SEQ2": (~df["is_super"] & (df["seq"] <= 1)).values,
                "DWALL150": (df["d_wall"] <= 150.0).values,
            }
        else:
            anc_masks = {
                "COMMON": (df["has_w"] | df["has_d"]).values,
                "ANY_WALL": df["has_w"].values,
                "DWALL150": (df["d_wall"] <= 150.0).values,
                "C1_ONLY": df["has_c1"].values,
            }

        time_masks = {
            "ALL": np.ones(len(df), dtype=bool),
            "09_12": (df["tm"] <= 720).values,
            "09_13": (df["tm"] <= 780).values,
            "09_15": (df["tm"] <= 900).values,
            "10_16": ((df["tm"] >= 600) & (df["tm"] < 960)).values,
            "HH_NE_11": (df["hh"] != 11).values,
            "MANHA_09_11": (df["tm"] < 660).values,
        }
        ctx_masks = {
            "NONE": np.ones(len(df), dtype=bool),
            "ext30>0": (df["ext30"] > 0.0).values,
            "ext50>-0.5&sl>-0.5": ((df["ext50"] > -0.5) & (df["slope50"] > -0.5)).values,
            "ext50>0": (df["ext50"] > 0.0).values,
            "pass>0": (df["pass_"] > 0.0).values,
            "candle_fav": df["candle_fav"].values,
        }

        for a_name, ma in anc_masks.items():
            for t_name, mt in time_masks.items():
                mat = ma & mt
                if mat.sum() < 100:
                    continue
                for c_name, mc in ctx_masks.items():
                    mask = mat & mc
                    if mask.sum() < 100:
                        continue
                    sub_base = df.loc[mask, ["date", "tm"]].copy()
                    for ex_name, (p_arr, x_arr) in presims.items():
                        sub_p = p_arr[mask]
                        valid = ~np.isnan(sub_p)
                        if valid.sum() < 100:
                            continue
                        sub = sub_base.iloc[valid].copy()
                        sub["pnl"] = sub_p[valid]
                        sub["xt"] = x_arr[mask][valid]
                        sub = bt.mgmt(sub, "pnl", "xt", "UM")
                        if len(sub) < 100:
                            continue
                        st = bt.stats(sub, "pnl", "xt")
                        if st["rdd"] >= 5.0 and st["h1"] > 0 and st["h2"] > 0 and st["oos"] > 0:
                            s_cand = sub.groupby("date")["pnl"].sum().reindex(all_dates, fill_value=0.0)
                            corr = float(s_cand.corr(s_e22))
                            hits.append(dict(
                                cfg=cfg_name, mode=mode, anc=a_name, time=t_name, ctx=c_name,
                                exit=ex_name, corr_e22=round(corr, 3), **st
                            ))

    res = pd.DataFrame(hits).sort_values(["rdd", "ops"], ascending=[False, False]).reset_index(drop=True)
    out_pkl = Path(__file__).with_name("win_v32_hits.pkl")
    res.to_pickle(out_pkl)
    print(f"Concluído em {time.time()-t0:.1f}s | Hits (ops>=100, Ret/DD>=5.0, H1/H2/OOS>0): {len(res)}")
    if not res.empty:
        print("\n=== Top 20 Geral ===")
        print(res.head(20).to_string(index=False))
        low_c = res[res["corr_e22"] < 0.35]
        print(f"\n=== Top 15 Baixa Correlação com E22 atual (corr < 0.35): {len(low_c)} hits ===")
        if not low_c.empty:
            print(low_c.head(15).to_string(index=False))
        conf_only = res[res["mode"] == "CONF"]
        print(f"\n=== Top 15 Modo CONF (estilo V1a do WDO): {len(conf_only)} hits ===")
        if not conf_only.empty:
            print(conf_only.head(15).to_string(index=False))
