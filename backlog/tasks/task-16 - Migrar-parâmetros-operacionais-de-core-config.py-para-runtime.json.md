---
id: TASK-16
title: Migrar parâmetros operacionais de core/config.py para runtime.json
status: To Do
assignee: []
created_date: '2026-05-12 19:36'
labels:
  - refactor
  - runtime-config
  - config-migration
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Hoje a separação entre `core/config.py` (constantes hardcoded, requer restart) e `config/runtime.json` (hot-reload via `/api/runtime-config`) é inconsistente. Parâmetros que afetam diretamente o gate de risco e entradas estão fora do `runtime.json`:

| Parâmetro | Onde mora | Hot-reload? |
|---|---|---|
| `rho_breakdown_level`, `eg_strategies`, `eg_threshold`, `eg_bars`, `eg_recalc`, `beta_delta_max`, `z_anomaly` | `config/runtime.json` | ✅ |
| **`WINDOW`** (ρ/β rolling) | `core/config.py` | ❌ |
| **`Z_ENTRY`** | `core/config.py` | ❌ |
| **`ENTRY_START_H/M`, `ENTRY_END_H/M`** | `core/config.py` | ❌ |
| **`FORCE_CLOSE_H/M`** | `core/config.py` | ❌ |
| **`BUY_SL/TP/BE_ACT/BE_LOCK`** | `core/config.py` | ❌ |
| **`SELL_SL/TP/BE_ACT/BE_LOCK`** | `core/config.py` | ❌ |

Motivação concreta: relatório do Miqueias (`~/relatorio_miqueias1.md`) recomenda mudar `WINDOW` de 90→240 para destravar o gate em abril; hoje isso exige restart e edit no `core/config.py`. Mesma fricção em qualquer reajuste de `Z_ENTRY` ou janela de sessão.

## Princípio da separação

- **`config/runtime.json`** → params *operáveis em produção* (thresholds, janelas, bypass flags, horários).
- **`core/config.py`** → constantes estruturais (símbolos, caminho MT5, Kalman Q/R, magic numbers, paths).

## Slices

- **16.1** Schema: estender `FIELDS`, `DEFAULTS`, validators em `core/runtime_config.py` + testes. Safe durante mercado.
- **16.2** Consumer `signals.py` — `WINDOW`, `Z_ENTRY`, `Z_ATTENTION` via profile.
- **16.3** Consumer `risk_gate.py` — `ENTRY_*`, `FORCE_CLOSE_*` via profile.
- **16.4** Consumer `trade_engine.py` — `BUY/SELL SL/TP/BE_*` capturados no `_open_trade` (NÃO afeta posições já abertas).
- **16.5** Cleanup: `core/config.py` continua exportando como defaults; remover imports diretos onde profile cobre.
- **16.6** Frontend: adicionar inputs no slideover `/config` UI.

## Constraints

- Executar slices 16.2-16.5 **fora do horário de mercado** (após 17:40 BRT, posições fechadas).
- Cada slice mantém defaults backward-compatible (backfill em `_backfill_missing_fields`).
- `BUY_*` e `SELL_*` lidos *no momento do open_trade*; mudanças mid-position não devem afetar slots já abertos (SL/TP gravados no `position` dict).
- Validators com bounds defensivos (ex: `Z_ENTRY` em [0.1, 5.0], `ENTRY_END_H` em [0, 23]).

## Acceptance Criteria
<!-- AC:BEGIN -->
- AC1: Schema novo aceita config legado (backfill) sem 500 no GET.
- AC2: POST com valor inválido retorna 400 com mensagem específica.
- AC3: Mudança de `WINDOW` via POST `/api/runtime-config` reflete na próxima barra fechada sem restart.
- AC4: Mudança de `BUY_SL` via POST NÃO altera posições já abertas (testado por unit + integração).
- AC5: Frontend exibe e edita os novos campos com mesma UX dos campos existentes.
<!-- SECTION:DESCRIPTION:END -->

- [ ] #1 Schema runtime_config aceita config legado sem 500 (backfill)
- [ ] #2 Validators rejeitam valores fora dos bounds com 400 + mensagem
- [ ] #3 WINDOW via POST reflete na próxima barra fechada sem restart
- [ ] #4 Mudança de BUY_SL/TP via POST não afeta posições já abertas
- [ ] #5 Frontend /config slideover edita os novos campos
<!-- AC:END -->
