# Entrada direta na divergência do Sniper — resultados (11/11/2026)

Protocolo: `PLANO.md`. Grades IS: `results/grid_is_{WIN,WDO}.csv` (640 linhas). OOS (uma vez): `results/oos_log.json`,
`results/oos_trades.csv`. Comparação: `compare.py`.

Observação: o filtro 3 motores aprova 99–100% das divergências (a própria divergência já exige os motores a favor);
como filtro de entrada ele não muda nada aqui.

## Escolhas do IS e OOS
| Ativo | Escolha (maior platô) | IS trades | IS PF | IS R$ | IS Ret/DD | Placebo p | OOS trades | OOS PF | OOS R$ | OOS Ret/DD | OOS meses | Aprovado |
| :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | :-: | :-: |
| WIN | sem exigir Wall · SL 260 alvo 750 · meta · 1 por vez | 384 | 1,19 | 2.480 | 2,47 | 0,04 | 179 | 0,89 | −707 | −0,45 | 1/4 | não |
| WDO | exige Wall · SL 8 alvo 16 · sem 11h · meta | 473 | 1,04 | 670 | 0,43 | 0,015 | 201 | 1,22 | 1.535 | 2,16 | 3/4 | não |

Na grade IS, nenhuma das 640 configs de cada ativo chegou a PF 1,3 (WIN: 65 com lucro; WDO: 40 com lucro).
O placebo passa (barras sorteadas perdem dinheiro), então a divergência tem informação — mas sozinha não paga os custos.

## Comparação (período completo, relatório pós-OOS)
| | Trades | PF | Lucro R$ | DD R$ | Ret/DD | IS Ret/DD | OOS Ret/DD | Meses + |
| :-- | --: | --: | --: | --: | --: | --: | --: | :-: |
| Entrada direta | 1.237 | 1,09 | 3.978 | 1.889 | 2,1 | 1,8 | 0,7 | 7/11 |
| Sniper 5176 corrigido | 287 | 1,95 | 7.436 | 524 | 14,2 | 9,0 | 6,3 | 10/11 |
| Sniper + entrada direta nas divergências sem trade do Sniper | 1.367 | 1,26 | 11.755 | 1.599 | 7,4 | 5,1 | 6,1 | 9/11 |

## Conclusão
A vantagem do Sniper vem da **combinação** entrada de setup + divergência. Entrar em toda divergência quadruplica os
trades, mas o PF cai para 1,1 e o DD triplica. Somar as entradas diretas ao Sniper dá mais lucro, mas piora o Ret/DD
(14,2 → 7,4).
