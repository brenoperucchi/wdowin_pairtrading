# Relatório Semanal — 04 a 10 de Maio de 2026

**Projeto:** WIN×WDO Advanced Regime Monitor (paper-trader → caminho para live na XP DEMO).
**Período:** 7 dias.
**Resumo executivo:** semana do hardening pré-live. Removemos os bloqueadores estruturais que impediam ligar a execução real, entregamos a Execution Timeline (auditoria operacional) tanto no live quanto em modo Replay por data, e iniciamos o scaffold de ordens reais no MT5 atrás de uma flag.

---

## 1. Hardening Pré-Live — TASK-3 ✅ Done

**Problema:** o sistema rodava como paper-trader, mas escondia fragilidades que estouravam se a flag de "ligar ordem real" fosse acionada.

**O que foi feito:**
- Removido endpoint legado `/api/regime` V1 (assinatura quebrada, podia rodar com parâmetros errados).
- Centralizado `core/risk_gate.py` retornando `{allowed, reasons, checks}` — antes os gates estavam espalhados em `server.py` e `trade_engine.py`.
- Migration idempotente para `bar_history` (antes a tabela podia faltar em ambiente novo).
- Manifesto `docs/PARAM_PROFILE.md` com **drift guard** automatizado para garantir que produção e backtest usem os mesmos parâmetros.
- Reconciler `scripts/reconcile_paper_vs_backtest.py` para comparar P&L paper vs backtest com janelas alinhadas (5 estados: BLOCKED/PASS/FAIL/MISSING_BACKTEST/WINDOW_NOT_COVERED).
- Política de risco operacional: `MAX_TRADES_PER_DAY`, `DAILY_LOSS_LIMIT_BRL`, `LOSS_COOLDOWN_MIN`, `BLOCK_ON_MT5_DISCONNECT`.
- Nomenclatura DOL/WDO documentada (não havia contrato cheio — sempre foi mini dólar).
- Lint frontend: 32 erros → **0 erros / 0 warnings**.
- Race condition real corrigida em `_eg_cache` (FastAPI síncrono usa threadpool, dois polls colidiam no dict — agora protegido por `threading.Lock`).

**Impacto:** TASK-2 (live MT5) destravada. Sem essa base, ligar live era apostar.

---

## 2. Execution Timeline Live — TASK-4 (5 slices) ✅ Done

**Problema:** quando o sistema não abria trade, o operador não sabia *por quê* — era um buraco preto. Não dava para distinguir "ainda não tem sinal" de "gate de cointegração bloqueou" de "MT5 desconectou".

**O que foi feito:**
- Novo módulo `core/execution_timeline.py` + tabela `execution_timeline` com WAL ligado.
- Funil completo emitido a cada barra: **DATA → INDICATORS → ELIGIBILITY → RISK → SIGNAL → ORDER → EXECUTION → EXIT**.
- Cada evento carrega `value`, `threshold`, `operator`, `distance` — operador vê *quão longe* está de passar o gate.
- Endpoint JSON `/api/execution-timeline` + página HTML standalone `/execution-timeline` (Jinja2).
- Painel React `ExecutionTimelinePanel` integrado ao dashboard principal.
- Helpers `current_bottleneck()` e `current_live_issue()` mostram o "primeiro gate que reprovou na última barra fechada" e "última falha crítica não recuperada".

**Impacto:** o gestor agora consegue olhar a tela e entender em segundos por que o motor não abriu trade hoje. Auditoria do funil deixou de exigir leitura de log.

---

## 3. Execution Timeline Replay (backtest auditável por data) — TASK-8 (5 slices) ✅ Done

**Problema:** mesmo com a timeline live, ainda não dava para ir em um pregão antigo e perguntar "por que o motor não operou em 08/05?". O histórico era reconstruído na cabeça.

**O que foi feito:**
- `bar_history` agora persiste os 5 indicadores que o replay precisa: `eg_pvalue`, `rho`, `rho_level`, `beta_value`, `beta_delta_pct`.
- Script `scripts/replay_execution_timeline.py` reconstrói o funil bar-a-bar a partir do `bar_history`, usando as mesmas funções centrais do live (`risk_gate`, `TradeEngine.evaluate`).
- Replay roda em **DB isolado** (`replays/execution_timeline_<data>.db`) — nunca polui o `trades.db` live.
- Endpoint `/api/execution-timeline?mode=replay&date=YYYY-MM-DD` + UI com toggle Live/Replay e date picker (auto-submit ao trocar modo/data).
- Botão "Gerar replay" na própria página, com lock para impedir runs concorrentes da mesma data.
- Garantia testada: replay **nunca** importa `MetaTrader5` nem chama `order_send`.

**Impacto:** auditoria completa por pregão, sem terminal MT5 e sem risco de poluição da base live.

---

## 4. Backfill Histórico via MT5 — TASK-10 ✅ Done

**Problema:** o replay de 08/05 só processava **18 de 112 barras**. As primeiras 90 não tinham janela histórica suficiente para os indicadores; outras 4 não tinham `di_price`.

**O que foi feito:**
- `scripts/backfill_bar_history_indicators.py` ganhou modo `--fetch-mt5` que lê histórico M5 de WIN/WDO/DI por `copy_rates_range`.
- Janela de warmup configurável por `--mt5-warmup-days`.
- Backup automático antes de qualquer escrita; preserva valores existentes (overwrite explícito).
- Garantia testada: o backfill nunca chama `order_send`.

**Impacto medido em 08/05:**

| Métrica | Antes | Depois |
|---|---|---|
| Bars processadas no replay | 18 / 112 | **108 / 115** |
| `eg_pvalue` NULL | 90 | 2 |
| `rho` / `beta_value` NULL | 90 | 2 |

---

## 5. Trades no Dashboard — TASK-1 🟡 In Progress (validação visual pendente)

**Problema:** o gestor pediu paridade com o backtest — entradas/saídas precisavam aparecer **dentro** dos gráficos do dashboard, não só na tabela do PerformancePanel.

**O que foi feito:**
- Novo endpoint `trades_today` em `/api/v2/regime`.
- Marcadores **▲ BUY / ▼ SELL / ■ saída** plotados em `SignalHistogram`, `ZScoreChart` e `IndexChart`.
- Tooltip mostra estratégia, direção, z_in, exit_reason, P&L.
- Trades em aberto mostram entrada sem saída.

**Pendente:** validação visual ponta-a-ponta com dashboard rodando em pregão real.

---

## 6. Execução Live no MT5 — TASK-2 🟡 In Progress (scaffold pronto, smoke test pendente)

**Problema:** TradeEngine era 100% paper. Para a primeira ordem real na XP DEMO, precisávamos de schema preparado para reconciliação MT5↔SQLite, magic numbers por estratégia, idempotência em restart e desligamento limpo via flag.

**O que foi feito:**
- Flag `LIVE_ORDERS=False` (default seguro) em `core/config.py`.
- Migration aditiva em `matador_ops`: `mt5_ticket_in`, `mt5_ticket_out`, `mt5_magic`, `live`.
- Magic distinto por estratégia (770001/770002/770003) — permite separar posições no MT5.
- Helpers `send_market_order` e `close_position_by_ticket` em `core/mt5_client.py`.
- `TradeEngine._open_trade` / `_close_trade` integrados atrás da flag: falha de envio **não** insere linha; falha de close mantém OPEN (próximo poll re-tenta).
- Dashboard mostra `risk_gate.reasons` para distinguir "sem entrada" de "gate bloqueado".

**Pendente:**
- Reconciliação no startup (3 estados: match / fantasma SQLite / órfã MT5).
- Suite `tests/test_trade_engine_live.py`.
- Smoke test em conta XP DEMO 52033102 com pelo menos um trade real aberto/fechado.

---

## 7. Bugs operacionais corrigidos com impacto direto

| Commit | Problema | Impacto |
|---|---|---|
| `b28f568` | DI usava Kalman quando deveria ser OLS; z-score do DI sofria mutação fora do filtro | Sinal DI estava sendo distorcido — gate ficava ruidoso |
| `82e9a2d` | `bar_history` na view live mostrava barras de outros dias | Dashboard exibia contexto enganoso no início do pregão |
| `62ca57e` | `wdo_price` e `di_price` não eram persistidos | Replay e backtest dependiam disso — sem essa correção, TASK-8 era impossível |
| `f537cb0` | TradeEngine poller dependia de outros endpoints terminarem | Se um endpoint travava, o motor inteiro parava de avaliar entradas |
| `5d16841` | Eventos da timeline desalinhados com semântica de barra fechada | Entradas eram avaliadas com dados de barra ainda aberta |

---

## 8. Pipeline da próxima semana

| Tarefa | Estado | O que falta |
|---|---|---|
| **TASK-2** Live MT5 | In Progress | Reconcile + tests + smoke test DEMO |
| **TASK-1** Trades no Dashboard | In Progress | Validação visual em pregão |
| **TASK-9** Replay no painel React | To Do | Levar o toggle Live/Replay para o React (hoje só na Jinja) |
| **TASK-7** Revalidar janela `ENTRY_START/END` (10:00–17:25) | To Do | Decisão de produto com gestor |
| **TASK-5** Backfill de gaps de timeline | To Do | Baixa prioridade |
| **TASK-6** Watchdog systemd para poller travado | To Do | Baixa prioridade |

---

## Métricas da semana

- **Commits no período:** 60 (52 ainda não publicados em `origin/main`).
- **Tests:** 228 passing.
- **Frontend:** lint zero, build verde.
- **Tasks fechadas com Done:** TASK-3, TASK-4 (5 slices), TASK-8 (5 slices), TASK-10.
- **Tasks ativas:** TASK-1, TASK-2.
