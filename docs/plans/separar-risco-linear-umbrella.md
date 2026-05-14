# Separar Risco Live de Paper e Manter SL/TP/BE pelo Motor

## Context

Hoje, com `LIVE_ORDERS=1`, todos os bloqueadores operacionais (`MAX_TRADES_REACHED`, `DAILY_LOSS_LIMIT`, `LOSS_COOLDOWN` e a checagem de posição aberta por slot) olham **todas** as linhas de `matador_ops`, sem distinguir trade real (live) de simulado (paper).

Consequência atual concreta: um trade paper de hoje com `pnl_brl=-494` está acionando o gate `DAILY_LOSS_LIMIT` e bloqueando entradas live, mesmo que nenhuma ordem real tenha sido enviada ao MT5.

Queremos que, em modo live:
- Os limites operacionais considerem somente linhas `matador_ops.live=1` (ordens MT5 com fill confirmado).
- Trades paper continuem existindo no banco para auditoria/histórico, mas **não bloqueiem** entradas reais e **não acionem saídas** pelo motor.
- SL, TP, BE e FORCE_CLOSE continuem decididos pelo motor e executados via fechamento a mercado no MT5 (`close_position_by_ticket`) — nada de SL/TP pendurado.
- A interface (`/api/v2/regime`, `/health`) e o timeline expliquem qual escopo está em uso (live vs paper/all) para auditoria.

O schema já suporta isso: `matador_ops.live INTEGER DEFAULT 0` existe desde a migration original (`core/trade_engine.py:69-94`) e só recebe `1` após `send_market_order` retornar `ok=True` com ticket (`core/trade_engine.py:665`). Não é preciso nova migration.

## Recommended Approach

Adicionar um kwarg `live_only: bool` nas funções de leitura agregada do `TradeEngine`. O `server.py` decide o valor com base em `LIVE_ORDERS` e propaga via `evaluate(...)`. `risk_gate()` e `operational_checks()` permanecem inalterados — eles já consomem números prontos.

Sem migração de dados. Trades paper-OPEN antigos ficam como estão no banco; em modo live deixam de aparecer em `_get_open_trades(live_only=True)`, então não bloqueiam novas entradas reais nem disparam exits do motor. Esse comportamento é documentado em docstring.

### Critical files

- `core/trade_engine.py` — adicionar `live_only` em `_get_open_trades` (l.117), `count_trades_today` (l.1037), `pnl_today` (l.1047), `minutes_since_last_loss` (l.1063) e `evaluate` (l.157+). Repassar internamente nas chamadas das l.213, 240–242. **Atenção**: existe um segundo cálculo das três stats em `evaluate` na l.240–242 (refresh pós Phase 1 / pré Phase 2) que também precisa receber `live_only`.
- `server.py` — em `regime_v2()` (≈l.1184) e nas três chamadas de `risk_gate`/`evaluate` (l.1411, l.1440, l.1464), passar `live_only=bool(LIVE_ORDERS)`. Adicionar campos flat `risk_*` em `_build_response` (l.1116-1179) e campo curto em `/health` (l.1815-1869).
- `core/timeline_emit.py` — em `reason_fields()` (l.74-115) injetar `"scope"` apenas para `MAX_TRADES_REACHED`, `DAILY_LOSS_LIMIT`, `LOSS_COOLDOWN`. `emit_closed_bar_timeline()` (l.212-305) ganha `live_only: bool=False` e repassa.
- `core/risk_gate.py` — **não muda**. Documentar no docstring que é scope-agnostic.
- `tests/test_trade_engine.py`, `tests/test_trade_engine_live.py`, `tests/test_execution_timeline.py`, `tests/test_execution_timeline_server.py` — novos testes (ver Slices).

### Open-trade órfãos (paper) — política

Decidido: **não tocar** trades paper com `status='OPEN'` no banco. Em modo live (`live_only=True`):
- `_get_open_trades` os omite → slot fica livre para nova entrada live.
- Eles continuam visíveis em relatórios históricos (`get_performance`, dashboards de PnL).
- Nunca serão fechados pelo motor automaticamente. Documentar isso em docstring de `_get_open_trades` e em `CLAUDE.md` na seção "Critical Constraints".

Rejeitado: criar migration ad-hoc para marcar paper-OPEN como `ABANDONED`. Custo > benefício e quebra dashboards que assumem `OPEN/CLOSED`.

### Slices (execução incremental, parar e reportar entre cada um)

Aderindo à memória [[feedback_slice_review_ritual.md]]: cada slice abre uma subtask no MCP backlog, é commitado isoladamente com seus testes verdes, e eu reporto antes de iniciar o próximo.

**Slice 1 — `live_only` read-side nas três stats (zero impacto em runtime)**
- `core/trade_engine.py`: adicionar `live_only: bool=False` (kwarg-only) a `count_trades_today`, `pnl_today`, `minutes_since_last_loss`. Anexar `AND live = 1` ao WHERE quando `True`.
- Novos testes em `tests/test_trade_engine.py` (helper `_seed_trade` via SQL direto):
  - `test_count_trades_today_default_includes_paper_and_live`
  - `test_count_trades_today_live_only_filters_paper`
  - `test_pnl_today_live_only_excludes_paper_losses` (replica o cenário R$-494)
  - `test_minutes_since_last_loss_live_only_ignores_paper_stop`
  - `test_minutes_since_last_loss_live_only_returns_none_when_no_live_stop`

**Slice 2 — `live_only` em `_get_open_trades` e propagação em `evaluate`**
- `core/trade_engine.py`: `_get_open_trades(*, live_only=False)` com `AND live = 1`. `evaluate(..., live_only: bool=False)` repassa para l.213 e para as três chamadas de stats em l.240–242.
- Novos testes:
  - `test_get_open_trades_live_only_hides_paper_open`
  - `test_evaluate_live_only_unblocks_after_paper_daily_loss` (replica o bug atual)
  - `test_evaluate_default_live_only_false_preserves_legacy_blocking` (back-compat replay/paper)
- Ainda zero efeito em produção: defaults `False` em todos os callers.

**Slice 3 — Cutover no `server.py` (corrige o bug)**
- `server.py`: as três chamadas a `risk_gate`/`evaluate` (l.1411, l.1440, l.1464) passam `live_only=bool(LIVE_ORDERS)`. Mesma propagação para `emit_closed_bar_timeline` no slice 5.
- Novo teste de integração:
  - `test_evaluate_live_only_still_blocks_on_live_daily_loss` (seed live `pnl = -DAILY_LOSS_LIMIT_BRL` → ainda bloqueia)
- Após este slice, o trade paper R$-494 deixa de bloquear o live.

**Slice 4 — Campos `risk_*` em `/api/v2/regime` e flag em `/health`**
- `_build_response` (l.1116): adicionar quatro campos flat no top-level do JSON (naming espelhando o brief original):
  ```
  "risk_stats_scope": "live" if LIVE_ORDERS else "all",
  "risk_trades_today": <pós-Phase1>,
  "risk_daily_pnl_brl": <pós-Phase1>,
  "risk_minutes_since_last_loss": <pós-Phase1>,
  ```
  Os três valores numéricos vêm dos `trades_today_now / daily_pnl_now / minutes_since_loss_now` já calculados em `evaluate()` (l.240–242). Vamos expô-los via retorno de `evaluate` (mais barato — sem nova query SQLite) ou recalcular em `regime_v2` com o mesmo `live_only`. Preferência: retorno de `evaluate`.
- `/health` (l.1815-1869): adicionar apenas `"risk_stats_scope": "live" if LIVE_ORDERS else "all"` para não duplicar query SQLite por probe. Sem os números detalhados.
- Novo teste:
  - `test_api_v2_regime_includes_risk_stats_fields_live` em `tests/test_execution_timeline_server.py` (já tem padrão FastAPI TestClient).

> **Nota de mudança / revisitar**: optamos por campos flat `risk_*` no top-level porque é o que o brief original do usuário descreveu. Se durante a implementação ficar evidente que o front-end prefere um objeto aninhado `risk_audit: {scope, trades_today, daily_pnl_brl, minutes_since_last_loss}` — em geral mais limpo para crescer — refatorar antes de mergear. Não congelar a forma do JSON sem validar com um consumer real.

**Slice 5 — Campo `scope` no timeline**
- `core/timeline_emit.py`: `reason_fields(reason, ..., live_only=False)` injeta `"scope": "live" if live_only else "all"` apenas em `MAX_TRADES_REACHED`, `DAILY_LOSS_LIMIT`, `LOSS_COOLDOWN`. `emit_closed_bar_timeline(..., live_only=False)` repassa.
- `server.py` passa `live_only=bool(LIVE_ORDERS)` na emissão (l.~1475).
- Demais reasons (BAR_NOT_CLOSED, RHO_BREAKDOWN, BETA_DRIFT, Z_ANOMALY etc.) não recebem `scope` — o conceito não se aplica.
- Novo teste:
  - `test_emit_closed_bar_timeline_includes_scope_for_operational_reasons`
- Consumidores existentes do timeline (dashboard, replay) toleram campos extras em `payload_json` — não há schema strict.

## Verification

1. **Unit tests**: `pytest tests/test_trade_engine.py tests/test_trade_engine_live.py tests/test_execution_timeline.py tests/test_execution_timeline_server.py -v`. Todos devem passar; cenário do bug (`test_evaluate_live_only_unblocks_after_paper_daily_loss`) deve falhar antes do slice 2 e passar depois.

2. **Manual end-to-end com DB real**:
   - Confirmar que o trade paper de hoje com `pnl_brl=-494` está presente: `sqlite3 <db> "SELECT id, timestamp_in, status, live, pnl_brl FROM matador_ops WHERE date(timestamp_in)=date('now','localtime');"`.
   - Subir o server com `LIVE_ORDERS=1` (após slice 3).
   - `curl http://localhost:8080/api/v2/regime | jq '{scope: .risk_stats_scope, daily_pnl_brl: .risk_daily_pnl_brl, trades_today: .risk_trades_today}'` → deve mostrar `scope: "live"` e ignorar o paper.
   - `curl http://localhost:8080/health | jq .risk_stats_scope` → `"live"`.
   - Aguardar próxima janela de sinal e confirmar que o motor não bloqueia mais por `DAILY_LOSS_LIMIT` originário do paper.

3. **Regressão paper-mode** (replay/backtest): rodar `pytest tests/test_replay_simulation*.py` para confirmar que `live_only=False` mantém comportamento legado de paper bloqueando paper.

4. **Inspeção do timeline** (slice 5): em uma sessão live, provocar `MAX_TRADES_REACHED` propositalmente (ex.: simular com `MAX_TRADES_PER_DAY=0`) e confirmar que o evento no `execution_timeline` carrega `payload_json` com `"scope": "live"`.

## Assumptions

- `matador_ops.live=1` é a fonte de verdade exclusiva para "risco real" nesta etapa. Linhas com `live=1` só existem após fill MT5 confirmado.
- Não criamos nem editamos trades paper antigos. Não criamos SL/TP pendurado no MT5.
- O sistema permanece `LIVE_ORDERS=1` e `LIVE_SYMBOL_WIN=AUTO` (conta XPMT5-DEMO 92033102) durante a validação.
- `risk_gate()` é scope-agnostic e segue assim — toda a lógica de filtragem fica no TradeEngine (read-side).
- Trades paper com `status='OPEN'` antes do cutover ficarão eternamente OPEN no DB. Comportamento desejado, será documentado em `_get_open_trades` docstring e em `CLAUDE.md`.
