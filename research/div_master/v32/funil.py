# -*- coding: utf-8 -*-
"""
Funil do especialista ESP_DIV_V22_WIN (motor v3.2 sem abertura): marcações do painel → entradas.
Para cada divergência (e para cada marcação = uma por perna, como o painel desenha), registra a PRIMEIRA etapa
em que ela é descartada, na mesma ordem do core/especialista_v22.run:
  1. confirmação tarde   — o pivô do F2 só confirma depois de F2+3 barras (janela do gatilho Opção C já fechou)
  2. sem gatilho         — confirmou a tempo, mas nenhum fechamento de retomada (Opção C) em F2+1..F2+3
  3. super-confluência   — F2 na Wall E no extremo do dia (descartado por regra)
  4. 3º+ gatilho do dia  — só o 1º e o 2º gatilho de cada direção no dia
  5. fora do horário     — entrada fora de 10:00–15:55
  6. NWE50 contra        — ext50 ≤ −0,5 ou slope50 ≤ −0,5
  7. posição aberta      — já havia um trade em andamento (um por vez)
  8. ENTROU
Confere que o conjunto "ENTROU" é idêntico aos trades do core.
Uso: python research/div_master/v32/funil.py → results/funil_*.csv
"""
import os, sys, warnings
from collections import Counter, defaultdict
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DM = os.path.join(ROOT, "research", "div_master")
sys.path[:0] = [ROOT, os.path.join(DM, "especialistas"), os.path.join(DM, "carteira_v22")]
import pandas as pd
import modulo as M, bt
from core import especialista_v22 as E
from paridade_especialista import day_inputs
from research.div_wall.data import load_asset

OUT = os.path.join(HERE, "results")
STAGES = ["1 confirmação tarde", "2 sem gatilho Opção C", "3 super-confluência", "4 3º+ gatilho do dia",
          "5 fora de 10:00–15:55", "6 NWE50 contra", "7 posição já aberta", "8 ENTROU"]


def day_funnel(fb, walls, ex):
    c = E.CFG
    P = M.PARAMS["WIN"]
    levels = sorted(float(w["price"]) for w in walls if w.get("type") in M.LEVEL_TYPES and w.get("price") is not None)
    atr = M.atr_series(fb, P["tick"])
    cands = M.engine_v32(fb, levels, P, "common", atr=atr, opt=M.V32_PROD)
    trig, _ = M.triggers(fb, cands, P)
    best = {}                      # (dir, j) -> índice da etapa mais avançada alcançada
    for cd in cands:
        late = cd["conf"] > cd["j"] + M.COMMON["trig_max"]
        best[(cd["dir"], cd["j"])] = 0 if late else 1
    pos = {str(b["time"])[:5]: i for i, b in enumerate(ex)}
    seq = {1: 0, -1: 0}
    rows = []
    for x in trig:
        t = x["idx"]
        if t + 1 >= len(fb):
            continue
        key = (x["dir"], x["j"])
        s = seq[x["dir"]]
        seq[x["dir"]] += 1
        t_in = fb[t + 1]["time"]
        e = pos.get(t_in)
        if e is None or e < 1:
            continue
        rows.append(dict(key=key, e=e, tm=E._hm(t_in), d=int(x["dir"]), seq=s, super=bool(x["super"])))
    last_exit = -1
    traded = []
    sims = []
    for r in sorted(rows, key=lambda z: z["tm"]):
        e, d, key = r["e"], r["d"], r["key"]
        # "e se tivesse entrado": mesma entrada e mesma saída do especialista, ignorando os filtros e o 1 por vez
        rs = E._sim(ex, e, float(ex[e]["open"]), d, False)
        brl = round(((rs["px"] - float(ex[e]["open"])) * d - c["cost"]) * c["contracts"] * c["brl_pt"], 2)
        stage = 2
        if not r["super"]:
            stage = 3
            if r["seq"] <= 1:
                stage = 4
                if c["t_start"] <= r["tm"] < c["t_end"]:
                    stage = 5
                    n50 = float(ex[e - 1].get("nwe50_line") or 0.0)
                    u50 = float(ex[e - 1].get("nwe50_upper") or 0.0)
                    n50_old = float(ex[max(0, e - 7)].get("nwe50_line") or 0.0)
                    if n50 > 0 and u50 > 0:
                        half = max(u50 - n50, c["tick"])
                        ext = -d * (float(ex[e - 1]["close"]) - n50) / half
                        slope = d * (n50 - n50_old) / half
                        if ext > c["ext_min"] and slope > c["slope_min"]:
                            stage = 6
                            if r["tm"] > last_exit:
                                stage = 7
                                res = E._sim(ex, e, float(ex[e]["open"]), d, False)
                                last_exit = E._hm(ex[res["k"]]["time"])
                                traded.append(ex[e]["time"][:5])
        best[key] = max(best.get(key, 0), stage)
        sims.append(dict(stage=stage, brl=brl, tm=r["tm"]))
    out = []
    for cd in cands:
        out.append(dict(dir=cd["dir"], k=cd["k"], j=cd["j"], conf=cd["conf"], f1=fb[cd["k"]]["time"],
                        f2=fb[cd["j"]]["time"], conf_t=fb[cd["conf"]]["time"], lag=cd["conf"] - cd["j"],
                        anchor=("WALL+EXT" if (cd["c1"] is not None or cd["c2"] is not None) and cd["day"] is not None
                                else "WALL" if (cd["c1"] is not None or cd["c2"] is not None) else "EXTREMO"),
                        ext=bool(cd.get("ext")), stage=best[(cd["dir"], cd["j"])]))
    return out, traded, sims


def main():
    os.makedirs(OUT, exist_ok=True)
    DS = bt.market("WIN")
    data = load_asset("WIN", "M5")
    allc, allsim, check_bad, n_days = [], [], 0, 0
    for d in sorted(data):
        if d > bt.END or d not in DS:
            continue
        n_days += 1
        fb, walls, ex = day_inputs(DS, data, d)
        cs, traded, sims = day_funnel(fb, walls, ex)
        allsim += [dict(s, date=d) for s in sims]
        core = [t["time"] for t in E.run(fb, walls, ex)]
        if sorted(core) != sorted(traded):
            check_bad += 1
        for x in cs:
            x["date"] = d
        allc += cs
    C = pd.DataFrame(allc)
    C["etapa"] = C.stage.map(lambda s: STAGES[s])
    # marcação = uma por perna (o que o painel desenha): a perna entra se qualquer extensão entrou
    L = C.groupby(["date", "dir", "k"]).agg(stage=("stage", "max"), f1=("f1", "first"), f2=("f2", "last"),
                                           n_ext=("j", "size"), lag=("lag", "last"), anchor=("anchor", "last")).reset_index()
    L["etapa"] = L.stage.map(lambda s: STAGES[s])
    C.to_csv(os.path.join(OUT, "funil_divergencias.csv"), index=False)
    L.to_csv(os.path.join(OUT, "funil_marcacoes.csv"), index=False)
    print(f"pregões {n_days} · conferência com o core: {check_bad} dias diferentes")
    for name, T in (("MARCAÇÕES (1 por perna, como no painel)", L), ("DIVERGÊNCIAS (com extensões)", C)):
        print(f"\n{name}: {len(T)} ({len(T) / n_days:.1f}/dia)")
        cnt = Counter(T.etapa)
        for s in STAGES:
            print(f"   {s:24s} {cnt.get(s, 0):5d}  {100 * cnt.get(s, 0) / len(T):5.1f}%")
    L["hora"] = L.f2.str[:2]
    print("\nmarcações por hora do F2 × entradas:")
    g = L.groupby("hora").agg(marc=("stage", "size"), entrou=("stage", lambda s: int((s == 7).sum())))
    print(g.T.to_string())
    print("\natraso da confirmação (barras após o F2) nas marcações:", L.lag.describe()[["25%", "50%", "75%"]].to_dict())
    S = pd.DataFrame(allsim)
    S["etapa"] = S.stage.map(lambda s: STAGES[s])
    S.to_csv(os.path.join(OUT, "funil_e_se.csv"), index=False)
    print("\n'E se tivesse entrado' (mesma entrada/saída do especialista, cada gatilho isolado, R$ com 2 contratos):")
    for s, g in S.groupby("etapa"):
        p = g.brl
        gw, gl = p[p > 0].sum(), -p[p < 0].sum()
        print(f"   {s:24s} {len(g):4d} gatilhos · WR {100 * (p > 0).mean():4.1f}% · PF {gw / gl if gl else 99:4.2f} · "
              f"R$ {p.sum():8.0f} · média R$ {p.mean():6.1f}")


if __name__ == "__main__":
    main()
