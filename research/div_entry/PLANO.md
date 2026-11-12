# Pré-registro — entradas próprias com divergência v2 (11/11/2026, antes de rodar)

Pergunta: a divergência v2 (definição de 11/11) ou a absorção rápida na Wall, usadas como **sinal de entrada**
(sem robô por baixo), com mais um filtro, se sustentam em BT com IS/OOS? O OOS ago–nov nunca foi olhado para
estas entradas.

## Entradas (M5, `.min` do Profit + Walls reais, dataset `div_wall_v1`, entrada na abertura da barra seguinte)
| Família | Regra | Parâmetros |
| :-- | :-- | :-- |
| E1 DIV_NWE | divergência v2 (sem filtro NWE no detector) + F2 afastado do centro da NWE ≥ z × meia banda, do lado certo | k {0,5 1,0 1,5} · R WIN {40,100} WDO {1,5 4,0} · L {30,50,80,100} · confirmação {PIVO, FECHA_WALL} · z {0,5 0,8 1,0} |
| E2 ABS_DIV | absorção rápida na Wall + divergência v2 (NWE "extreme", PIVO) na mesma direção nas últimas N barras | k · R · L · N {3,6,12} |
| E3 ABS_DIV_NWE | E2 + extremo da barra de absorção afastado da NWE ≥ z | k · R · L · N · z |
| E4 ABS (controle) | absorção rápida na Wall sozinha | R |

Absorção rápida: extremo da barra a até R de uma Wall/MidWall, fechamento do lado defendido do nível,
`wyckoff_abs` a favor, `inst_pass_delta` a favor e `ret_delta_bar` contra. Janela de entrada 09:15–17:00.

## Saídas (`core.div_wall_signal.simulate_trade`, regras MT5, custos WIN 10 pts / WDO 0,5 pt, 1 contrato)
stop {atrás do pivô, atrás da Wall} (descarta se > 300 pts WIN / 10 pts WDO) × alvo {1,5R, 2R, próxima Wall,
centro da NWE} × BE {não, em 1R} · máx. 24 barras · saída 17:30.

## Modo de posição (pedido do usuário): os dois são reportados
- LIVRE: todo sinal vira trade (posições podem se sobrepor).
- UM_POR_VEZ: só entra se a posição anterior da mesma configuração já saiu (mesmos trades, filtrados).

## Regras (congeladas)
1. Grade só no IS (jan–jul). Score = Ret/DD se ≥ 150 trades no IS e lucro > 0; senão 0.
2. Platô = mediana do score da config e das vizinhas de 1 parâmetro de sinal (mesma saída e modo).
3. Escolha: a config de maior platô por (ativo, família, modo).
4. Placebo: 200 sorteios de entradas em barras que tocam a Wall e fecham do lado defendido (sem fluxo), mesmo
   número de trades por mês e direção, mesma saída. Exige p < 0,10.
5. OOS ago–6/nov **uma vez** (trava `results/oos_log.json`) para as escolhas com platô > 0 e placebo OK, e para
   o controle E4 como referência. Aprovação: PF ≥ 1,20, lucro > 0, ≥ metade dos meses positivos.
