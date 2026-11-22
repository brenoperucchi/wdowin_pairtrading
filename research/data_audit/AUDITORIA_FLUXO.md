# Auditoria da cobertura dos dados de fluxo — 2026

**Data da auditoria:** 13/11/2026 (America/Sao_Paulo).
**Escopo:** pregões B3 de 02/01 a 13/11/2026, WIN e WDO. Somente leitura das fontes; este arquivo e o CSV são os únicos arquivos novos.

## 1. O que é “dado de fluxo” neste projeto

Há três camadas, e elas não têm a mesma qualidade:

1. **Agressão compradora/vendedora** (`buy_qty` / `sell_qty`) nos arquivos `.min` do Profit. Isso é o volume agressor da B3 gravado na barra M1/M5. O Profit guarda esse histórico no contrato; **não depende** de o coletor ter ficado ligado o pregão inteiro. RLP é o residual `qty_vol - buy_qty - sell_qty`.
2. **Decomposição institucional / passivo / varejo / HFT** (`inst_aggr_delta`, `inst_pass_delta`, `ret_delta_bar`). Fora dos dias com `.trd`, isso **não é o tape**. É a fórmula de `core/profit_min_decomp.py` e `core/profit_wall_players_engine.py`: tamanho médio do lote + formato do candle (pavios). A onda “Fluxo Smart Money” dos backtests e do rotulador sai daqui. Cerca de 45% da onda é volume × formato do candle.
3. **Times & Trades nativo (`.trd`)**. Aí sim há corretora, flag de RLP, agressão vs passivo no negócio. Só existe nos dias em que o Profit/Scalper gravou o tape (e com tamanho mínimo de ~150 KB). No motor, se o arquivo estiver ausente ou curto demais, a sessão cai para o `.min`.

O painel ao vivo (5176 / motor Profit+MT5) usa a mesma hierarquia: `.trd` se estiver no disco, senão `.min`, com fallback de barras MT5 no pregão corrente. O cache `data/profit_broker_flow_cache.json` só tem 11 pregões recentes (27/10 a 11/11), fonte `PROFIT_TRD_NATIVE`.

Os backtests do especialista v2.2, do setup extra v3.2, do motor v2.1 e do rotulador leem o dataset congelado `data/research/div_wall_v1` (“`.min` do Profit, hash verificado”, **sem `.trd`**). Mesmo nos poucos dias em que o tape existe, o backtest usa a decomposição do `.min`.

Há um estoque paralelo, `data/processed/gex_historical_sessions_v1` (211 JSONs). Ele nasceu de um backfill por ticks do MT5 (`research/flow_window_asg/backfill_flow_sessions_2026.py`) e depois foi atualizado por `backfill_profit_sessions_2026.py` para a decomposição Profit (`.trd` quando havia, `.min` no resto). O dashboard antigo de fluxo (5174/filtros) usou essa base. **Não é a base do especialista atual.**

O banco `rastro_irado/data/irai_live.db` guarda barras MT5 (`WIN$N`/`WDO$N`, fonte `br`) e snapshots do IRAI. O M1 de WIN nesse banco só começa em 29/05/2026. Não é a fonte dos backtests de divergência nem da onda Smart Money do 5176.

## 2. Calendário e buracos

O arquivo `mt5/Files/jumba_gex_win_history.csv` lista 224 datas entre 02/01 e 13/11, mas **7 não são pregão B3**: 23/05 e 29/08 (sábado), 01/11 (domingo), e os feriados 04/06 (Corpus Christi), 07/09 (Independência), 12/10 (N. Sra. Aparecida) e 02/11 (Finados). Nessas datas não há `.min`, nem MT5, nem sessão. O CSV marca `is_b3_trading_day=0`.

O calendário limpo tem **217 pregões**. Nestes:

- `.min` WIN e WDO (M1 ou M5, 09:00–18:25): **216 dias**. Só falta o 13/11, que ainda não estava gravado no arquivo anual do contrato (o `WINZ26`/`WDOZ26` `.min` foi escrito de manhã, antes do pregão).
- `div_wall_v1` WIN: **213 dias**. Ficaram de fora: 18/02 e 31/07 (sessões incompletas, já no manifesto), 12/11 (o dataset foi congelado em 11/11) e 13/11.
- `div_wall_v1` WDO: **211 dias**. Além dos mesmos, faltam 01/09 e 04/09 (`.min` curto ou inconsistente).
- Sessões JSON: **211 dias** até 12/11. Faltam, entre pregões reais, 06/01, 13/05, 27/07, 31/07, 04/09 e 13/11. Os quatro primeiros com `.min` completo (06/01, 13/05, 27/07 e o WIN de 04/09) **estão no `div_wall_v1`** — o buraco é só do arquivo de sessão, não do backtest atual. 06/01, 13/05 e 27/07 até têm `.trd` de WIN no disco (~107–143 MB) que a sessão nunca chegou a usar.

O manifesto do `div_wall_v1` já registrava os dois pregões pulados por sessão incompleta no WIN: **18/02 (65 barras M5, 325 M1)** e **31/07 (71 barras M5, 351 M1)**.

## 3. Cobertura por classe (217 pregões B3 reais)

Classes usadas no CSV:

- `trd_completo`: sessão montada com `.trd` e barras quase completas.
- `trd_parcial`: `.trd` usado, mas o tape não cobre o pregão inteiro (Profit fechado no meio da tarde).
- `min_decomp`: agressão real do `.min` + decomposição sintética dos players; sessão (ou dataset de backtest) completa.
- `min_parcial`: há `.min`, mas a sessão está curta ou ficou de fora do dataset de backtest.
- `mt5_reconstruido`: fluxo reconstruído por ticks/regras do MT5, sem Profit na sessão.
- `ausente`: pregão real ainda sem fonte de fluxo arquivada (hoje, 13/11).

**WIN (ano, 217 pregões):** tape completo 7 (3,2%), tape parcial 3 (1,4%), `.min` decomp 203 (93,5%), `.min` parcial 2 (0,9%), MT5 1 (0,5%), ausente 1 (0,5%).
**WIN (IS jan–jul, 145 pregões):** tape completo 3, tape parcial 2, `.min` decomp 138 (95,2%), `.min` parcial 2.

**WDO (ano, 217 pregões):** tape completo 9 (4,1%), `.min` decomp 200 (92,2%), `.min` parcial 6 (2,8%), MT5 1, ausente 1.
**WDO (IS jan–jul, 145 pregões):** tape completo 5, `.min` decomp 138 (95,2%), `.min` parcial 2.

### Por mês (WIN, só pregões reais)

| Mês | Pregões | Tape completo | Tape parcial | `.min` decomp | `.min` parcial | MT5 | Ausente |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-01 | 21 | 1 | 0 | 20 | 0 | 0 | 0 |
| 2026-02 | 18 | 0 | 0 | 17 | 1 | 0 | 0 |
| 2026-03 | 22 | 0 | 0 | 22 | 0 | 0 | 0 |
| 2026-04 | 20 | 2 | 1 | 17 | 0 | 0 | 0 |
| 2026-05 | 20 | 0 | 0 | 20 | 0 | 0 | 0 |
| 2026-06 | 21 | 0 | 1 | 20 | 0 | 0 | 0 |
| 2026-07 | 23 | 0 | 0 | 22 | 1 | 0 | 0 |
| 2026-08 | 21 | 1 | 1 | 19 | 0 | 0 | 0 |
| 2026-09 | 21 | 0 | 0 | 21 | 0 | 0 | 0 |
| 2026-10 | 21 | 0 | 0 | 21 | 0 | 0 | 0 |
| 2026-11 | 9 | 3 | 0 | 4 | 0 | 1 | 1 |

### Por mês (WDO, só pregões reais)

| Mês | Pregões | Tape completo | Tape parcial | `.min` decomp | `.min` parcial | MT5 | Ausente |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2026-01 | 21 | 0 | 0 | 21 | 0 | 0 | 0 |
| 2026-02 | 18 | 0 | 0 | 17 | 1 | 0 | 0 |
| 2026-03 | 22 | 1 | 0 | 21 | 0 | 0 | 0 |
| 2026-04 | 20 | 1 | 0 | 19 | 0 | 0 | 0 |
| 2026-05 | 20 | 1 | 0 | 19 | 0 | 0 | 0 |
| 2026-06 | 21 | 2 | 0 | 19 | 0 | 0 | 0 |
| 2026-07 | 23 | 0 | 0 | 22 | 1 | 0 | 0 |
| 2026-08 | 21 | 1 | 0 | 20 | 0 | 0 | 0 |
| 2026-09 | 21 | 1 | 0 | 16 | 4 | 0 | 0 |
| 2026-10 | 21 | 2 | 0 | 19 | 0 | 0 | 0 |
| 2026-11 | 9 | 0 | 0 | 7 | 0 | 1 | 1 |

## 4. Os dias em que realmente coletamos o tape (`.trd`)

Sim: ficamos a maior parte do ano **sem gravar o Times & Trades**. Isso é o buraco de coleta de que você lembra. A agressão do `.min`, na maior parte dos pregões, foi baixada depois no histórico do contrato, não capturada ao vivo.

A sessão JSON só foi montada com `.trd` em 10 pregões do WIN e 9 do WDO, e **nunca nos dois ativos no mesmo dia**. Três sessões de WIN são parciais (cerca de 96 barras M5, o normal é 113): 15/04, 17/06 e 12/08 — o próprio motor documenta o caso “Profit fechado no meio da tarde”.

- **WIN, sessão com `.trd`:** 05/01, 13/04, 14/04, 15/04 (parcial), 17/06 (parcial), 11/08, 12/08 (parcial), 05/11, 06/11, 09/11.
- **WDO, sessão com `.trd`:** 30/03, 30/04, 29/05, 29/06, 30/06, 31/08, 30/09, 28/10, 29/10.
- **`.trd` de WIN no disco, inclusive dias que a sessão não usou:** além da lista acima, 06/01, 13/05, 27/07, 10/11, 11/11 e 12/11.
- **`.trd` de WDO no disco, inclusive não usados na sessão:** além da lista acima, 31/03, 13/04, 31/07 (arquivo pequeno, 0,28 MB), 30/10, 10/11, 11/11 e 12/11.

Ou seja: em 10/11, 11/11 e 12/11 o tape dos dois ativos já estava no disco, mas o backfill das sessões não os aproveitou (em 12/11 a sessão ficou como `HISTÓRICO MT5`). O cache ao vivo de corretoras também só cobre 27/10–11/11.

## 5. Comparação tape real × decomposição do `.min`

Nos dias em que a sessão JSON foi montada com `.trd` e o `div_wall_v1` tem a decomposição do `.min`, comparei barra a barra o `inst_aggr_delta` e a onda acumulada (`cumsum(inst_aggr + inst_pass)`).

| Data | Ativo | Barras comuns | Correlação inst_aggr | Concordância de sinal | Correlação da onda |
|---|---|---:|---:|---:|---:|
| 2026-01-05 | WIN | 113 | 0.98 | 96% | 0.91 |
| 2026-03-30 | WDO | 114 | 0.95 | 90% | -0.19 |
| 2026-04-13 | WIN | 113 | 0.97 | 91% | 0.98 |
| 2026-04-14 | WIN | 113 | 0.97 | 89% | 0.88 |
| 2026-04-15 | WIN | 96 | 0.43 | 68% | 0.76 |
| 2026-04-30 | WDO | 114 | 0.35 | 46% | 0.24 |
| 2026-05-29 | WDO | 113 | 0.20 | 42% | 0.60 |
| 2026-06-17 | WIN | 96 | 0.37 | 67% | 0.40 |
| 2026-06-29 | WDO | 114 | 0.95 | 93% | 0.95 |
| 2026-06-30 | WDO | 114 | 0.37 | 55% | 0.91 |
| 2026-08-11 | WIN | 113 | 0.96 | 92% | 1.00 |
| 2026-08-12 | WIN | 96 | 0.41 | 64% | -0.88 |
| 2026-08-31 | WDO | 114 | 0.96 | 78% | -0.61 |
| 2026-09-30 | WDO | 113 | 0.28 | 52% | 0.86 |
| 2026-10-28 | WDO | 114 | 0.89 | 86% | -0.00 |
| 2026-10-29 | WDO | 114 | 0.87 | 91% | 0.07 |
| 2026-11-05 | WIN | 113 | 0.98 | 96% | 0.97 |
| 2026-11-06 | WIN | 113 | 0.98 | 96% | 0.88 |
| 2026-11-09 | WIN | 113 | 0.97 | 93% | 0.96 |

Mediana geral: correlação de `inst_aggr_delta` **0,95**; concordância de sinal **89%**; correlação da onda **0,86**.

A mediana esconde dois regimes. Nos pregões **completos de WIN**, a decomposição do `.min` acompanha muito bem o tape (correlação 0,96–0,98, sinal ~90–96%, onda em geral acima de 0,88). Nos **WIN parciais** (15/04, 17/06, 12/08) a correlação cai para ~0,40 e no 12/08 a onda até inverte o sinal (−0,88). No **WDO** o quadro é instável: alguns dias ficam no mesmo patamar do WIN (29/06, 30/03), outros têm correlação de 0,20–0,37, e a onda acumulada às vezes descola mesmo quando o delta da barra ainda correlaciona (28/10 e 29/10, onda ~0).

Leitura: o proxy do `.min` é utilizável, principalmente no WIN em sessão completa, mas **não é o tape**. No WDO e em sessões truncadas ele pode desenhar outra história. Por isso a onda Smart Money dos backtests deve ser lida como um indicador estável e repetível, não como fluxo institucional observado.

## 6. Impacto nos backtests e nas marcações

O especialista de produção (`ESP_DIV_V22_WIN`, 02/01–11/11) tem **252 trades** (jan–jul: **173**). Todos vieram do `div_wall_v1`, portanto da decomposição do `.min`, inclusive nos dias com tape. Nenhum trade caiu em pregão ausente ou só MT5. Os dois pregões incompletos (18/02 e 31/07) já estavam fora do dataset, então também não geraram trade.

Distribuição dos 252 trades segundo a classe do **pregão** (a fonte da sessão JSON; o trade em si usou `.min`):

- min_decomp: 243 trades (96,4%)
- trd_completo: 7 trades (2,8%)
- trd_parcial: 2 trades (0,8%)

No IS jan–jul (173 trades):

- min_decomp: 168 trades (97,1%)
- trd_completo: 3 trades (1,7%)
- trd_parcial: 2 trades (1,2%)

Os 9 pregões rotulados são todos `min_decomp` nos dois ativos, inclusive o 11/11 (que tem `.trd` no disco, mas o rotulador e o `div_wall_v1` usaram o `.min`).

## 7. O alerta de 11/11 (deltas institucionais perto de zero depois das 10:05)

No histórico, o dia está saudável: depois das 10:05, **0 de 100** barras do WIN e **0 de 101** do WDO têm `inst_aggr_delta` zero, tanto no `div_wall_v1` quanto na sessão JSON. A sessão foi gravada como `PROFIT NATIVO M1+M5`, embora o `.trd` dos dois ativos já esteja no disco e o cache ao vivo marque 11/11 como `PROFIT_TRD_NATIVE`.

Conclusão: o buraco das 10:05 foi no **feed ao vivo** daquele pregão. Ele **não contaminou** o histórico usado no backtest e na rotulagem.

## 8. Veredito de confiança

**Confiança alta no preço e na agressão do `.min`** em 216 dos 217 pregões reais (o 13/11 ainda não estava no arquivo anual). Essas barras não exigem que o PC tenha coletado o dia ao vivo; o Profit as baixa no histórico do contrato. Só 18/02 e 31/07 (e alguns dias curtos de WDO em setembro) estão visivelmente incompletos.

**Confiança baixa de que a onda Smart Money seja fluxo institucional observado.** A sessão usou tape em apenas 4,6% dos pregões de WIN (10 de 217, três deles parciais) e 4,1% dos de WDO, e nunca nos dois ativos juntos. Os backtests (especialista, setup v3.2, motor v2.1, rotulador) **nem usam** esse tape: usam 100% a decomposição do `.min`. Corretoras observadas e o recorte institucional “de verdade” só existem nos dias `.trd`; no resto, o book de corretoras da sessão é imputado. No WIN completo o proxy até acompanha o tape; no WDO e em sessões truncadas, não se pode contar com isso.

**Caveats:**

- “Ficamos vários dias sem coletar” é verdade para o **Times & Trades** e para o cache de corretoras ao vivo. Não é automaticamente verdade para as barras `.min` com agressão.
- O rótulo `PROFIT NATIVO M1+M5 (Book+RLP B3)` da sessão histórica é otimista: no `.min` o RLP é residual de volume, e não há book de corretoras observado.
- O calendário GEX traz 7 datas que não são pregão; o CSV as mantém, com `is_b3_trading_day=0`.
- 12/11 tem `.trd` no disco, mas a sessão ficou só com histórico MT5 e o dia não entra no `div_wall_v1`. 13/11 está no calendário e ainda não tinha `.min` nem sessão arquivada no fim desta auditoria.
- A comparação tape × `.min` cobre poucos dias e um ativo por vez. A mediana boa do WIN não vale para o WDO.
- O OOS ago–nov já foi consultado várias vezes em pesquisas de divergência; esta auditoria não reabre esse ponto, só a qualidade da fonte de fluxo.

Arquivo dia a dia: `research/data_audit/fluxo_cobertura_2026.csv`.
