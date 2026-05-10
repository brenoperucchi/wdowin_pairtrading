---
id: TASK-8.4
title: Slice D — UI Jinja /execution-timeline com toggle Live/Replay + date picker
status: To Do
assignee: []
created_date: '2026-05-09 17:14'
labels:
  - execution-timeline
  - replay
  - frontend-jinja
  - ui
dependencies: []
references:
  - templates/execution_timeline.html
  - server.py
parent_task_id: TASK-8
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Adicionar à página Jinja existente `/execution-timeline` o toggle Live × Replay + date picker, mostrando claramente em qual contexto o usuário está. Reutiliza tudo do template atual (tabela, filtros, summary).

Depende do Slice C (endpoint precisa aceitar `mode=replay`).

Escopo:
- Adicionar controle `mode=live|replay` no form de filtros + `<input type="date" name="date">`.
- Handler `/execution-timeline` (HTML) lê `mode` e `date`, monta o `db_path` igual ao endpoint JSON do Slice C, e renderiza com o mesmo template.
- Em modo replay: badge/banner no topo "Replay YYYY-MM-DD" e meta-refresh desabilitado (`refresh=0` força). Em modo live: comportamento atual preservado.
- Em caso de date inválida ou DB inexistente, mostrar mensagem amigável dentro do template (não 500).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Form de filtros tem `mode=live|replay` (radio/select) e `date` (input date), enviados via GET.
- [ ] #2 Modo live (default) mantém visual e auto-refresh atuais.
- [ ] #3 Modo replay com data válida e DB existente mostra eventos do DB de replay; banner indica `Replay YYYY-MM-DD`; meta-refresh desabilitado.
- [ ] #4 Modo replay com DB inexistente renderiza página com mensagem amigável ("Sem replay para esta data") em vez de 404/500.
- [ ] #5 Handler usa o mesmo path/validação do Slice C (sem duplicar regex de data).
- [ ] #6 QueryString preserva o estado: clicar Apply em replay mantém `mode=replay&date=...`.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 Subir o servidor, abrir `http://localhost:8080/execution-timeline?mode=replay&date=2026-05-08`, conferir banner e tabela.
- [ ] #2 Conferir manualmente que `mode=live` continua exibindo dados do `trades.db` em tempo real.
<!-- DOD:END -->
