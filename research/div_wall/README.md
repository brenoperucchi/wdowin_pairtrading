# Divergência Preço × Fluxo Smart Money na Wall — laboratório do zero (10/11/2026)

Setup independente dos EAs antigos: divergência F1→F2 / T1→T2 entre o preço e a onda de fluxo,
com o pivô F2 perto de uma Wall/MidWall GEX real. NWE fixa em período 100, bw 8, mult 3.

## Arquivos
| Arquivo | Papel |
| :-- | :-- |
| `core/div_wall_signal.py` | **Fonte única** de fluxo, detecção e simulação, usada pelo BT e pelo ao vivo (`run_session`). |
| `build_dataset.py` | Congela `data/research/div_wall_v1/` (só `.min` do Profit, walls do `jumba_gex_*_history.csv`, NWE aquecida no mesmo contrato). |
| `dataset_manifest.json` | Hash sha256 do dataset; o BT se recusa a rodar se o dado mudar. |
| `bt_grid.py` | Grade **só no IS (jan–jul)**, critérios pré-registrados, ranking por platô. |
| `parity_test.py` | Recalcula tudo barra a barra com `bars[:t+1]` e exige igualdade com o lote. |

## Regras de execução
- Sinal no fechamento da barra de confirmação, entrada na abertura da seguinte.
- Stop antes do alvo na mesma barra; gap preenche na abertura; BE só se a abertura seguinte passar do novo stop.
- Custo: WIN 10 pts/contrato (R$ 2), WDO 0,5 pt (R$ 5), mais 1 tick de slippage nos stops.
- Stop técnico acima do máximo → trade descartado (nunca truncado).

## Resultado da 1ª rodada (IS jan–jul/2026, 143 dias)
- 3.456 configs por ativo. Elegíveis (≥ 80 trades, PF ≥ 1,30): **WIN 1** (PF 1,32, Ret/DD 0,99), **WDO 0**.
- PF mediano da grade: WIN 0,77, WDO 0,64.
- Retorno médio à frente (1–12 barras) após a divergência na Wall é igual ao de qualquer pivô, com ou sem
  divergência, com ou sem Wall, e também com a onda **invertida**. Trocar a onda por CVD real (compra − venda),
  `inst_aggr` ou `inst_pass` não muda isso.
- Conclusão: com dado `.min` em M5, a divergência de fluxo em pivô não carrega informação sozinha.
  O OOS (ago–nov) **não foi aberto**.

## Paridade
`parity_test.py`: 4 configs × 25 dias por ativo, 100% de paridade. Um bug de olhar 1 barra à frente injetado
de propósito é detectado.

## Pendente
- Confirmar durante o pregão se o Profit atualiza o `.min` intraday (o ao vivo precisa do mesmo dado).
- Integrar `run_session` no `gex_live_dealer_engine.py` só quando algum setup passar no IS e no OOS.

---

# Fase B — M1 (10/11/2026)

## Novos arquivos
| Arquivo | Papel |
| :-- | :-- |
| `core/profit_min_decomp.py` | Decomposição de fluxo por minuto (mesmas fórmulas do motor). |
| `test_m1_decomp.py` | Prova que a soma dos minutos reproduz o M5 do motor: 0 lote de diferença em ~21 mil comparações. |
| `build_dataset_m1.py` | Dataset `div_wall_m1_v1` (211 dias WIN / 207 WDO). NWE 100/8/3 no M1, aquecida no contrato identificado pelos preços (o rótulo do índice vem do M5). |
| `core/div_wall_signal.py` → `detect_springs` | Spring/upthrust na Wall: furo entre `pierce_min` e `pierce_max` em até N barras, retomada no fechamento, filtro de fluxo opcional (`anti_force` = placebo). |
| `bt_grid_m1.py` | Grade IS para `div` e `spring`. Critério: >= 120 trades, PF >= 1,30. |
| `parity_test.py ... M1` | Paridade 100% nos dois detectores (4 configs × 6 dias por ativo). |

## Resultado IS (jan–jul)
| Grade | Configs | Elegíveis | PF mediano |
| :-- | --: | --: | --: |
| WIN M1 divergência | 6.912 | 0 | 0,89 |
| WIN M1 spring | 9.216 | 0 | 0,69 |
| WDO M1 divergência | 6.912 | 0 | 0,71 |
| WDO M1 spring | 9.216 | 0 | 0,56 |

- **Custo domina o M1.** WIN divergência: 66% das configs com >= 60 trades são positivas no bruto, mas o bruto
  mediano é R$ 0,72/trade, contra R$ 2 de custo. WDO: o custo de R$ 5 é maior que qualquer vantagem.
- **Spring/upthrust:** nenhuma vantagem. O filtro de fluxo não supera o placebo (`anti_force`).
- **Pista mais forte: dose-resposta na força da divergência.** O PF sobe de forma monotônica com `wave_k`
  nos dois ativos (WIN 0,84 → 0,98 → 1,21; WDO 0,66 → 0,71 → 0,79), mas o número de trades cai junto
  (WIN 144 → 54 no IS). Filtro de inclinação da NWE ≈ sem filtro.
- Pivôs M1 na Wall andam mais que pivôs fora dela (WDO +0,5 contra +0,2 pt em 20 min), mas é pouco para o custo.
- O OOS (ago–nov) continua fechado.

## Fase 2 — divergência forte (pré-registro em `PREREG_M1_FASE2.md`)
- 8.640 configs por ativo, `wave_k` 1,5 a 4,0, mínimo de 50 trades no IS.
- WIN: 205 elegíveis; PF mediano por k = 1,27 / 1,27 / 0,91 / 1,83 / 7,60, mas com 42 / 22 / 12 / 5 / 3 trades
  (acima de k = 2 é ruído). WDO: PF < 1 em todo k, nenhuma elegível.
- Config nº 1 do WIN (k 1,5, pivô 1, raio 40, só Wall, NWE contra a inclinação, stop no pivô, alvo 1,5R, BE 1R):
  IS 53 trades, PF 1,91, R$ +318, platô 1,93.
- **OOS (ago–nov), rodado uma vez em 10/11 22:09: 11 trades, PF 0,33, R$ −106, 0/3 meses positivos → REPROVADA.**
  Registro em `results/oos_log.json`; `run_oos.py` não deixa rodar de novo.
- Conclusão das Fases A/B: a divergência de fluxo do `.min` não sustenta um setup sozinha, nem em M5 nem em M1.
