# Sniper v2 — resultados (11/11/2026)

Protocolo: `PLANO.md`. Grades IS: `results/grid_is_{WIN,WDO}_{sem_fluxo,com_fluxo}.csv` (25.368 linhas cada).
OOS (uma vez): `results/oos_log.json`, `results/oos_trades.csv`.

## Escolhas do IS (maior platô) e OOS
| Ativo · pool | Escolha | Regra | IS Ret/DD | OOS trades | OOS PF | OOS R$ | OOS DD | OOS Ret/DD | OOS meses |
| :-- | :-- | :-- | --: | --: | --: | --: | --: | --: | :-: |
| WIN · sem fluxo | com divergência | v2 k0,5 R100 L50 N6 · SL200 próxima Wall + BE · 1 por vez | 13,2 | 105 | 1,74 | 1.359 | 760 | 1,79 | 3/4 |
| WIN · sem fluxo | sem divergência | SL200 próxima Wall + BE · sem almoço · meta | 12,0 | 534 | 1,40 | 4.130 | 1.442 | 2,86 | 3/4 |
| WIN · com fluxo | com divergência | v2 k0,5 R100 L100 N6 · SL260 fixo 450 · meta | 12,3 | 90 | 1,51 | 1.269 | 401 | 3,16 | 4/4 |
| WIN · com fluxo | sem divergência | SL200 próxima Wall + BE · sem almoço · meta | 17,4 | 391 | 1,50 | 3.486 | 913 | 3,82 | 3/4 |
| WDO · sem fluxo | com divergência | v2 k1,5 R4 L100 N12 · saída original · sem 11h | 15,4 | 80 | 1,98 | 1.960 | 695 | 2,82 | 3/4 |
| WDO · sem fluxo | sem divergência | SL8 fixo 10 + BE · meta | 7,8 | 458 | 1,51 | 6.510 | 1.170 | 5,56 | 4/4 |
| WDO · com fluxo | com divergência | v2 k1,5 R4 L30 FECHA_WALL N12 · SL10,5 NWE30 · sem 11h | 21,1 | 81 | 1,46 | 940 | 620 | 1,52 | 3/4 |
| WDO · com fluxo | sem divergência | SL8 fixo 10 + BE · meta | 8,5 | 408 | 1,49 | 5.595 | 1.185 | 4,72 | 3/4 |

Placebo (IS) das escolhas com divergência: p ≤ 0,01 nas quatro.

## Carteiras (melhor WIN + melhor WDO pelo platô do IS)
| Carteira | IS trades | IS Ret/DD | OOS trades | OOS PF | OOS R$ | OOS DD | OOS Ret/DD | OOS meses |
| :-- | --: | --: | --: | --: | --: | --: | --: | :-: |
| Com divergência (WIN sem fluxo + WDO com fluxo) | 401 | 33,3 | 186 | 1,59 | 2.299 | 1.029 | 2,23 | 3/4 |
| **Sem divergência (WIN com fluxo + WDO com fluxo)** | 1.838 | 18,1 | 799 | 1,49 | **9.081** | **820** | **11,07** | **4/4** |
| Sniper 5176 corrigido (auditoria, versão B) | 212 | 9,0 | 75 | 2,79 | 2.700 | 428 | 6,31 | 4/4 |
| 8 Elite sem filtro (referência; OOS já visto antes) | 3.026 | 6,4 | 1.252 | 1,46 | 15.653 | 1.034 | 15,1 | 4/4 |

## Conclusão
- O filtro de divergência repete o padrão: Ret/DD altíssimo no IS (33,3, igual ao painel) e 2,2 no OOS.
  Com 144 variações do filtro, a escolha no IS se encaixa no passado, mesmo passando no placebo.
- A vantagem que se sustenta vem de **juntar as entradas dos setups (com o filtro de fluxo atual) e aplicar uma
  saída única**: SL 200 + alvo na próxima Wall + BE no WIN; SL 8 + alvo fixo 10 + BE no WDO; meta diária e sem
  almoço no WIN. OOS: 799 trades, PF 1,49, R$ 9.081, DD R$ 820, Ret/DD 11,1, 4/4 meses.
