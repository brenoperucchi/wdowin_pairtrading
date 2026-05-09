# Motor de Compra/Venda e Fluxo de Dados

**Data:** 2026-05-07

**Escopo:** fluxo operacional do sistema em modo live/paper, fora dos scripts de backtest.

Este documento explica como os dados entram no sistema, como os indicadores sao calculados, como o `TradeEngine` decide compra/venda e como o dashboard consome o resultado.

## Resumo Executivo

O sistema operacional atual nao consome tick a tick puro. Ele trabalha por **polling de barras M5 do MetaTrader 5**.

O backend busca barras dos ativos no MT5, calcula indicadores/filtros, chama o `TradeEngine`, registra trades paper no SQLite e devolve tudo para o dashboard.

Estado atual:

- Dados de mercado: MT5 via `copy_rates_from_pos`.
- Timeframe operacional: M5.
- Motor de ordem real: ainda nao implementado.
- Motor atual: paper trading em SQLite.
- Ativo operado pelo motor: WIN.
- WDO e DI: fontes de sinal/filtro, nao pernas executadas atualmente.
- Backtests: scripts separados em `research/`, nao sao chamados automaticamente pelo dashboard.

## Visao de Alto Nivel

```text
FastAPI server.py
  |
  | poller operacional interno a cada 2.5s
  | dashboard/Firebase apenas consomem ou espelham o estado
  v
GET /api/v2/regime
  |
  | conecta no MT5
  v
core/mt5_client.py
  |
  | copy_rates_from_pos(WIN$N, WDO$N, DI1$N, M5)
  v
Indicadores e filtros
  |
  | Kalman, OLS/rho, DI, NWE, beta, Johansen informativo
  v
core/trade_engine.py
  |
  | decide WAIT / BUY_WIN / SELL_WIN / CLOSE
  v
trades.db / matador_ops
  |
  | trades_today + performance
  v
Dashboard com sinais, historico e marcadores de trades
```

## Arquivos Principais

| Arquivo | Papel |
|---------|-------|
| `core/config.py` | Simbolos, timeframe, parametros de entrada, risco, horarios e sizing |
| `core/mt5_client.py` | Conexao com MT5 e coleta de barras |
| `server.py` | Endpoints FastAPI, calculo de indicadores e montagem da resposta |
| `core/kalman_filter.py` | Filtro de Kalman usado no spread WIN/WDO e em partes do sistema |
| `core/signals.py` | Funcoes de z-score, beta, rho, NWE e sinais auxiliares |
| `core/trade_engine.py` | Motor de decisao e registro de trades paper |
| `trades.db` | SQLite local com tabela `matador_ops` |
| `regime-dashboard/src/App.jsx` | Consumo da API/Firebase pelo dashboard |

## Entrada de Dados

O sistema operacional nao usa CSV para rodar ao vivo/paper. Ele precisa do MetaTrader 5 aberto, logado e com os simbolos habilitados no Market Watch.

Simbolos atuais:

```text
WIN$N
WDO$N
DI1$N
```

Configuracao atual em `core/config.py`:

```python
SYMBOL_A = "WIN$N"
SYMBOL_B = "WDO$N"
DI_SYMBOL = "DI1$N"
TIMEFRAME = mt5.TIMEFRAME_M5
```

A coleta acontece em `core/mt5_client.py`:

```python
rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, count)
```

Isso retorna barras OHLC do MT5. O ultimo candle M5 pode ir sendo atualizado pelo MT5 enquanto esta em formacao, mas o sistema nao assina fluxo tick a tick nem livro de ofertas.

## Fluxo do Endpoint Principal

O endpoint operacional principal e:

```text
GET /api/v2/regime
```

Fluxo simplificado:

1. `server.py` chama `connect_mt5()`.
2. Busca barras M5 de `WIN$N` e `WDO$N`.
3. Alinha os arrays pelo menor tamanho disponivel.
4. Calcula spread WIN/WDO via Kalman.
5. Calcula z-score WDO a partir do spread Kalman.
6. Calcula NWE sobre o preco do WIN.
7. Calcula rho e beta/saude da relacao.
8. Calcula Johansen gate para diagnostico.
9. Atualiza/consulta o cache de DI via `/api/di-regime`.
10. Detecta se houve virada de candle M5.
11. Chama `TradeEngine.evaluate(...)`.
12. Monta historico para graficos.
13. Busca `trades_today` em `matador_ops`.
14. Retorna JSON para o dashboard.

## Indicadores e Filtros

### WIN/WDO

O par principal e `WIN$N` contra `WDO$N`.

O backend calcula um spread dinamico usando `KalmanBetaFilter`. O z-score atual de WDO vem desse spread normalizado em janela rolling.

Uso atual:

- `z_wdo <= -Z_ENTRY`: favorece compra de WIN.
- `z_wdo >= Z_ENTRY`: favorece venda de WIN.

### DI

O `DI1$N` entra como uma segunda fonte de sinal/filtro macro. O `server.py` mantem um cache `_di_cache` e o endpoint `/api/v2/regime` forca atualizacao do DI quando detecta fechamento/virada de barra M5.

Uso atual:

- `z_di <= -Z_ENTRY`: favorece compra de WIN.
- `z_di >= Z_ENTRY`: favorece venda de WIN.

### NWE

O NWE e calculado sobre o preco do WIN e funciona como filtro de tendencia/proximidade de banda.

Ele tenta evitar:

- comprar WIN enquanto o NWE ainda aponta alta forte e preco esta longe da banda inferior;
- vender WIN enquanto o NWE ainda aponta queda forte e preco esta longe da banda superior.

O NWE e usado nos slots `WDO_NWE` e `DI_NWE`. O slot `CONS_BASE` nao usa NWE.

### Rho e Beta

O `safe_to_trade` atual em `/api/v2/regime` considera principalmente:

- status da correlacao `rho`;
- status do delta de beta.

Se esses filtros nao estiverem saudaveis, `beta_safe=False` chega ao `TradeEngine` e entradas novas sao bloqueadas.

### Johansen e HMM

O Johansen gate e calculado e devolvido no JSON, mas atualmente nao e um bloqueio forte de entrada dentro do `TradeEngine`.

O `hmm_state` tambem e passado para o `TradeEngine`, mas a implementacao atual nao usa esse estado para bloquear entradas. Isso e uma pendencia de hardening: decidir se Johansen/HMM bloqueiam, reduzem sizing ou apenas informam.

## Funil de Decisao do TradeEngine

O metodo central e:

```python
TradeEngine.evaluate(...)
```

Ele avalia tres slots independentes:

```text
CONS_BASE
WDO_NWE
DI_NWE
```

Cada slot pode ter um trade aberto proprio. O funil por slot e:

```text
1. Ja existe trade aberto neste slot?
   - Sim: checa saida.
   - Nao: continua para possivel entrada.

2. A barra M5 acabou de virar?
   - Nao: nao abre entrada nova.
   - Sim: continua.

3. Existe anomalia de z-score?
   - Se abs(z_wdo) >= Z_ANOMALY ou abs(z_di) >= Z_ANOMALY: bloqueia.

4. Esta dentro do horario de entrada?
   - Fora da janela: bloqueia.

5. Relacao esta segura?
   - beta_safe=False: bloqueia.

6. Estrategia especifica gerou sinal?
   - Sim: abre trade paper.
   - Nao: WAIT.
```

## Estrategias

### CONS_BASE

Consenso entre WDO e DI.

Compra WIN quando:

```text
z_wdo <= -Z_ENTRY e z_di <= -Z_ATTENTION
ou
z_wdo <= -Z_ATTENTION e z_di <= -Z_ENTRY
```

Vende WIN quando:

```text
z_wdo >= Z_ENTRY e z_di >= Z_ATTENTION
ou
z_wdo >= Z_ATTENTION e z_di >= Z_ENTRY
```

### WDO_NWE

Usa somente `z_wdo` para o sinal base e aplica filtro NWE.

Compra WIN quando:

```text
z_wdo <= -Z_ENTRY
e filtro NWE permite compra
```

Vende WIN quando:

```text
z_wdo >= Z_ENTRY
e filtro NWE permite venda
```

### DI_NWE

Usa somente `z_di` para o sinal base e aplica filtro NWE.

Compra WIN quando:

```text
z_di <= -Z_ENTRY
e filtro NWE permite compra
```

Vende WIN quando:

```text
z_di >= Z_ENTRY
e filtro NWE permite venda
```

## Abertura de Trade

Quando uma estrategia abre trade, o motor grava uma linha em `trades.db`, tabela `matador_ops`.

Campos importantes:

| Campo | Significado |
|-------|-------------|
| `timestamp_in` | horario de entrada |
| `status` | `OPEN` ou `CLOSED` |
| `direction` | `BUY` ou `SELL` |
| `strategy` | `CONS_BASE`, `WDO_NWE` ou `DI_NWE` |
| `z_in` | z-score de entrada |
| `price_win_in` | preco WIN na entrada |
| `price_wdo_in` | preco WDO observado na entrada |
| `qty_win` | quantidade de WIN configurada |
| `rho_in` | correlacao na entrada |
| `beta_in` | beta na entrada |

O retorno do motor e:

```text
BUY_WIN
SELL_WIN
WAIT
HOLDING
CLOSE
ANOMALY
```

Importante: apesar de existirem sinais WDO/DI, o trade gravado e sempre direcional em WIN. O motor atual nao abre perna WDO nem perna DI.

## Saida de Trade

Saidas sao avaliadas a cada ciclo do poller interno enquanto houver posicao aberta. O dashboard pode chamar `/api/v2/regime`, mas a avaliacao operacional nao depende do navegador estar aberto.

Regras atuais:

| Regra | Descricao |
|-------|-----------|
| Target | Fecha quando pontos a favor >= TP |
| Stop loss | Fecha quando pontos contra >= SL |
| Break-even | Apos ganho minimo, protege retorno para zero |
| Force close | Fecha apos horario final configurado |

O PnL paper e calculado com:

```text
pontos_favoraveis * WIN_CONTRACTS * WIN_PV
```

Hoje os parametros principais sao:

```text
WIN_CONTRACTS = 2
WIN_PV = 0.20
BUY_SL / SELL_SL = 300 pontos
BUY_TP / SELL_TP = 800 pontos
FORCE_CLOSE = 17:40
```

## Consumo pelo Dashboard

O dashboard usa:

```text
/api/v2/regime
/api/performance
/api/di-regime
/api/history
```

O endpoint `/api/v2/regime` devolve:

- z-score atual;
- historico para graficos;
- estado de regime;
- `trade_engine`;
- `trades_today`;
- `johansen_gate`;
- `nwe`;
- informacoes de beta/rho.

O campo `trades_today` vem de `TradeEngine.get_trades_for_date(...)` e e usado para desenhar marcadores nos graficos do dashboard.

Em producao com Firebase Hosting, o frontend pode ouvir Firebase Realtime Database em vez de bater direto na API local. O backend empurra o estado para Firebase em loop.

## Relacao com Backtest

O motor operacional e os backtests nao sao o mesmo codigo.

O operacional usa:

```text
server.py -> TradeEngine -> trades.db -> dashboard
```

Os backtests usam scripts em:

```text
research/
```

Existem dois tipos de scripts:

1. Scripts que leem CSV local exportado do MT5, por exemplo:

```text
base de dados/WDO$N_M1_202103100900_202603261829.csv
base de dados/WIN$N_M1_202103100900_202603261831.csv
```

2. Scripts que puxam barras direto do MT5 com `copy_rates_from_pos`.

Isso significa que um resultado de backtest so valida o motor operacional se as regras, parametros, ativo operado, horarios, custos e filtros forem equivalentes. Hoje ha divergencias conhecidas entre alguns scripts de `research/` e o `TradeEngine`.

## Dados Necessarios

### Para o operacional/paper ao vivo

Nao precisa baixar CSV.

Precisa:

- MT5 Windows aberto e logado;
- caminho `MT5_PATH` correto;
- `WIN$N`, `WDO$N`, `DI1$N` habilitados no Market Watch;
- historico M5 suficiente carregado no terminal;
- simbolos continuos funcionando ou rollover manual para contratos atuais.

### Para backtest offline por CSV

Precisa exportar do MT5 ou outra fonte confiavel:

- `WIN$N` M1;
- `WDO$N` M1;
- opcionalmente `DI1$N` M1/M5, se o backtest incluir DI;
- mesmo periodo;
- mesmo fuso/horario;
- formato tab-separated padrao do MT5.

Formato esperado pelos scripts legados:

```text
date    time    open    high    low    close    tickvol    vol    spread
```

Alguns scripts de ML usam outro caminho:

```text
data/historical/
data/processed/dataset_m30.parquet
```

O diretorio `data/` esta no `.gitignore`, entao bases historicas nao ficam versionadas no repositorio.

## Limitacoes Atuais do Fluxo Operacional

1. Nao ha consumo tick a tick puro.
2. Nao ha envio de ordem real via `mt5.order_send`.
3. WDO e DI nao sao executados como hedge; so geram sinal/filtro.
4. Custos, slippage e spread operacional nao entram no PnL paper.
5. Johansen e HMM ainda nao sao gates fortes de entrada.
6. A paridade entre `research/` e `TradeEngine` precisa ser reconciliada antes de live.
7. O endpoint legado `/api/regime` V1 (OLS) foi removido; toda observacao do regime passa por `/api/v2/regime` (Kalman).
8. A tabela `bar_history` tem migration idempotente (`init_bar_history`) e dedup por `INSERT OR IGNORE` no `timestamp` (PK). O caminho de escrita esta ativo: o V2 chama `_persist_closed_bars(live_history)` a cada poll, persistindo barras fechadas e pulando a barra aberta para evitar repaint.

## Fonte de Verdade Atual

Para avaliar o comportamento operacional atual, use como fonte primaria:

```text
GET /api/v2/regime
core/trade_engine.py
trades.db / matador_ops
regime-dashboard/src/App.jsx
```

Para validar historico/backtest, primeiro defina qual script de `research/` e o backtest canonico. Sem essa decisao, os backtests atuais devem ser tratados como pesquisa exploratoria, nao como validacao direta do motor de producao.
