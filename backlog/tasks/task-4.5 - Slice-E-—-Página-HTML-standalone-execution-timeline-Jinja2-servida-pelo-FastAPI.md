---
id: TASK-4.5
title: >-
  Slice E — Página HTML standalone /execution-timeline (Jinja2) servida pelo
  FastAPI
status: Done
assignee: []
created_date: '2026-05-08 19:36'
updated_date: '2026-05-08 19:53'
labels:
  - timeline
  - slice-e
  - backend
  - html
dependencies:
  - TASK-4.3
references:
  - /home/brenoperucchi/.claude/plans/stateful-toasting-pony.md
  - server.py
  - core/execution_timeline.py
parent_task_id: TASK-4
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Página HTML standalone para visualizar o execution timeline sem precisar do dashboard React (`npm run dev`) ligado. Renderizada server-side pelo FastAPI usando Jinja2; reusa as mesmas funções do `core/execution_timeline.py` consumidas pelo endpoint JSON. Útil para diagnóstico rápido em SSH/PM2 e quando o Vite não está rodando.

**Decisão de escopo (B)**: a página é adicional ao Slice D — o painel React em `regime-dashboard` continua sendo o canal principal; esta página é fallback operacional. JSON em `/api/execution-timeline` permanece intocado.

**Ordem**: executar imediatamente após Slice C (TASK-4.3), antes do Slice D (TASK-4.4).

**Arquivos**
- Novo: `templates/execution_timeline.html` — template Jinja2 (dark theme inline CSS, sem frameworks)
- Modificado: `server.py`
  - importar `Jinja2Templates` e `HTMLResponse`
  - instanciar `templates = Jinja2Templates(directory="templates")` próximo às outras inicializações
  - novo handler `GET /execution-timeline` (sem prefix `/api`) retornando `HTMLResponse`
  - reusa `load_timeline`, `current_bottleneck`, `current_live_issue` do mesmo módulo
- Sem alterações em `core/execution_timeline.py` (apenas consumidor)

**Comportamento da página**
- Bloco superior "Gargalo atual" (mesmo conteúdo de `summary.current_bottleneck`/`current_live_issue` do JSON):
  - Se `current_live_issue` existe, mostrar destacado em vermelho com phase/event/message/timestamp.
  - Senão, se `current_bottleneck` existe, mostrar phase, event, strategy, value, threshold, operator, distance (sinalizado), ratio_to_threshold.
  - Senão "Funil OK na última barra fechada" em verde.
- Tabela cronológica (mais recente no topo) com colunas: timestamp, phase, event, status, strategy, symbol, value, threshold, distance, message (truncada), correlation_id (8 chars).
  - Linhas BLOCKED/FAILED em vermelho, OK em verde, SKIPPED/INFO neutras.
- Filtros via query string (server-side): `?phase=&status=&strategy=&event=&limit=` (default `limit=200`, clamp em `_MAX_LOAD_LIMIT`).
- Auto-refresh: `<meta http-equiv="refresh" content="5">` (configurável via `?refresh=N`, 0 desliga).
- Footer com timestamp da renderização e link para `/api/execution-timeline` (JSON cru).

**Dependências**
- `jinja2` já é dependência transitiva do FastAPI mas não está em `requirements.txt` explícito — adicionar se necessário (verificar com `pip show jinja2`).

**Verificação**
- `pytest tests/` continua verde (target ≥ 169 + novos testes).
- Novo teste em `tests/test_execution_timeline_server.py`:
  - `test_execution_timeline_html_page_renders_summary_and_rows` — TestClient GET `/execution-timeline`, status 200, content-type `text/html`, body contém `Gargalo atual` + ao menos uma linha da tabela após gravar evento.
  - `test_execution_timeline_html_filters_by_phase` — query `?phase=ELIGIBILITY` retorna apenas linhas dessa fase.
- Manual: `curl http://localhost:8080/execution-timeline | head -50` mostra HTML coerente; abrir no browser confirma summary + tabela com dark theme.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 #1 Rota `GET /execution-timeline` registrada no `server.py` retornando `HTMLResponse` via Jinja2
- [x] #2 #2 Template `templates/execution_timeline.html` renderiza bloco de summary (current_bottleneck OR current_live_issue OR 'Funil OK') e tabela cronológica colorida por status
- [x] #3 #3 Filtros por query string funcionam: `?phase=`, `?status=`, `?strategy=`, `?event=`, `?limit=` (clampado em _MAX_LOAD_LIMIT)
- [x] #4 #4 Auto-refresh via meta refresh (default 5s, configurável via `?refresh=N`, `0` desliga)
- [x] #5 #5 Endpoint JSON `/api/execution-timeline` permanece inalterado e funcional
- [x] #6 #6 Pelo menos 2 testes novos em `tests/test_execution_timeline_server.py` cobrindo render do HTML e filtro por phase
- [x] #7 #7 `pytest tests/ -q` verde com novos testes incluídos
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Slice E entregue:

- Novo `templates/execution_timeline.html` com dark theme inline CSS, summary block (3 estados: live_issue / bottleneck / OK), filtros (form GET com phase/status/strategy/event/limit/refresh) e tabela cronológica (12 colunas) colorida por status (BLOCKED/FAILED red, OK green, SKIPPED skip-grey, INFO neutral).
- Novo handler `GET /execution-timeline` em `server.py:1417` retornando `HTMLResponse` via `Jinja2Templates(directory="templates")`. Reusa `load_timeline`, `current_bottleneck`, `current_live_issue` — zero alterações no `core/execution_timeline.py`.
- Auto-refresh: meta refresh com default `?refresh=5`, clamp em `[0, 3600]`, `0` desliga.
- Filtros: phase/status/strategy/event/limit passados a `load_timeline` que já clampa limit em `_MAX_LOAD_LIMIT=1000`. Query string preservada no link "JSON" do header pra abrir o mesmo recorte em raw.
- Endpoint JSON `/api/execution-timeline` (+ alias) **intacto**.
- `requirements.txt`: adicionado `jinja2==3.1.4` (não era transitiva explícita do FastAPI 0.136).
- `tests/test_execution_timeline_server.py`: +2 testes (`test_execution_timeline_html_page_renders_summary_and_rows`, `test_execution_timeline_html_filters_by_phase_and_disables_refresh`).

`PYTHONPATH=/tmp/codex-pytest:. python3 -m pytest tests/ -q` → **180 passed** (178 anterior + 2 novos), sem warnings.

Review concluido; Slice D / TASK-4.4 tambem concluido. TASK-4 pode ser fechado no parent.
<!-- SECTION:NOTES:END -->
