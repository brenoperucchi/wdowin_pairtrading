---
id: TASK-11
title: Runtime Configuration UI + perfis Live/Replay
status: In Progress
assignee: []
created_date: '2026-05-10 22:02'
updated_date: '2026-05-11 13:00'
labels:
  - config
  - ui
  - replay
  - live
  - risk-gate
dependencies: []
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Permitir alterar parâmetros de risco/cointegração via UI (slideover) com 2 perfis separados (Live e Replay), persistindo em `config/runtime.json`.

**Motivação:** investigação em 2026-05-10 mostrou que o sistema atual bloqueia 100% das entradas em 05-06/07/08 por `EG_NOT_COINTEGRATED`, enquanto a versão do Miqueias (https://github.com/miqueiasa1/wdowin_pairtrading) opera nesses dias usando janela de cointegração maior (2240 bars) e cálculo 1×/dia. Precisamos poder **calibrar** esses parâmetros sem editar código, primeiro pra reproduzir o comportamento do gestor e depois pra otimizar.

**Decisões de UI:**
- Slideover lateral direito (dashboard segue visível)
- Tabs/seções: "Live" e "Replay"
- Botões: Salvar Live | Salvar Replay | Salvar e Rodar Replay

**Parâmetros (escopo desta task):**
- `eg_threshold` (float, default 0.10)
- `eg_bars` (int, default 2240 live + replay — espelha gestor Miqueias)
- `eg_recalc` (str, "bar" | "daily" — default "daily" em ambos perfis)
- `rho_breakdown_level` (int, default 2)
- `beta_delta_max` (float, default 25.0)
- `eg_strategies` (list[str], default ["CONS_BASE", "WDO_NWE"] — adicionado em Slice C)

**Persistência:** `config/runtime.json` com 2 perfis. Server lê do perfil live a cada poll (Slice D — hot-reload por POST sem restart). Replay lê de `replay` profile ou aceita CLI overrides.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 GET /api/runtime-config retorna {live:{...}, replay:{...}} com defaults se config/runtime.json não existir
- [x] #2 POST /api/runtime-config valida e persiste o JSON; falha 400 em campos inválidos (ranges, tipos)
- [x] #3 Slideover lateral direito abre por botão no header do dashboard, mostra os 6 params em 2 perfis (Live/Replay)
- [x] #4 Botão 'Salvar Replay' grava só perfil replay; 'Salvar Live' grava só perfil live; 'Salvar e Rodar Replay' grava + dispara /api/execution-timeline/generate
- [x] #5 scripts/replay_execution_timeline.py lê o perfil replay e aplica os 6 params; CLI flags --eg-threshold/--eg-bars/--eg-recalc/--rho-breakdown-level/--beta-delta-max/--eg-strategies sobrepõem o JSON
- [x] #6 EG do replay recomputa pvalue na hora usando win/wdo do bar_history com janela --eg-bars; modo daily usa cache por date_str
- [x] #7 Live (server.py) lê do perfil live a cada poll; após POST hot-reload reflete no próximo poll sem restart (todos os 6 params)
- [ ] #8 Tests: load/save runtime_config; replay com --eg-bars 2240 --eg-recalc daily reproduz trades em datas onde Miqueias opera; UI lint+build OK
<!-- AC:END -->
