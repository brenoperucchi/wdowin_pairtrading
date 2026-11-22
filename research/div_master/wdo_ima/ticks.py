# -*- coding: utf-8 -*-
"""
WDO — execução da ordem limite na Wall com os NEGÓCIOS REAIS do Profit (.trd), nos dias que existem em disco.
Para cada 1º toque do dia de cada Wall/MidWall (09:15–16:30), olhando negócio a negócio (sem RLP, flag 13):
  vol_no_nivel   contratos negociados exatamente no preço do nível até o episódio acabar
  furou_1tick    houve negócio 1 tick além do nível (a ordem na fila seria executada com certeza)
  resultado      com a ordem executada no toque: alvo +6 ou stop −4 primeiro (negócio a negócio, até 60 min)
Episódio acaba quando o preço sai 3 pts para o lado do respeito ou fura 1 tick.
A pergunta: nos toques que SEGURAM sem furar (onde "toque" e "fila" divergem), há volume suficiente no nível para
uma ordem de 1 contrato posta antes da abertura (as Walls são conhecidas no pré-mercado) ser executada?
Uso: python research/div_master/wdo_ima/ticks.py
"""
import glob, os, sys, warnings
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path[:0] = [ROOT]
import numpy as np
import pandas as pd
from core.profit_statarb_engine import TRD_DTYPE

TICK = 0.5
DAYS = ["2026-03-30", "2026-06-29", "2026-10-28", "2026-10-29", "2026-11-10", "2026-11-11"]


def load_ticks(date):
    ymd = date.replace("-", "")
    fs = glob.glob(os.path.join(os.path.expanduser(r"~\AppData\Roaming"), "Nelogica", "*", "database", "assets", "WDO*",
                                f"*_0_1_1_1_0_{ymd}.trd"))
    fs = sorted(fs, key=os.path.getsize, reverse=True)
    if not fs:
        return None, None
    a = np.fromfile(fs[0], dtype=TRD_DTYPE, count=os.path.getsize(fs[0]) // 45)
    a = a[(a["qty"] > 0) & (a["px"] > 0) & (a["flag"] != 13)]
    mins = (a["dt"] - np.floor(a["dt"])) * 1440.0
    order = np.argsort(a["tr"], kind="stable")
    return pd.DataFrame(dict(m=mins[order], px=a["px"][order], q=a["qty"][order].astype(float))), os.path.basename(fs[0])


def main():
    h = pd.read_csv(os.path.join(ROOT, "mt5", "Files", "jumba_gex_wdo_history.csv"), sep=";")
    rows = []
    for d in DAYS:
        tk, fname = load_ticks(d)
        if tk is None:
            print(d, "sem .trd")
            continue
        lv = h[(h.session_date == d) & h.type.isin(["Wall", "MidWall"])]
        px, m, q = tk.px.values, tk.m.values, tk.q.values
        print(f"{d} · {fname} · {len(tk):,} negócios · {m.min() / 60:.2f}h → {m.max() / 60:.2f}h · {len(lv)} níveis")
        for r in lv.itertuples():
            L = float(r.price)
            ok = (m >= 555) & (m <= 990)
            idx = np.where(ok & (np.abs(px - L) < 1e-6))[0]
            if len(idx) == 0:
                continue
            i0 = idx[0]
            prev = px[:i0][m[:i0] >= 540]
            if len(prev) == 0:
                continue
            d_ = 1 if prev[-1] > L else -1               # veio de cima → compra (respeito)
            vol, thru, end = 0.0, False, len(px)
            for i in range(i0, len(px)):
                if abs(px[i] - L) < 1e-6:
                    vol += q[i]
                if d_ * (L - px[i]) >= TICK - 1e-9:
                    thru = True
                    end = i
                    break
                if d_ * (px[i] - L) >= 3.0:
                    end = i
                    break
            # resultado com execução no toque (preço L): alvo +6 / stop −4 negócio a negócio, até 60 min
            res = "tempo"
            for i in range(i0 + 1, len(px)):
                if m[i] - m[i0] > 60:
                    break
                if d_ * (px[i] - L) >= 6.0:
                    res = "alvo"
                    break
                if d_ * (L - px[i]) >= 4.0:
                    res = "stop"
                    break
            rows.append(dict(data=d, hora=f"{int(m[i0]) // 60:02d}:{int(m[i0]) % 60:02d}", tipo=r.type, nivel=L,
                             lado="compra" if d_ == 1 else "venda", vol_no_nivel=int(vol), furou_1tick=thru,
                             resultado_toque=res))
    E = pd.DataFrame(rows)
    E.to_csv(os.path.join(HERE, "results", "ticks_toques.csv"), index=False)
    pd.set_option("display.width", 200)
    print("\n" + E.to_string(index=False))
    seg = E[~E.furou_1tick]
    print(f"\n{len(E)} toques · furaram 1 tick: {int(E.furou_1tick.sum())} · seguraram sem furar: {len(seg)}")
    if len(seg):
        print(f"volume no nível nos que seguraram sem furar: mediana {seg.vol_no_nivel.median():.0f} · "
              f"mín {seg.vol_no_nivel.min()} · máx {seg.vol_no_nivel.max()} contratos")
        print(seg.groupby("resultado_toque").vol_no_nivel.describe()[["count", "50%", "min", "max"]].to_string())


if __name__ == "__main__":
    main()
