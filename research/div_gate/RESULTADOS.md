# Gate de divergência v2 — resultados (11/11/2026)

Protocolo: `PLANO.md`. Arquivos: `results/grid_is.csv` (17.051 BTs IS), `results/grid_is_plateau.csv`,
`results/oos_log.json` (trava, escolhas, placebo, resultado), `results/oos_versions.csv`, `results/oos_trades.csv`.
Fase 0 v2: 3.504 cortes barra a barra, 0 diferenças. Grade v1 descartada (definição antiga + tolerância do WIN no WDO).

## Funil
| Etapa | Versões |
| :-- | --: |
| Testadas | 31 |
| (a) platô IS ≥ 1,2 × base | 24 |
| (b) placebo p < 0,10 e (c) invertido não atinge a marca | 14 |
| OOS aprovado (PF ≥ 1,2, lucro > 0, ≥ ½ meses +, Ret/DD OOS ≥ melhor base OOS) | **6** |

Aprovadas no OOS: EST_07 e EST_07_EA (EXIGIR), EST_01 (EXIGIR + filtro atual), WIN_S10 (EXIGIR), WIN_E2 (VETAR +
filtro atual), WDO_S13 (EXIGIR, FECHA_WALL). Amostras OOS pequenas: 10 a 52 trades.

Nenhum gate do WDO registrado passou no placebo (WDO_01/02/05/07/09/10): no WDO o efeito não se separa de
cortar trades ao acaso. EST_13 e EST_14 passaram no IS, mas no OOS a versão sem filtro foi melhor.

## Carteiras (1 contrato, líquido, dias cobertos pelo gate)
| Carteira | IS Ret/DD | OOS trades | OOS PF | OOS lucro | OOS DD | OOS Ret/DD |
| :-- | --: | --: | --: | --: | --: | --: |
| Escolhida no IS (15 famílias, 9 com gate) | 22,4 | 1.158 | 1,49 | 14.257 | 1.291 | 11,0 |
| 8 Elite sem filtro | 6,4 | 1.252 | 1,46 | 15.653 | 1.034 | 15,1 |
| 8 Elite com os gates aprovados no IS | 11,7 | 955 | 1,42 | 11.370 | 1.109 | 10,3 |

O OOS ago–nov das entradas já tinha sido visto antes deste teste; vale para comparar gate × sem gate, não para
eleger carteira. Próximo passo antes de qualquer mudança no MT5: papel ao vivo (fase 5).

## Painel "só divergência" (toda entrada exige divergência v2 na Wall) — `portfolio_div.py`
22 candidatas (melhor regra EXIGIR por família no IS, ≥ 40 trades IS). Combinação escolhida só no IS (gulosa por
Ret/DD): EST_07, EST_16, WIN_E2, EST_04, EST_13, WDO_07, WDO_10, WIN_S02, EST_01. OOS rodado uma vez
(`results/oos_log_portfolio_div.json`).

| Carteira | IS trades | IS Ret/DD | OOS trades | OOS PF | OOS lucro | OOS DD | OOS Ret/DD | OOS meses + |
| :-- | --: | --: | --: | --: | --: | --: | --: | :-: |
| 9 escolhidas (só divergência) | 491 | 29,9 | 199 | 1,45 | 1.927 | 821 | 2,35 | 2/4 |
| 22 candidatas (só divergência) | 1.570 | 7,1 | 593 | 1,24 | 3.786 | 2.660 | 1,42 | 3/4 |
| 8 Elite sem filtro | 3.026 | 6,4 | 1.252 | 1,46 | 15.653 | 1.034 | 15,1 | 4/4 |

Conclusão: o Ret/DD 29,9 do IS não se sustentou (2,35 no OOS). Com ~50 trades por estratégia em 7 meses, a
escolha da combinação no IS ficou sobreajustada.
