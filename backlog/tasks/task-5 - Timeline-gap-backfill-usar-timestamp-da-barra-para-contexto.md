---
id: TASK-5
title: Timeline gap/backfill + usar timestamp da barra para contexto
status: To Do
assignee: []
created_date: '2026-05-09 06:55'
labels:
  - timeline
  - observability
milestone: m-1
dependencies: []
references:
  - server.py
  - core/execution_timeline.py
  - core/risk_gate.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Resíduos da Execution Timeline (TASK-4) detectados em sessão de análise pós-deploy:

**Gap/backfill**
Cada chamada a `regime_v2()` emite eventos para apenas a barra mais recente confirmada (`tc[-2]`). Se o poller falhar, o serviço reiniciar, ou MT5 não advance entre dois polls, barras intermediárias ficam sem registro no funil — buraco no audit trail.

**Hora da barra vs hora do servidor**
`risk_gate(hour=now_dt.hour, minute=now_dt.minute, ...)` usa relógio do servidor para checar `_in_session`. Para o gate de **entrada** está correto (não abrir trade às 17:02 com sinal velho). Mas para o **timeline** isso pinta como `OUT_OF_SESSION` barras que fecharam dentro da janela — ruim para diagnóstico em replay/post-restart.

**Proposta**
- Backfill: detectar `_last_emitted_bar_ts → tc[-2]` com gap > 1 bar e emitir 1 evento `TIMELINE_GAP` (phase=DATA, status=INFO) com `bars_skipped` no payload, sem tentar reconstruir os dados intermediários.
- Hora da barra: na emissão do timeline (não no gate de entrada), checar `_in_session(closed_bar_ts→hora_local)` ao invés de `now_dt`. Mantém gate de entrada usando `now_dt`.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Gap > 1 barra entre `_last_emitted_bar_ts` e `tc[-2]` gera evento TIMELINE_GAP (phase=DATA, status=INFO) com `bars_skipped`
- [ ] #2 Eventos OUT_OF_SESSION no timeline são avaliados contra a hora da barra (`closed_bar_ts`), não `now_dt`
- [ ] #3 Gate de entrada (`risk_gate` chamado por `_build_gate`) continua usando `now_dt` — apenas a emissão do timeline muda
- [ ] #4 Testes: gap detection + session-by-bar-time vs session-by-now
<!-- AC:END -->
