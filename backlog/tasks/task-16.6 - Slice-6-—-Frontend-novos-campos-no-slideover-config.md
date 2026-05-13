---
id: TASK-16.6
title: 'Slice 6 — Frontend: novos campos no slideover /config'
status: Done
assignee: []
created_date: '2026-05-12 19:38'
updated_date: '2026-05-13 14:32'
labels:
  - frontend
  - ui
  - runtime-config
dependencies: []
parent_task_id: TASK-16
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Escopo

Adicionar inputs no slideover Runtime Config (`regime-dashboard/`) para os 16 novos campos. UX consistente com os campos existentes.

## Tarefas

1. Identificar o componente que renderiza `/api/runtime-config` no React.
2. Adicionar grupos visuais:
   - **Janela & thresholds**: `window`, `z_entry`
   - **Janela de sessão**: `entry_start_h/m`, `entry_end_h/m`, `force_close_h/m`
   - **Risk (BUY)**: `buy_sl`, `buy_tp`, `buy_be_act`, `buy_be_lock`
   - **Risk (SELL)**: `sell_sl`, `sell_tp`, `sell_be_act`, `sell_be_lock`
3. Inputs com validation client-side (bounds idênticos ao backend).
4. Submit chama POST `/api/runtime-config` (já existe).

## Acceptance criteria

- AC1: Slideover mostra os 16 novos campos com defaults atuais.
- AC2: Edit + Save persiste em runtime.json e reflete em `/api/runtime-config` GET.
- AC3: Validation rejeita valores fora de bounds sem chamar API.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## TASK-16.6 — Frontend runtime-config fields

### Mudanças

**`regime-dashboard/src/components/RuntimeConfigSlideover.jsx`**
- Slideover `/CONFIG` agora renderiza os campos operacionais migrados para runtime config:
  - Janela & thresholds: `window`, `z_entry`, `z_attention`.
  - Janela de sessão: `entry_start_h/m`, `entry_end_h/m`, `force_close_h/m`.
  - Risk BUY: `buy_sl`, `buy_tp`, `buy_be_act`, `buy_be_lock`.
  - Risk SELL: `sell_sl`, `sell_tp`, `sell_be_act`, `sell_be_lock`.
- Campos existentes de EG/rho/beta/z_anomaly foram mantidos e agrupados em "Cointegração".
- Client-side validation espelha `core/runtime_config.py`:
  - ranges numéricos e inteiros;
  - `z_attention < z_entry`;
  - `entry_start < entry_end <= force_close`;
  - regras BE/TP por lado (`be_lock <= be_act`, `be_lock < tp`, `be_act <= tp`).
- Botões de salvar ficam desabilitados quando o perfil alvo está inválido; `handleSave()` também faz guard antes do `POST /api/runtime-config`.

### Verificação

- `npm run lint` — clean.
- `npm run build` — clean; somente warning conhecido de chunk > 500 kB do Vite.
- `python3 -m pytest tests/test_runtime_config.py -q` — 144 passed.

### Nota

A task original citava "16 novos campos" e listava grupos sem `z_attention`; a UI inclui `z_attention` porque ele já foi migrado e consumido pelo engine na TASK-16.2/16.5.
<!-- SECTION:FINAL_SUMMARY:END -->
