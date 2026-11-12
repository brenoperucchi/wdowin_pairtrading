# Paridade dos setups registrados: motor ao vivo × BT (10/11/2026)

`compare_live_vs_bt.py` roda `GexLiveDealerEngine.analyze_asset` em cada dia de
`gex_historical_sessions_v1` (cache de trades desligado, sem reconciliação MT5) e casa trade a trade com os
trades `in_flow` de `portfolio_4_sistematicas_equity_v1.json` por (data, estratégia, direção, horário).
Resultado completo em `results/summary_live_vs_bt.csv` e `results/trades_live_vs_bt.csv`.

## Resultado (207 dias)
| Estratégia | BT | Ao vivo | Casados | % | Saída igual |
| :-- | --: | --: | --: | --: | --: |
| EST_14 | 289 | 267 | 245 | 85 | 93 |
| WIN_E2 | 219 | 225 | 184 | 82 | 152 |
| WDO_07 | 297 | 235 | 211 | 71 | 52 |
| EST_07 | 122 | 73 | 51 | 42 | 39 |
| WDO_01 | 622 | 287 | 134 | 22 | 14 |
| WDO_05 | 660 | 266 | 115 | 17 | 14 |
| EST_15 | 386 | 102 | 14 | 4 | 5 |
| EST_01 | 676 | 42 | 4 | 1 | 2 |
| EST_04 | 320 | 266 | 2 | 1 | 0 |
| EST_13 | 211 | 6 | 2 | 1 | 1 |
| WDO_10 | 139 | 1 | 1 | 1 | 0 |
| WDO_02 | 471 | 59 | 0 | 0 | 0 |
| EST_16 | 349 | 0 | 0 | 0 | — (não existe no ao vivo) |
| WDO_09 | 74 | 0 | 0 | 0 | — (não existe no ao vivo) |

## Causas encontradas
1. **Preço não é a causa:** barras M5 do Profit e do MT5 têm OHLC idêntico (WDO 100%, WIN 95,8% dos fechamentos).
2. **Bug no BT, filtros de fluxo 12–18 desligados:** `flow_filters.load_flow_tables` pula o JSON do Profit em todo
   dia coberto pelo `mt5_tick_flow_tables_2026.pkl`, mas o `.pkl` só tem os filtros 1–11. Os filtros 12–18
   (`NR_*`, usados por EST_01/04/07/14/15/16, WIN_E2, WDO_01/02/05/07/09) ficam com dado em **1 dia** por ativo e
   `make_sig_filter` libera barra sem dado. Na prática o BT atual roda esses setups **sem filtro de fluxo**,
   enquanto o ao vivo aplica as condições `NR_*` inline.
3. **O `.pkl` de fluxo MT5 não é reproduzível:** nenhum script do repositório o gera.
4. **O ao vivo é uma reimplementação separada:** EST_16 e WDO_09 não existem nele; EST_04 do BT usa alinhamento com o
   WDO (`simulate_aligned_win_wdo_slot`) e o ao vivo usa outra regra; EST_01/13/15 e WDO_02/10 geram muito menos sinais.
5. **Execução diferente da regra MT5 no ao vivo:** stop preenche no preço mesmo com gap, BE não exige a abertura
   seguinte além do novo stop, pontos sem custo.
6. **Metadados de janela no JSON estão errados** (ex.: EST_01 "15:00–16:40", mas o BT opera 10:00–16:35).

## Caminho proposto
1. Uma fonte de fluxo para BT e ao vivo (proposta: `.min` do Profit, a mesma do laboratório `div_wall`).
2. Uma implementação por setup: o ao vivo chama a mesma função de sinal/execução dos simuladores alinhados ao MT5.
3. Teste de paridade incremental (barra a barra), como `research/div_wall/parity_test.py`.
4. Só então: o gatilho de divergência F1/T1 na Wall por cima, com pré-registro e OOS.

---

# Unificação (10/11/2026, fonte de fluxo: `.min` do Profit)

## O que mudou
| Arquivo | Mudança |
| :-- | :-- |
| `research/setup_parity/build_flow_min.py` | Gera os 18 filtros de fluxo do `.min` para 234 dias (WIN e WDO), com hash em `flow_min_manifest.json`. |
| `research/flow_window_asg/flow_filters.py` | `load_flow_tables("min")` é o padrão (o caminho antigo virou `legacy`); `make_sig_filter` agora é **estrito**: barra sem dado bloqueia. |
| `research/mt5_loader.py` | Corte único de dados: `set_bar_cutoff(T)` (só barras fechadas até T), `set_bar_floor`, `set_live_extension` (barras do pregão via MT5). |
| `research/optimizers/wdo_mt5_sim.py`, `sg_sim.py` | `EMIT_OPEN_AT_END` (desligado no BT): emite a posição aberta quando os dados acabam no meio do pregão. |
| `core/setups_runner.py` | **Runner único** dos 14 setups: os mesmos simuladores do BT, com corte opcional. |
| `core/setups_live.py` | Ponte para o motor: dia passado = BT; pregão corrente = barras MT5 até agora + fluxo `.min` do dia + corte na última M5 fechada. Barras MT5 incompletas → erro, nunca opera com buraco. |
| `core/gex_live_dealer_engine.py` | O modo campeão passa a usar `_get_setup_trades` (runner) no histórico e ao vivo. A reimplementação `_evaluate_live_mt5_*_strategies` não é mais chamada. Sniper legado (`*_DIV_WALL`) preservado. |

## Testes
- `test_runner_causal.py`: cortes a cada 15 min (6 dias, 138 trades) e a cada barra M5 (4 dias, 85 trades) → **100%**.
  Sem trade "do futuro", sem saída diferente, sem trade fechado ausente.
- `compare_live_vs_bt.py all runner`: motor ao vivo × BT do runner, 207 dias, **4.815 trades, 100%** em todas as 14
  estratégias (entrada e saída idênticas). Antes: de 0% a 85% por estratégia.
- Caminho ao vivo real em 10/11 (barras MT5 de hoje + `.min` de hoje): corte 15:00 mostra WDO_10 das 13:20 `ABERTA`;
  corte 17:00 mostra o mesmo trade fechado às 15:20.

## BT novo (`bt_setups_runner.py`, jan–6/nov, 1 contrato, líquido)
Bate com o JSON de produção dentro de poucos trades (ex.: EST_01 683 × 685, PF 1,18 × 1,18), então o JSON foi gerado
antes do `.pkl` existir e **não** foi afetado pelo bug. O bug atingiria qualquer regeneração com o código antigo.
Maior diferença: WDO_10 (PF 1,90 × 2,17; R$ 3.740 × 4.480). WIN_E2 não está no `all_11_comparison` do JSON.
Consultas de fluxo sem dado: 0. Resultado completo em `results/bt_runner_2026_summary.csv`.

## Pendências
- O motor ao vivo só usa o código novo depois de reiniciar o `server.py`. A 1ª chamada do dia leva ~17 s (cache frio),
  depois ~2 s por barra, dentro da requisição (ainda não em thread de fundo).
- Confirmar no pregão que o `.min` do Profit é atualizado intraday. Se não for, o filtro estrito bloqueia as
  entradas dos setups com filtro de fluxo, e `setups_live.LAST_STATUS["flow_bars_min"]` mostra isso.
- O JSON de produção (`portfolio_4_sistematicas_equity_v1.json`) não foi regenerado.
