---
id: TASK-6
title: Systemd watchdog + alerta de poller travado
status: To Do
assignee: []
created_date: '2026-05-09 06:55'
labels:
  - ops
  - reliability
milestone: m-1
dependencies: []
references:
  - scripts/systemd/pairtrading-server.service
  - server.py
  - f537cb0
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Complemento do fix em `f537cb0` (poller interno + endpoint `/health` reportando última execução do trade engine).

`/health` já permite observar se o engine travou, mas não há mecanismo automático para:
1. **Restart se travar**: systemd não sabe que o processo está vivo mas o loop interno congelou
2. **Notificação**: nenhum alerta dispara se o poller parar de avançar

**Proposta**
- `WatchdogSec=30` no `pairtrading-server.service`
- Loop do poller chama `sd_notify("WATCHDOG=1")` a cada iteração bem-sucedida (após `regime_v2()` retornar)
- Se watchdog expirar, systemd restarta o processo automaticamente
- Opcional: webhook/log estruturado de "poller_stalled" para o alerta externo (Slack/Discord/email) — escopo separado se necessário

**Why**
Sem isso, o cenário do bug original pode reincidir silenciosamente: poller existe mas trava em alguma exceção dentro de `regime_v2()` (ex.: MT5 hang, SQLite lock), e ninguém saberia até abrir o dashboard.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `pairtrading-server.service` tem `WatchdogSec=30` (ou valor apropriado)
- [ ] #2 Poller chama `sd_notify('WATCHDOG=1')` após cada iteração bem-sucedida do `regime_v2()`
- [ ] #3 Teste manual: matar o loop com `kill -STOP` no PID interno (ou forçar exception) → systemd restarta em <2*WatchdogSec
- [ ] #4 `journalctl` registra o restart com motivo claro (watchdog timeout)
<!-- AC:END -->
