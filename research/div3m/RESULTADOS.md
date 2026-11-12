# Setup Divergência 3 Motores — resultados (11/11/2026)

Protocolo: `PLANO.md`. Script: `bt_div3m.py` (saídas tick a tick em M1, ordem do Strategy Tester "OHLC 1 minuto";
WDO sem M1 antes de 25/02 → barra M5 com stop primeiro). Grade IS: `results/grid_is_{WIN,WDO}.csv.gz` (122.880 por
ativo). OOS (uma vez): `results/oos_log.json` · trades: `results/trades_escolhas.csv`.

## Setups escolhidos em jan–jul
| | WIN | WDO |
| :-- | :-- | :-- |
| Sinal | divergência 3 motores (F1→F2 / T1→T2) | idem |
| Filtros | TEND (não contra NWE50 forte) + FLUXO (inst/varejo fora do quartil mais a favor) + HORA (sem 9h) | PA (corpo da barra do sinal contra o trade) + HORA + SEQ (não a 1ª do dia) |
| Entrada | E1 stop 1 tick além da máx./mín. da barra do sinal, vale 2 barras | E2 limite no meio da barra do sinal, vale 3 barras |
| Saída | SL 260 · alvo banda oposta NWE50 · sem BE · sem trailing · máx 24 barras | SL 10,5 · alvo 16 · sem BE · sem trailing · máx 48 barras |
| Gestão | uma por vez · meta R$ 90 | livre · sem meta |
| Platô IS · placebo divergência · placebo barra | 5,16 · p 0,005 · p 0,005 | 3,58 · p 0,005 · p 0,005 |

## Resultados (1 contrato, líquido)
| | Período | Trades | WR | PF | Lucro R$ | DD R$ | Ret/DD | Meses + |
| :-- | :-- | --: | --: | --: | --: | --: | --: | :-: |
| WIN | jan–jul | 179 | 41,3 | 1,50 | 2.586 | 432 | 5,99 | 7/7 |
| WIN | ago–6/nov | 78 | 32,1 | 1,11 | 308 | 584 | 0,53 | 2/4 |
| WIN | completo | 257 | 38,5 | 1,37 | 2.894 | 584 | 4,96 | 9/11 |
| WDO | jan–jul | 344 | 52,9 | 1,34 | 4.070 | 860 | 4,73 | 5/7 |
| WDO | ago–6/nov | 144 | 45,1 | 1,08 | 445 | 1.090 | 0,41 | 2/4 |
| WDO | completo | 488 | 50,6 | 1,26 | 4.515 | 1.620 | 2,79 | 7/11 |
| Carteira | completo | 745 | 46,4 | 1,29 | 7.409 | 1.476 | 5,02 | 8/11 |
| Carteira | ago–6/nov | 222 | 40,5 | 1,09 | 753 | 1.152 | 0,65 | 2/4 |

Aprovação OOS (PF ≥ 1,3, ≥ 3/4 meses): **nenhum dos dois**. No top 5 do IS de cada ativo, nenhum passaria no OOS.

## M1 x regra M5
WIN escolhido no período completo: R$ 2.894 (PF 1,37) com M1 contra R$ 258 (PF 1,03) com "stop primeiro" em M5.
WDO: igual nas duas regras (stop 10,5 / alvo 16 quase nunca caem na mesma barra M5).

## Junto com o Sniper 5176 corrigido (período completo)
1.032 trades · PF 1,44 · R$ 14.845 · DD R$ 1.162 · Ret/DD 12,8 · 10/11 meses (ago–nov: PF 1,35, Ret/DD 4,8).
O Sniper sozinho: PF 1,95 · R$ 7.436 · DD R$ 524 · Ret/DD 14,2.
