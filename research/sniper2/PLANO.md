# Pré-registro — Sniper v2: entradas de todos os setups + divergência + saída própria (11/11/2026)

Ideia tirada da auditoria da 5176 (`research/audit_5176/AUDITORIA.md`): a divergência funciona como filtro
quando a amostra é a **união das entradas de todos os setups**. Aqui a ideia é refeita do jeito certo e com
variações, para ver se a vantagem melhora.

## Pool de entradas
As 31 versões de `research/div_gate/versions.py`, simuladas pelo runner (regras MT5), nos 211 dias do dataset
`div_wall_v1`, em **dois pools** testados separadamente: sem filtro de fluxo, e com o filtro de fluxo atual de
cada versão (o Sniper da 5176 usa os trades do JSON, que já são as versões com filtro de fluxo). Por ativo, entradas únicas por (data, horário, direção); se duas versões
entram junto, fica a primeira da lista (ordem fixa do arquivo). Guarda horário, preço de entrada e o resultado
da saída original.

## Filtros de divergência (sempre só até a barra ANTERIOR à entrada — sem barra do futuro)
| Filtro | Parâmetros |
| :-- | :-- |
| F0 nenhum (controle: só o pool) | — |
| F1 detector do Sniper 5176 (`detect_visual_swing_divergences`) | tol {1, 2, 3} barras · Wall {não exige, exige} |
| F2 divergência v2 (tabela `div_gate_v2`) | k {0,5 1,0 1,5} · R · NWE L {30,50,80,100} · confirmação {PIVO, FECHA_WALL} · janela N {3, 6, 12} |

## Saídas (iguais para todo o pool; barras MT5; stop antes do alvo; gap preenche na abertura; BE só se a
abertura seguinte passar; na barra de entrada só conta o stop; máx. 24 barras; fecha 17:25; custos WIN 10 pts
por contrato, WDO 0,5 pt)
| | WIN | WDO |
| :-- | :-- | :-- |
| Stop | 200 · 260 pts | 8 · 10,5 pts |
| Alvo | banda oposta NWE30 (260–750) · próxima Wall/MidWall · fixo 450 · fixo 750 · 2 lotes (NWE30 + 750) | banda oposta NWE30 (5–16) · próxima Wall/MidWall · fixo 10 · fixo 16 · 2 lotes (NWE30 + 16) |
| Break-even | não · +180 → +20 | não · +7 → +1 |
| Saída original do setup | também testada (NATIVA) | também testada (NATIVA) |

## Gestão (opções da grade)
Horário: {sem corte, sem 12:00–12:55 WIN / 11:00–11:55 WDO} · Meta diária causal: {não, WIN R$ 90 por contrato /
WDO R$ 120} (só soma trades com saída ANTES da entrada) · Posição: {LIVRE, UM_POR_VEZ}.

## Regras (congeladas)
1. Grade só no IS (jan–jul). Score = Ret/DD trade a trade se ≥ 150 trades e lucro > 0.
2. Platô = mediana do score da config e das vizinhas de 1 parâmetro (parâmetros do filtro e o stop).
3. Por ativo: a config de maior platô. Placebo: 200 sorteios do mesmo nº de entradas do pool por (mês, direção),
   mesma saída e gestão; exige p < 0,10. Também se reporta a melhor config SEM divergência (F0) para medir o ganho.
4. OOS ago–6/nov uma vez (trava `results/oos_log.json`). Aprovação: PF ≥ 1,3, lucro > 0, ≥ 3 de 4 meses +.
5. As regras 1–4 valem para cada (ativo, pool). Carteira = melhor WIN + melhor WDO pelo platô do IS. Comparação: Sniper 5176 corrigido (auditoria, versão B) e 8 Elite.
