# Pré-registro — entrar direto na divergência do Sniper (11/11/2026)

Motivo (`research/sniper_add/RESULTADOS.md`): 70–75% das divergências do detector do Sniper não têm entrada de
setup logo depois. Aqui a própria divergência vira o sinal de entrada.

## Sinal
- Barras do Profit da 5176 (mesmo cache e mesma onda dos 3 motores do Sniper), detector
  `detect_visual_swing_divergences` (F1→F2 / T1→T2), sinal no fechamento da barra `i`.
- Entrada na **abertura da barra seguinte** (`i+1`), preço de abertura da barra MT5 do mesmo horário.
- Filtro 3 motores na barra `i` (a barra anterior à entrada, igual ao Sniper): {não, sim}.
  WIN = fórmula do Sniper. WDO = mesma fórmula com os limiares na escala do próprio detector
  (preço × 0,03 → 30 pts = 0,9; −380..50 = −11,4..1,5; onda/Wyckoff × 0,12 → 1.200 = 144, 800 = 96).
- Wall: {não exige, exige `near_wall` do detector}.
- Janela fixa do Sniper: WIN 09:05–16:45, WDO 09:00–17:00.

## Saídas (as 20 do Sniper v2, regras MT5)
Stop {200, 260} WIN / {8, 10,5} WDO × alvo {banda oposta NWE30, próxima Wall/MidWall, fixo 450/10, fixo 750/16,
2 lotes NWE30 + 750/16} × BE {não, +180→+20 / +7→+1}. Na barra de entrada só conta o stop; stop antes do alvo;
gap preenche na abertura; máx. 24 barras; fecha 17:25; custos WIN 10 pts, WDO 0,5 pt por contrato.
(O "2 lotes SL 260 + BE" é a saída do Sniper 5176 com regras MT5.)

## Gestão
Sem almoço/NY {não, sim} (WIN 12:00–12:55, WDO 11:00–11:55) · meta diária causal {não, WIN R$ 90/contrato,
WDO R$ 120/contrato} · posição {LIVRE, UM_POR_VEZ}.

## Regras (congeladas)
1. Grade só em jan–jul (IS): 4 filtros × 20 saídas × 8 gestões = 640 por ativo. Score = Ret/DD trade a trade
   se ≥ 150 trades e lucro > 0.
2. Platô = mediana do score da config e das vizinhas (troca do stop, liga/desliga BE, liga/desliga Wall).
3. Por ativo, a config de maior platô. Placebo: 200 sorteios de barras quaisquer do IS (que passem no mesmo filtro
   3 motores, se ele estiver ligado), mesmo nº por (mês, direção), mesma saída e gestão; exige p < 0,10.
4. OOS ago–6/nov uma vez (trava `results/oos_log.json`). Aprovação: PF ≥ 1,3, lucro > 0, ≥ 3 de 4 meses +.
5. Depois do OOS (só relatório, sem nova escolha): entrada direta sozinha, Sniper 5176 corrigido, e os dois juntos
   (quando o Sniper já tem trade para a mesma divergência, fica o do Sniper).
