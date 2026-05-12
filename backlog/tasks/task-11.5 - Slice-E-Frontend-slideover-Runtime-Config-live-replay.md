---
id: TASK-11.5
title: '[Slice E] Frontend slideover Runtime Config (live + replay)'
status: Done
assignee: []
created_date: '2026-05-11 13:00'
updated_date: '2026-05-11 13:44'
labels:
  - live
  - ui
  - config
  - replay
dependencies: []
references:
  - regime-dashboard/src/components/RuntimeConfigSlideover.jsx
  - regime-dashboard/src/App.jsx
  - 'server.py:1755 GET /api/runtime-config'
  - 'server.py:1768 POST /api/runtime-config'
  - 'server.py:1640 POST /api/execution-timeline/generate'
parent_task_id: TASK-11
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Slideover lateral direito no dashboard React para editar `live`/`replay` profiles, com os 3 botões de save e disparo de replay.

## Mudanças

**Novo `regime-dashboard/src/components/RuntimeConfigSlideover.jsx`**
- Overlay + painel direito (420px), ESC para fechar.
- Tabs Live/Replay (independentes).
- 6 campos por perfil: eg_threshold, eg_bars, eg_recalc (select), rho_breakdown_level, beta_delta_max, eg_strategies (toggle chips CONS_BASE/WDO_NWE/DI_NWE).
- 3 botões: **SALVAR LIVE**, **SALVAR REPLAY**, **SALVAR E RODAR REPLAY**.
- Whole-document POST mantém o perfil oposto intocado (lê do `original` no momento do save) — evita "vazar" edição entre tabs.
- "Salvar e Rodar Replay" só habilita com data preenchida (input dentro da tab Replay; default vem do date picker do topbar).
- Feedback inline: erro de validação do backend (400), status de sucesso com trades_opened/pnl quando replay roda.

**`regime-dashboard/src/App.jsx`**
- Botão "CONFIG" no topbar (estilo dourado, mesmo set visual do MATADOR badge).
- Estado `configOpen` + mount do slideover passando `selectedDate` como `defaultReplayDate`.

## Não-escopo

- Auto-refresh do dashboard após save (live engine já hot-reload no próximo poll por TASK-11.4).
- Side-by-side diff de "antes/depois" no UI.
- Histórico de mudanças de config.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Botão CONFIG no topbar abre o slideover lateral direito
- [x] #2 Slideover tem tabs Live e Replay; tab ativa destaca em dourado
- [x] #3 Cada perfil mostra os 6 campos com labels, hints e inputs apropriados (number/select/chips)
- [x] #4 POST /api/runtime-config envia o documento inteiro; perfil oposto preservado do original
- [x] #5 Erros de validação (400) são exibidos inline; sucesso mostra '✓ Perfil X salvo.'
- [x] #6 'Salvar e Rodar Replay' só habilita com data preenchida; após POST do config dispara /api/execution-timeline/generate?date=...
- [x] #7 Resultado do replay mostra trades_opened e pnl no rodapé de status
- [x] #8 ESLint sem warnings; vite build sem erros
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## Resumo

Slideover lateral entregue, integrado ao topbar via botão **CONFIG**. Edita os 6 campos por perfil (Live/Replay), com whole-document POST e disparo opcional de replay server-side.

## Verificação

- `npm run lint` → sem warnings/erros.
- `npm run build` → build OK (782 KB, 3.75s).
- Lint + build são os únicos sinais automatizáveis sem rodar o backend Windows (MT5). **Não testei o slideover em browser real contra a API** — o usuário deve fazer um smoke manual: clicar CONFIG, editar `eg_threshold` no Live, salvar, conferir que próximo poll do `/api/v2/regime` reflete o novo threshold (Slice D já validou o hot-reload server-side).

## Decisões de UX

- 420px de largura: cabe os 6 campos sem rolagem em viewports de 1080p+.
- "Salvar Live" e "Salvar Replay" mandam o documento inteiro, mas o lado oposto vem do `original` (snapshot do GET inicial). Isso evita que uma edição no tab Live "vaze" pro tab Replay antes do save.
- Replay date é input próprio do slideover (com default herdado do date picker do topbar). Mantém o fluxo "configurar e disparar" coeso dentro do painel.

## Pendências (ficam abertas no TASK-11)

- AC #8 do parent: teste automatizado de replay com `--eg-bars 2240 --eg-recalc daily` reproduzindo trades em datas Miqueias-positivas — ainda manual.

## Patch follow-up (review)

Segundo round de revisão apontou 2 issues Low de UX no slideover; ambos corrigidos em `RuntimeConfigSlideover.jsx`:

1. **`defaultReplayDate` ficando stale após primeira edição manual** — adicionado state `replayDateTouched`. O `useEffect` que sincroniza `replayDate` com a prop só dispara enquanto `!replayDateTouched`; o `onChange` do input de data marca touched=true; abrir o slideover (`isOpen`) reseta o flag. Resultado: a primeira abertura herda a data do topbar, edições manuais são respeitadas, e fechar+reabrir volta a herdar.

2. **`SALVAR E RODAR REPLAY` visível na aba Live** — botão envolvido em `{activeTab === "replay" && (...)}`. Aba Live agora mostra apenas `SALVAR LIVE`. Também substituí o indicador único de dirty por `dirtyByProfile` (calculado por perfil via JSON.stringify) e duas mensagens de aviso: uma para mudanças no perfil ativo e outra para mudanças não-salvas no perfil oposto (`• Mudanças não salvas em REPLAY — serão descartadas se você salvar LIVE`). Operador agora vê explicitamente quando vai descartar trabalho cross-tab.

## Verificação pós-patch

- `npm run lint` → clean.
- `npm run build` → OK (782.73 KB, 2.19s).
- Smoke manual ainda pendente do usuário (mesma observação do resumo original).
<!-- SECTION:FINAL_SUMMARY:END -->
