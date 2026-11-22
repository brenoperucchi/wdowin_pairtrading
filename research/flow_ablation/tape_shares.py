# -*- coding: utf-8 -*-
"""Participação de cada classe de corretora no volume agressor e passivo (dias de tape completos) e quem fica
do lado comprador nas barras de alta. Saída: results/tape/participacao_classes.csv"""
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tape_components as TC

inv = pd.read_csv(os.path.join(TC.OUT, "inventario_trd.csv"))
full = inv[inv.completo & inv.asset.isin(["WIN", "WDO"])].drop_duplicates(["asset", "date"])
rows = []
for _, r in full.iterrows():
    T = TC.prep(r["path"], r["asset"] == "WIN")
    book, qty, agg, pas, sw = T["book"], T["qty"], T["agg"], T["pas"], T["sw"]
    tot = qty[book].sum()
    known_a = np.zeros(len(qty), bool)
    known_p = np.zeros(len(qty), bool)
    rec = dict(asset=r["asset"], date=r["date"], vol_book=tot, rlp_share=qty[T["fl"] == 13].sum() / qty.sum())
    for c, codes in TC.CLS.items():
        ma, mp = np.isin(agg, codes) & book, np.isin(pas, codes) & book
        known_a |= ma
        known_p |= mp
        rec[f"agr_{c}"] = qty[ma].sum() / tot
        rec[f"pas_{c}"] = qty[mp].sum() / tot
        rec[f"lote_med_agr_{c}"] = np.median(sw[ma]) if ma.any() else np.nan
    rec["agr_OUTROS"] = qty[book & ~known_a].sum() / tot
    rec["pas_OUTROS"] = qty[book & ~known_p].sum() / tot
    rows.append(rec)
    print(r["asset"], r["date"], flush=True)
pd.DataFrame(rows).to_csv(os.path.join(TC.OUT, "participacao_classes.csv"), index=False)
