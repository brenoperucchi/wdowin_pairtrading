---
id: TASK-9
title: Replay Execution Timeline no painel React (regime-dashboard)
status: To Do
assignee: []
created_date: '2026-05-09 16:23'
updated_date: '2026-05-09 16:24'
labels:
  - execution-timeline
  - replay
  - frontend
  - react
  - dashboard
milestone: m-1
dependencies: []
references:
  - regime-dashboard/src/App.jsx
  - regime-dashboard/src/components/PerformancePanel.jsx
  - regime-dashboard/src/components/ZScoreChart.jsx
  - regime-dashboard/src/components/IndexChart.jsx
  - regime-dashboard/src/components/SignalHistogram.jsx
  - regime-dashboard/src/components/RegimeHealthPanel.jsx
  - server.py
  - templates/execution_timeline.html
documentation:
  - docs/MOTOR_E_FLUXO_DE_DADOS.md
  - CLAUDE.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Levar o modo Replay da Execution Timeline (entregue por TASK-8 na página Jinja `/execution-timeline`) para o painel React principal em `regime-dashboard/`, para que o operador veja o funil DATA→EXIT por data histórica dentro do mesmo dashboard que usa para acompanhar o live, sem precisar abrir uma página HTML separada.

Depende de TASK-8 estar concluída e em produção (endpoint `/api/execution-timeline?mode=replay&date=YYYY-MM-DD`, persistência de indicadores em `bar_history`, isolamento por DB de replay).

Contexto:
- Hoje o dashboard React (`regime-dashboard/`, porta 5174) consome `/api/v2/regime`, `/api/performance`, `/api/history` e `/api/di-regime`. Não consome `/api/execution-timeline` ainda.
- O React dashboard é a superfície que o operador usa rotineiramente; manter o replay só na Jinja cria ergonomia ruim ("para auditar pregão tenho que abrir outra aba HTML").
- Esta task é frontend-pesada: novo componente, rota/aba, fetcher, estado e UX para alternar Live × Replay sem confundir o operador sobre qual contexto está sendo exibido.

Não-objetivos:
- Não muda backend criado pela TASK-8 (endpoint, schema, isolamento por DB são reusados como estão).
- Não muda regra de janela operacional (segue TASK-7).
- Não substitui a página Jinja `/execution-timeline` — ambas continuam disponíveis.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Dashboard React (`regime-dashboard/`) ganha uma seção/aba/rota "Execution Timeline" que renderiza o funil DATA→INDICATORS→ELIGIBILITY→RISK→SIGNAL→ORDER→EXECUTION→EXIT consumindo `/api/execution-timeline`.
- [ ] #2 A nova seção oferece um seletor claro de modo Live × Replay; em modo Replay há um date picker (`YYYY-MM-DD`) que dispara fetch para `/api/execution-timeline?mode=replay&date=…`.
- [ ] #3 Quando o usuário está em Replay, a UI deixa explícito (badge, header, banner ou equivalente) que está visualizando dados históricos de uma data específica, e o auto-refresh do replay é desabilitado ou claramente separado do auto-refresh do live.
- [ ] #4 Em modo Live, o componente reaproveita o auto-refresh padrão do dashboard (~2.5s) e mostra `current_bottleneck` e `current_live_issue` no topo, paridade visual com o que a página Jinja já mostra.
- [ ] #5 A tabela de eventos suporta filtros equivalentes aos da Jinja: `phase`, `status`, `strategy`, `event`, `limit` — sem repetir 1:1 o layout, mas garantindo que o operador consegue filtrar.
- [ ] #6 Estado de Replay (data selecionada, filtros) sobrevive a navegação entre abas dentro do dashboard durante a mesma sessão (state lifted ou query params na URL); não precisa persistir entre reloads.
- [ ] #7 Erros do endpoint (404 para data sem replay, 5xx, payload vazio) são tratados com mensagem amigável dentro do componente; não derrubam outras partes do dashboard.
- [ ] #8 Replay nunca dispara fetch contra `/api/v2/regime` ou outros endpoints live com a data histórica — o componente só conversa com `/api/execution-timeline`.
- [ ] #9 A nova seção fica claramente separada dos componentes existentes (`ZScoreChart`, `IndexChart`, `RegimeHealthPanel`, `PerformancePanel`, `SignalHistogram`); não muda o comportamento deles em modo Live.
- [ ] #10 Tema visual segue o padrão do dashboard (dark financial, inline styles ou padrão atual do projeto), e a tabela é legível em viewport típico do operador (>=1280px).
- [ ] #11 Testes (Vitest/RTL ou equivalente já em uso) cobrem: render em modo Live com mock do endpoint, render em modo Replay com data válida, render com endpoint retornando erro, troca Live↔Replay limpando estado da request anterior.
- [ ] #12 Lint e build passam: `npm run lint` e `npm run build` em `regime-dashboard/`.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 `npm run build` em `regime-dashboard/` conclui sem warnings novos.
- [ ] #2 `npm run lint` em `regime-dashboard/` passa sem erros.
- [ ] #3 Verificação manual: abrir o dashboard, alternar Live↔Replay com a data `2026-05-08` (ou outra com replay disponível) e confirmar que o funil mostra eventos do replay e não polui as outras seções (`PerformancePanel`, `IndexChart` etc.) com dados históricos.
- [ ] #4 Verificação manual: tirar `replays/execution_timeline_<date>.db` do disco e confirmar que a UI mostra mensagem de erro amigável em vez de quebrar.
- [ ] #5 Verificação manual: deixar o dashboard aberto em modo Replay por >5 min e confirmar que ele NÃO faz polling automático contra `/api/execution-timeline?mode=replay`.
<!-- DOD:END -->
