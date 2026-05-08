---
id: TASK-2
title: Execução live no MT5 (XP DEMO) — versão robusta
status: In Progress
assignee: []
created_date: '2026-05-06 22:35'
updated_date: '2026-05-08 14:32'
labels:
  - backend
  - mt5
  - trade-engine
  - live-orders
dependencies:
  - TASK-3
references:
  - core/trade_engine.py
  - core/mt5_client.py
  - core/config.py
  - 'server.py:125'
  - 'server.py:626'
  - 'server.py:737'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Hoje o `TradeEngine` é paper-only: detecta sinal, persiste no SQLite (`matador_ops`), nunca chama `mt5.order_send`. Queremos a primeira versão **robusta** de execução real contra a conta XP DEMO 52033102 (terminal portable `E:\MetaTraders\MT5-Python\Ticks\terminal64.exe`), mantendo o fluxo paper como fallback via flag.

"Robusta" significa: schema preparado para reconciliação MT5↔SQLite, magic numbers por estratégia, idempotência em restart, helpers MT5 testáveis, e desligamento limpo via flag. **NÃO** é toggle simples de `if LIVE: order_send()`.

## Estado atual (descobertas da leitura)

- `_trade_engine = TradeEngine(db_path="trades.db")` em `server.py:125` (instância única, módulo).
- Os 3 slots (`CONS_BASE`, `WDO_NWE`, `DI_NWE`) abrem **somente WIN$N**, qty `WIN_CONTRACTS = 2`. WDO e DI são fontes de sinal, não são negociados.
- Slice 9 já preparou o schema `matador_ops` com campos MT5 (`mt5_ticket_in`, `mt5_ticket_out`, `mt5_magic`, `live`) e manteve o caminho paper gravando `live=0`.
- `_open_trade()` (linha 264) e `_close_trade()` (linha 344) só fazem INSERT/UPDATE no SQLite.
- Lock por slot: se `status='OPEN'` para a estratégia, só roda `_check_exits`.
- Entradas só em `bar_close_confirmed=True`; saídas (SL/TP/BE/FORCE_CLOSE) rodam todo poll (~2.5s).
- Endpoint legado V1 já foi removido na TASK-3; o fluxo live deve mirar somente `/api/v2/regime`.
- `mt5.order_send` ainda não aparece no caminho de runtime (`core/`/`server.py`).

## Plano técnico

### 1. Feature flag e constantes (`core/config.py`)

```python
LIVE_ORDERS = False              # master switch — default paper
LIVE_SYMBOL_WIN = "WIN$N"
LIVE_DEVIATION = 50              # slippage (pontos) em market order
LIVE_MAGIC_BASE = 770000
MAGIC_BY_STRATEGY = {
    "CONS_BASE": LIVE_MAGIC_BASE + 1,   # 770001
    "WDO_NWE":   LIVE_MAGIC_BASE + 2,   # 770002
    "DI_NWE":    LIVE_MAGIC_BASE + 3,   # 770003
}
LIVE_FILLING = mt5.ORDER_FILLING_RETURN  # XP aceita; FOK/IOC podem rejeitar WIN
```

`LIVE_ORDERS=False` por padrão garante que merge no `main` não dispara ordem real.

### 2. Migration aditiva em `_init_db()`

Quatro colunas novas, todas nullable — paper-only continua intacto:

| Coluna           | Tipo    | Para quê                                                  |
|------------------|---------|-----------------------------------------------------------|
| `mt5_ticket_in`  | INTEGER | ticket do `order_send` de entrada                         |
| `mt5_ticket_out` | INTEGER | ticket do `order_send` de saída (deal/order de close)     |
| `mt5_magic`      | INTEGER | magic da estratégia (rastreabilidade + reconciliação)     |
| `live`           | INTEGER | 0=paper, 1=ordem real — facilita filtro no dashboard      |

Migration via `ALTER TABLE ... ADD COLUMN` com try/except em `OperationalError`, padrão já usado para a coluna `strategy`.

### 3. Helpers em `core/mt5_client.py`

Funções puras, testáveis (mockáveis). Não conhecem `TradeEngine`.

- `send_market_order(symbol, side, volume, magic, deviation, comment) -> dict`
  - `side`: `"BUY"` ou `"SELL"`.
  - Monta `request = {"action": TRADE_ACTION_DEAL, "type": ORDER_TYPE_BUY/SELL, ...}`.
  - Pega preço de `mt5.symbol_info_tick(symbol)`.
  - Chama `mt5.order_send(request)`. Retorna `{ok, ticket, retcode, message, price}`.
  - Trata retcodes `TRADE_RETCODE_DONE`, `DONE_PARTIAL`, `REQUOTE`, etc.
  - Sem retry inicial (ordem repetida = posição duplicada). Loga e retorna falha.

- `close_position_by_ticket(ticket, magic, comment) -> dict`
  - Localiza `mt5.positions_get(ticket=ticket)`.
  - Monta deal oposto com mesmo volume.
  - Retorna mesma estrutura `{ok, ticket, retcode, message, price}`.

- `list_open_positions(symbol=None, magic=None) -> list[dict]`
  - Wrapper de `mt5.positions_get` com filtros, normaliza para dict.
  - Usado pela reconciliação.

### 4. Integração em `core/trade_engine.py`

Mudanças cirúrgicas, sem refatorar lógica de sinal:

- `_open_trade(...)`:
  - Se `LIVE_ORDERS`:
    - Chamar `send_market_order(LIVE_SYMBOL_WIN, direction, WIN_CONTRACTS, MAGIC_BY_STRATEGY[strategy], LIVE_DEVIATION, comment=f"{strategy}/{z_source}")`.
    - Se falhar → retornar `_result("ORDER_FAILED", strategy)` (ou `WAIT` + log) **sem** persistir linha. Próximo `bar_close_confirmed` reavalia.
    - Se sucesso → `INSERT` com `mt5_ticket_in=ticket`, `mt5_magic=magic`, `live=1`. Usar `price` retornado pelo MT5 em `price_win_in` (não o `win_price` da vela).
  - Se `LIVE_ORDERS=False`: comportamento atual + `live=0`, `mt5_magic=NULL`.

- `_close_trade(...)`:
  - Recebe agora também `trade` (já lido do row OPEN) para acessar `mt5_ticket_in`/`mt5_magic`.
  - Se `LIVE_ORDERS` e `mt5_ticket_in` not null:
    - `close_position_by_ticket(mt5_ticket_in, mt5_magic, comment=reason)`.
    - Se falhar → **não** marcar CLOSED no SQLite. Logar, deixar OPEN. Próximo poll reavalia exit (saídas rodam todo tick — recuperação automática).
    - Se sucesso → `UPDATE` com `mt5_ticket_out`, `price_win_out=` preço retornado, status=CLOSED.
  - Se paper ou ticket null → comportamento atual.

- `_check_exits(...)`: passar o `trade` completo para `_close_trade`. Atualizar SELECT em `_get_open_trades()` para incluir `mt5_ticket_in`, `mt5_magic`, `live`.

### 5. Reconciliação no startup do `server.py`

Antes de subir o uvicorn (ou no startup hook do FastAPI), rodar `reconcile_open_trades()`:

Estados possíveis:

| SQLite OPEN | MT5 posição (mesmo magic) | Ação                                                                 |
|---|---|---|
| sim | sim | OK — vincula em memória. Loga.                                       |
| sim | não | "trade fantasma" no SQLite. Marcar CLOSED com `exit_reason="RECONCILE_LOST"`, `mt5_ticket_out=NULL`. Loga warning. |
| não | sim (com magic conhecido) | "posição órfã" no MT5. Não fechamos automaticamente — apenas loga e alerta. Operador decide. |
| não | sim (magic desconhecido / 0) | Posição manual ou outro sistema. Ignora. |

Reconciliação roda **sempre** quando `LIVE_ORDERS=True` (mesmo se ninguém mexeu) — barato e idempotente. Quando `LIVE_ORDERS=False`, pula.

### 6. Tests (`tests/test_trade_engine_live.py`)

- `test_open_trade_paper_unchanged`: sem flag, comportamento idêntico ao atual.
- `test_open_trade_live_persists_ticket`: mock `send_market_order` retornando ticket — verifica INSERT com `mt5_ticket_in`/`mt5_magic`/`live=1`.
- `test_open_trade_live_failure_no_insert`: mock falha — `matador_ops` permanece vazio.
- `test_close_trade_live_calls_mt5`: mock `close_position_by_ticket` — verifica chamada com `mt5_ticket_in` correto.
- `test_close_trade_live_failure_keeps_open`: mock falha de close — status continua OPEN, próximo tick reavalia.
- `test_reconcile_ghost_in_sqlite`: SQLite OPEN, MT5 vazio → marca CLOSED com reason RECONCILE_LOST.
- `test_reconcile_orphan_in_mt5`: MT5 com posição magic conhecido, SQLite limpo → loga warning, não modifica.
- `test_magic_per_strategy`: cada strategy resolve para magic distinto.

### 7. Smoke test manual (DEMO)

Roteiro documentado em `docs/live_orders_smoke.md`:
1. Confirmar `LIVE_ORDERS=True` em `core/config.py`.
2. Subir backend, aguardar conexão MT5 + reconciliação limpa.
3. Forçar sinal (script `scripts/force_signal.py` opcional ou esperar).
4. Verificar abertura no MT5 terminal (Comércio → Posições) com magic correto.
5. Verificar `matador_ops` com `mt5_ticket_in` populado.
6. Aguardar saída (SL/TP/FORCE_CLOSE) ou cancelar manualmente; verificar UPDATE.
7. Reiniciar server → reconciliação não deve criar trades fantasma.

## Arquivos afetados

- `core/config.py` — flag + magic dict + filling.
- `core/mt5_client.py` — 3 helpers novos.
- `core/trade_engine.py` — schema migration + branches LIVE em open/close + SELECT atualizado + reconcile method.
- `server.py` — chamada de reconciliação no startup.
- `tests/test_trade_engine_live.py` — novo.
- `docs/live_orders_smoke.md` — novo (roteiro manual).

## Riscos e mitigações

- **Posição duplicada por retry** → sem retry automático em `send_market_order`. Falha é falha; próximo bar close reavalia.
- **Saída falha repetidamente** → cada poll (~2.5s) tenta de novo. Se persistir, log de erro e operador fecha manual (FORCE_CLOSE manual no MT5; reconcile pega no próximo restart).
- **Magic colidir com outro EA** → faixa 770001-770003 não usada pelo dco-collector (auditado: collector é read-only). Documentar em `core/config.py`.
- **Crash entre `order_send` OK e INSERT** → janela curta (<10ms), mas reconcile pega na subida (posição órfã com magic conhecido → alerta).
- **WDO_NWE e DI_NWE abrindo posição WIN simultânea** → 3 magics distintos = 3 posições paralelas no MT5. Comportamento intencional (cada slot é independente). Documentar.
- **Filling mode rejeitado** → `LIVE_FILLING=ORDER_FILLING_RETURN` é o aceito por XP em WIN$N (validado via `mt5.symbol_info`). Se `order_send` retornar `INVALID_FILL`, fallback para `IOC` apenas após log.

## Fora de escopo (followups)

- Posições parciais ou pyramiding.
- Order types além de market (limit, stop).
- Conta real (apenas DEMO até validação completa).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Flag `LIVE_ORDERS` em `core/config.py` com default `False` controla todo o fluxo live; quando `False`, comportamento de `_open_trade`/`_close_trade` é idêntico ao atual (paper).
- [x] #2 Tabela `matador_ops` ganha colunas `mt5_ticket_in`, `mt5_ticket_out`, `mt5_magic`, `live` via migration aditiva idempotente (re-rodar `_init_db` não falha em base existente).
- [x] #3 `MAGIC_BY_STRATEGY` mapeia cada slot para um magic único (770001/770002/770003); ordem aberta carrega o magic correspondente.
- [x] #4 Helper `send_market_order` em `core/mt5_client.py` envia ordem market via `mt5.order_send` e retorna `{ok, ticket, retcode, message, price}`; não faz retry automático.
- [x] #5 Helper `close_position_by_ticket` em `core/mt5_client.py` fecha posição pelo ticket + magic e retorna a mesma estrutura.
- [x] #6 Quando `LIVE_ORDERS=True` e `send_market_order` falha, nenhuma linha é inserida em `matador_ops` e a estratégia retorna `WAIT`/`ORDER_FAILED`; próximo bar close reavalia.
- [x] #7 Quando `LIVE_ORDERS=True` e `close_position_by_ticket` falha, o trade permanece `status=OPEN`; saída é re-tentada no próximo poll de exit.
- [ ] #8 Reconciliação no startup detecta os 3 estados (match / fantasma SQLite / órfã MT5) e age conforme tabela do plano; quando `LIVE_ORDERS=False`, é skipada.
- [ ] #9 Suite `tests/test_trade_engine_live.py` cobre: paper inalterado, live success, live order fail, live close fail, reconcile ghost, reconcile orphan, magic per strategy.
- [ ] #10 Roteiro de smoke test manual em `docs/live_orders_smoke.md` cobre: subir com `LIVE_ORDERS=True`, validar abertura/fechamento no MT5, validar persistência no SQLite, validar reconciliação após restart.
- [ ] #11 Smoke test executado com sucesso em conta XP DEMO 52033102 com pelo menos um trade aberto e fechado live; evidência (screenshot ou log) anexada à task antes de mover para Done.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-05-07 — TASK-3 (`Pré-live hardening`) criada como pré-requisito recomendado antes da execução live. Não iniciar integração `mt5.order_send` enquanto fragilidades de paridade produção/backtest, risk gate, persistência `bar_history`, validação e clareza operacional não estiverem resolvidas ou explicitamente aprovadas como exceção.

2026-05-08 — Slice 9 iniciou a TASK-2 com scaffold seguro: `LIVE_ORDERS=False` e perfil live/magic em `core/config.py`; migration idempotente adiciona `mt5_ticket_in`, `mt5_ticket_out`, `mt5_magic`, `live` em `matador_ops`; o caminho paper grava `live=0` e tickets/magic nulos. Nenhuma chamada a `mt5.order_send` foi adicionada nesta slice. AC #1 fica aberto até `_open_trade`/`_close_trade` consumirem a flag no fluxo live. AC #3 tem o mapa testado, mas só fecha quando a ordem live persistir/carregar o magic.

2026-05-08 14:32 — Slice 10 integrou execução live no `TradeEngine` atrás de `LIVE_ORDERS`: abertura chama `send_market_order` antes do INSERT; falha retorna `ORDER_FAILED` e não grava linha; sucesso grava `mt5_ticket_in`, `mt5_magic`, `live=1` e preço de fill. Fechamento live chama `close_position_by_ticket`; falha mantém `status=OPEN` para retry no próximo poll; sucesso grava `mt5_ticket_out`, preço de fill e P&L recalculado. Dashboard agora mostra `risk_gate.reasons` no painel de regime para distinguir "sem entrada" de "gate bloqueado" (`EG_NOT_COINTEGRATED`, `BAR_NOT_CLOSED`, etc.). AC #8/#10/#11 ainda pendentes.
<!-- SECTION:NOTES:END -->
