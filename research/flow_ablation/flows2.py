# -*- coding: utf-8 -*-
"""
Variantes da onda com componentes por player / forma de apregoar / tamanho de lote (16/11/2026).
Estende flows.make (sem alterar flows.py): mesmo pipeline da onda, só a força por barra muda.

.min (todos os pregões — backtest completo):
  M_NTRD   força = (boletas compradoras − vendedoras do .min) × lote médio da barra     [contagem, sem preço]
  M_LOTE   força = delta só dos minutos/lados com lote médio >= p90 do ativo             ["lote grande", sem preço]
  M_EXC    força = delta agressor − lote médio × delta de contagem                       [excesso de lote, sem preço]
  W_SEM_INST  base sem o termo Inst: (0,45·Wyckoff + 0,25·Porte)/0,70                   [controle]
  W_NTRD / W_LOTE / W_EXC   base com o termo Inst TROCADO pelo componente acima (Wyckoff e Porte mantidos)
Tape (.trd) — híbridas: base em todos os pregões, e nos pregões com tape completo o termo Inst é trocado por:
  H_PROJ     0,55·inst_agr + 1,15·inst_pas − 0,85·varejo com a classificação do projeto aplicada ao TAPE real
  H_PLAYERS  0,55·agr(gringo+nacional) + 1,15·pas(gringo+nacional) − 0,85·agr(varejo) por corretora (sem regra de lote)
  H_GRINGO   saldo líquido das corretoras estrangeiras
  H_HFT      agressão das corretoras HFT (Ideal)
  H_LOTE     delta das boletas agressoras >= p90 do ativo
  H_ABS      absorção (grupos passivos >= p99, sinal do lado passivo)
  HP_*       mesmas, mas o componente vira a força INTEIRA nos pregões de tape (sem Wyckoff/Porte);
             HP_AGR = agressão total do tape (controle = "B puro"), HP_VAREJO = −agressão do varejo
"""
import os, json, glob
from functools import lru_cache
import numpy as np, pandas as pd
import flows as FL

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
_orig_make = FL.make
MIN_VARS = ["M_NTRD", "M_LOTE", "M_EXC", "W_SEM_INST", "W_NTRD", "W_LOTE", "W_EXC"]
TAPE_VARS = ["H_PROJ", "H_PLAYERS", "H_GRINGO", "H_HFT", "H_LOTE", "H_ABS"]
# puras (só o componente vira a força nos pregões de tape; base nos demais). HP_AGR = agressão total = controle "B puro"
TAPE_PURE = ["HP_AGR", "HP_PROJ", "HP_PLAYERS", "HP_GRINGO", "HP_HFT", "HP_LOTE", "HP_ABS", "HP_VAREJO"]
TAPE_VARS = TAPE_VARS + TAPE_PURE
ALL2 = MIN_VARS + TAPE_VARS


@lru_cache(maxsize=2)
def min_comp(asset):
    p90 = json.load(open(os.path.join(RES, "min_p90_lote.json")))[asset]
    out = {}
    for d, (a, mod) in FL.m1_raw(asset).items():
        bq, sq = a["buy_qty"].astype(float), a["sell_qty"].astype(float)
        bt, st = a["buy_trd"].astype(float), a["sell_trd"].astype(float)
        bl, sl = bq / np.maximum(1, bt), sq / np.maximum(1, st)
        big = np.where(bl >= p90, bq, 0) - np.where(sl >= p90, sq, 0)
        b5 = (mod // 5) * 5
        dd = {}
        for k in np.unique(b5):
            s = b5 == k
            B, S_, BT, ST = bq[s].sum(), sq[s].sum(), bt[s].sum(), st[s].sum()
            lot = (B + S_) / max(1.0, BT + ST)
            lb, ls = B / max(1.0, BT), S_ / max(1.0, ST)
            dd[f"{int(k) // 60:02d}:{int(k) % 60:02d}"] = dict(ntrd=(BT - ST) * lot, lote=float(big[s].sum()),
                                                           exc=(B - S_) - 0.5 * (lb + ls) * (BT - ST))
        out[d] = dd
    return out


@lru_cache(maxsize=2)
def tape_comp(asset):
    out = {}
    for f in glob.glob(os.path.join(RES, "tape", f"comp_{asset}_*.pkl")):
        d = os.path.basename(f)[len(f"comp_{asset}_"):-4]
        c = pd.read_pickle(f)
        out[d] = {r["time"]: r for r in c.to_dict("records")}
    return out


def _tape_inst(name, r):
    if name == "H_PROJ":
        return 0.55 * r["proj_inst_aggr"] + 1.15 * r["proj_inst_pass"] - 0.85 * r["proj_ret"]
    if name == "H_PLAYERS":
        return (0.55 * (r["agr_GRINGO"] + r["agr_NACIONAL"]) + 1.15 * (r["pas_GRINGO"] + r["pas_NACIONAL"])
                - 0.85 * r["agr_VAREJO"])
    name = name.replace("HP_", "H_")
    if name == "H_VAREJO":
        return -r["agr_VAREJO"]          # varejo invertido (mesmo sinal do termo −0,85·varejo da força)
    if name == "H_PROJ":
        return 0.55 * r["proj_inst_aggr"] + 1.15 * r["proj_inst_pass"] - 0.85 * r["proj_ret"]
    if name == "H_PLAYERS":
        return (0.55 * (r["agr_GRINGO"] + r["agr_NACIONAL"]) + 1.15 * (r["pas_GRINGO"] + r["pas_NACIONAL"])
                - 0.85 * r["agr_VAREJO"])
    return r[{"H_GRINGO": "net_GRINGO", "H_HFT": "agr_HFT", "H_LOTE": "p_ge90", "H_ABS": "abs_big",
              "H_AGR": "agr_total"}[name]]


def make(name):
    if name.startswith("HPS_"):            # nulo: força HP_PROJ embaralhada dentro do pregão de tape (semente = sufixo)
        seed = int(name[4:])
        inner = make("HP_PROJ")

        def flow_null(bars, asset):
            out = inner(bars, asset)
            if FL.Ctx.date not in tape_comp(asset):
                return out
            F = np.array([b["force"] for b in out])
            rs = np.random.RandomState(int(FL.Ctx.date.replace("-", "")) % 100000 + seed)
            return FL._pipeline([dict(b) for b in bars], [float(x) for x in F[rs.permutation(len(F))]])
        return flow_null
    if name not in ALL2:
        return _orig_make(name)

    def flow(bars, asset):
        FL._set_date(bars, asset)
        P = [FL._parts(b, asset) for b in bars]
        keys = [str(b["time"])[:5] for b in bars]
        if name in MIN_VARS:
            C = min_comp(asset).get(FL.Ctx.date, {})
            if name == "W_SEM_INST":
                F = [(0.45 * p["wyk"] + 0.25 * p["porte"]) / 0.70 for p in P]
            else:
                k = {"NTRD": "ntrd", "LOTE": "lote", "EXC": "exc"}[name.split("_")[1]]
                comp = [float(C.get(t, {}).get(k, 0.0)) for t in keys]
                if name.startswith("M_"):
                    F = comp
                else:
                    F = [0.45 * p["wyk"] + 0.25 * p["porte"] + 0.30 * x for p, x in zip(P, comp)]
        else:
            T = tape_comp(asset).get(FL.Ctx.date)
            F = []
            for p, t in zip(P, keys):
                if T is None:
                    inst = p["inst"]
                else:
                    r = T.get(t)
                    inst = 0.0 if r is None else float(_tape_inst(name, r))
                if name.startswith("HP_") and T is not None:
                    F.append(inst)
                elif name.startswith("HP_"):
                    F.append(0.45 * p["wyk"] + 0.25 * p["porte"] + 0.30 * p["inst"])
                else:
                    F.append(0.45 * p["wyk"] + 0.25 * p["porte"] + 0.30 * inst)
        return FL._pipeline(bars, [float(x) for x in F])
    return flow


FL.make = make
