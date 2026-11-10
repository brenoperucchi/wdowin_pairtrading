# Backtest das 11 estratégias com e sem filtros de Fluxo/Janela do dashboard

Período **11/05 a 04/11/2026**, 1 lote, custo R$ 2/ctr (WIN) e R$ 5/ctr (WDO).
Simuladores alinhados ao MT5 (mesmos validados trade a trade). Os filtros do dashboard
(`research/flow_window_asg/flow_filters.py`) são aplicados na barra de sinal, dentro do simulador.
IS = 11/05–31/08, OOS = 01/09–04/11.

Script: `research/flow_window_asg/backtest_11_flow_filters.py` · Dados: `data/reports/flow_filters_11/`

## Filtros testados
| Código | Filtro |
|---|---|
| 0 | Sem filtro (MT5) |
| 1 | Janela A.S.G a favor |
| 2 | Janela sem explosão contra |
| 3 | Fluxo institucional 5m/15m a favor |
| 4 | Fluxo ou absorção no pavio |
| 5 | Janela + fluxo/absorção (estrito) |
| 6 | Janela s/ explosão + fluxo/absorção (smart) |

## Por estratégia: sem filtro × melhor filtro
| Estratégia | Sem filtro (tr / R$ / PF / DD / Ret/DD) | Melhor filtro | Com filtro (tr / R$ / PF / DD / Ret/DD) | Veredito |
|---|---|---|---|---|
| EST-01 | 485 / 1.800 / 1,17 / 393 / 4,58 | 6 smart | 421 / 2.183 / 1,25 / 510 / 4,28 | filtro ajuda no R$ e PF (+383), IS e OOS positivos |
| EST-04 | 177 / 2.055 / 1,67 / 264 / 7,78 | — | igual | sem filtro |
| EST-07 | 319 / 1.662 / 1,23 / 553 / 3,01 | 2 | 310 / 1.799 / 1,26 / 553 / 3,25 | ganho marginal |
| EST-13 | 258 / 2.397 / 1,33 / 715 / 3,35 | — | filtros pioram | sem filtro |
| EST-14 | 284 / 4.146 / 1,56 / 559 / 7,42 | — | filtros pioram | sem filtro |
| EST-15 | 287 / 1.389 / 1,15 / 521 / 2,67 | 5 estrito | 130 / 1.579 / 1,45 / 448 / 3,52 | filtro melhora bem (OOS 786 × 209) |
| EST-16 | 221 / 1.681 / 1,25 / 828 / 2,03 | — | filtros pioram | sem filtro |
| WDO-02 | 342 / 3.640 / 1,31 / 545 / 6,68 | — | todos pioram | sem filtro |
| WDO-07 | 247 / 3.125 / 1,48 / 390 / 8,01 | — | todos pioram | sem filtro |
| WDO-09 | 183 / 2.440 / 1,38 / 860 / 2,84 | 1 janela | 91 / 1.770 / 1,59 / 725 / 2,44 | PF sobe, R$ cai |
| WDO-10 | 160 / 2.735 / 1,57 / 790 / 3,46 | 3 fluxo inst | 84 / 1.725 / 1,85 / 285 / 6,05 | DD cai muito, R$ cai; OOS pior |

## Carteira das 11 com o mesmo filtro em todas
| Filtro | Trades | R$ | DD | Ret/DD | Pior dia |
|---|---|---|---|---|---|
| Sem filtro | 2.963 | 27.070 | 2.009 | 13,47 | −1.179 |
| 4 fluxo/absorção | 2.428 | 18.450 | 1.320 | 13,98 | −1.179 |
| 5 combo estrito | 1.211 | 10.640 | 1.295 | 8,22 | −622 |
| 1 janela | 1.542 | 14.646 | 2.287 | 6,40 | −1.396 |
| Melhor filtro por estratégia | 2.739 | 26.103 | 2.155 | 12,11 | −1.179 |

## Melhor portfólio de até 3 estratégias por ativo
| Portfólio | Trades | R$ | PF | DD | Ret/DD | Pior dia | Ret/DD IS | Ret/DD OOS |
|---|---|---|---|---|---|---|---|---|
| **WIN: EST-01 [6 smart] + EST-04 + EST-14** | 882 | 8.384 | 1,44 | 529 | **15,85** | −340 | 8,97 | 8,14 |
| WIN: EST-01 + EST-04 + EST-14 (sem filtro) | 946 | 8.001 | 1,38 | 559 | 14,31 | −340 | 8,49 | 7,66 |
| **WDO: WDO-07 + WDO-09 + WDO-10 (sem filtro)** | 590 | 8.300 | 1,47 | 615 | **13,50** | −480 | 7,56 | 7,60 |
| WDO: WDO-07 + WDO-09 + WDO-10 [3 fluxo] | 514 | 7.290 | 1,49 | 615 | 11,85 | −465 | 7,57 | 4,83 |

## Consolidado WIN + WDO
| Carteira | Trades | R$ | PF | DD | Ret/DD | Pior dia | Dias + |
|---|---|---|---|---|---|---|---|
| 11 atuais sem filtro | 2.963 | 27.070 | 1,34 | 2.009 | 13,47 | −1.179 | 67,5% |
| 6 (01,04,14 + 07,09,10) sem filtro | 1.536 | 16.301 | 1,42 | 891 | 18,30 | −526 | 70,7% |
| **6 com fluxo só no EST-01** | 1.472 | 16.684 | 1,45 | 791 | **21,09** | −476 | 70,7% |


## Todas as estratégias × todos os filtros (colunas 0 a 6 = códigos dos filtros)

### Lucro líquido (R$, com custo)
| Estratégia | 0 sem filtro | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| EST-01 | 1.800 | 1.706 | 1.854 | 1.550 | 1.919 | 1.518 | **2.183** |
| EST-04 | **2.055** | 1.736 | 1.909 | 1.962 | **2.055** | 1.736 | 1.909 |
| EST-07 | 1.662 | 1.230 | **1.799** | 1.588 | 1.662 | 1.230 | **1.799** |
| EST-13 | **2.397** | 478 | 223 | 1.870 | **2.397** | 478 | 223 |
| EST-14 | **4.146** | 1.311 | 2.963 | 2.878 | **4.146** | 1.201 | 2.853 |
| EST-15 | 1.389 | 1.282 | 792 | 1.110 | 1.315 | **1.579** | 1.194 |
| EST-16 | **1.681** | 853 | 563 | 853 | **1.681** | 853 | 563 |
| WDO-02 | **3.640** | 2.105 | 2.630 | 640 | 790 | 975 | 1.115 |
| WDO-07 | **3.125** | 815 | 875 | 1.280 | 475 | 240 | 35 |
| WDO-09 | **2.440** | 1.770 | 1.300 | 900 | 690 | 770 | 475 |
| WDO-10 | **2.735** | 1.360 | 715 | 1.725 | 1.320 | 60 | 50 |

### Drawdown máximo (R$)
| Estratégia | 0 sem filtro | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| EST-01 | 393 | 369 | 401 | 541 | 610 | 418 | 510 |
| EST-04 | 264 | 307 | 361 | 264 | 264 | 307 | 361 |
| EST-07 | 553 | 490 | 553 | 553 | 553 | 490 | 553 |
| EST-13 | 715 | 584 | 885 | 947 | 715 | 584 | 885 |
| EST-14 | 559 | 465 | 825 | 782 | 559 | 465 | 825 |
| EST-15 | 521 | 448 | 732 | 738 | 521 | 448 | 732 |
| EST-16 | 828 | 442 | 683 | 891 | 828 | 442 | 683 |
| WDO-02 | 545 | 740 | 495 | 950 | 1.435 | 380 | 575 |
| WDO-07 | 390 | 480 | 585 | 480 | 640 | 270 | 580 |
| WDO-09 | 860 | 725 | 810 | 680 | 750 | 490 | 530 |
| WDO-10 | 790 | 460 | 1.060 | 285 | 390 | 260 | 370 |

### Retorno / Drawdown
| Estratégia | 0 sem filtro | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| EST-01 | 4,58 | **4,62** | **4,62** | 2,87 | 3,15 | 3,63 | 4,28 |
| EST-04 | **7,78** | 5,65 | 5,29 | 7,43 | **7,78** | 5,65 | 5,29 |
| EST-07 | 3,01 | 2,51 | **3,25** | 2,87 | 3,01 | 2,51 | **3,25** |
| EST-13 | **3,35** | 0,82 | 0,25 | 1,97 | **3,35** | 0,82 | 0,25 |
| EST-14 | **7,42** | 2,82 | 3,59 | 3,68 | **7,42** | 2,58 | 3,46 |
| EST-15 | 2,67 | 2,86 | 1,08 | 1,50 | 2,52 | **3,52** | 1,63 |
| EST-16 | **2,03** | 1,93 | 0,82 | 0,96 | **2,03** | 1,93 | 0,82 |
| WDO-02 | **6,68** | 2,84 | 5,31 | 0,67 | 0,55 | 2,57 | 1,94 |
| WDO-07 | **8,01** | 1,70 | 1,50 | 2,67 | 0,74 | 0,89 | 0,06 |
| WDO-09 | **2,84** | 2,44 | 1,60 | 1,32 | 0,92 | 1,57 | 0,90 |
| WDO-10 | 3,46 | 2,96 | 0,67 | **6,05** | 3,38 | 0,23 | 0,14 |

### Número de trades
| Estratégia | 0 sem filtro | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| EST-01 | 485 | 346 | 469 | 420 | 436 | 304 | 421 |
| EST-04 | 177 | 129 | 170 | 173 | 177 | 129 | 170 |
| EST-07 | 319 | 207 | 310 | 313 | 319 | 207 | 310 |
| EST-13 | 258 | 68 | 139 | 229 | 258 | 68 | 139 |
| EST-14 | 284 | 109 | 192 | 255 | 284 | 108 | 191 |
| EST-15 | 287 | 134 | 204 | 240 | 285 | 130 | 201 |
| EST-16 | 221 | 92 | 172 | 207 | 221 | 92 | 172 |
| WDO-02 | 342 | 165 | 247 | 206 | 177 | 66 | 117 |
| WDO-07 | 247 | 127 | 180 | 109 | 56 | 29 | 43 |
| WDO-09 | 183 | 91 | 134 | 120 | 119 | 47 | 83 |
| WDO-10 | 160 | 74 | 98 | 84 | 96 | 31 | 49 |
