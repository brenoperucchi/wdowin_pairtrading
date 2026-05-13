---
id: TASK-17.3
title: >-
  Slice A.5 — SimulationProfile dentro de cada perfil (live/replay) em
  runtime_config
status: Done
assignee: []
created_date: '2026-05-13 01:19'
updated_date: '2026-05-13 03:20'
labels:
  - runtime-config
  - simulation
dependencies: []
parent_task_id: TASK-17
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Objetivo

Adicionar bloco `simulation` aninhado **dentro** de cada perfil (`live`, `replay`) em `runtime_config.json` + schema correspondente em `core/runtime_config.py`.

## Por que aninhado (codex)

Top-level `simulation` quebra o schema atual (perfis com campos estritos). Aninhar dentro de cada perfil preserva o contrato existente e deixa o default conservador: live com `enabled=false` (nunca simula); replay com `enabled=false` por default também (regressão zero até habilitar explicitamente).

## Estrutura

```json
{
  "live": {
    ...campos atuais...,
    "simulation": {
      "enabled": false,
      "entry_slippage_pts": 5.0,
      "exit_slippage_pts": 5.0,
      "cost_per_contract_rt_brl": 1.00,
      "intra_bar_sl_tp": true,
      "exit_at_sl_tp_level": true,
      "conflict_rule": "sl_first"
    }
  },
  "replay": { ... idem, com enabled = false por default ... }
}
```

## Escopo

- `core/runtime_config.py`: SIMULATION_FIELDS, validators, backfill_missing_fields (perfis legados ganham bloco `simulation` desativado).
- Validators com bounds: slippage ∈ [0, 50], cost ∈ [0, 50], conflict_rule ∈ {sl_first, tp_first, worst}.
- `tests/test_runtime_config.py` (estender): GET com config legado não 500a; POST com slippage=999 retorna 400; POST com conflict_rule="foo" retorna 400.

## Safe durante mercado

Sim — campos opcionais com defaults conservadores; engine ainda não os lê (vem em A.6).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 runtime_config.json (live, replay) aceita bloco simulation aninhado
- [x] #2 Config legado sem bloco simulation é normalizado com enabled=false + defaults (sem 500 no GET)
- [x] #3 POST com valor fora de bounds retorna 400 com mensagem específica do campo
- [x] #4 POST com conflict_rule inválido retorna 400
- [x] #5 Validators rejeitam tipos errados (string em entry_slippage_pts, etc)
- [x] #6 Tests novos em tests/test_runtime_config.py cobrem cenários acima
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Implementação

**Arquivos modificados:**
- `core/runtime_config.py` — adicionado bloco `simulation` aninhado por perfil
- `config/runtime.json` — committed config recebe bloco `simulation` (enabled=false) em ambos os perfis
- `tests/test_runtime_config.py` — 26 testes novos
- `tests/test_execution_timeline_server.py` — payload de `test_runtime_config_post_persists_and_returns_normalised` recebe `simulation` (POST agora exige o bloco)

### Schema (core/runtime_config.py)

- `SIMULATION_FIELDS = (enabled, entry_slippage_pts, exit_slippage_pts, cost_per_contract_rt_brl, intra_bar_sl_tp, exit_at_sl_tp_level, conflict_rule)`
- `CONFLICT_RULES = ("sl_first", "tp_first", "worst")`
- `SIMULATION_DEFAULTS = {enabled: False, entry/exit_slippage: 5.0, cost_rt: 1.0, intra_bar: True, exit_at_level: True, conflict: "sl_first"}`
- `simulation` adicionado a `FIELDS` → integra ao loop de validação por-perfil; `DEFAULTS[live|replay]` recebem `"simulation": copy.deepcopy(SIMULATION_DEFAULTS)`.

### Validator (`_validate_simulation`)

- Strict: rejeita extra/missing keys, bool exato para `enabled/intra_bar_sl_tp/exit_at_sl_tp_level` (não aceita int como bool), número (não bool) para floats com bounds `[0.0, 100.0]`.
- `conflict_rule` enum-only.
- Mensagens qualificadas: `"{profile}.simulation.{field} must be ..."`.

### Backfill (`_backfill_missing_fields`)

Dois níveis de tolerância no read path:
1. Perfil sem bloco `simulation` → injeta `SIMULATION_DEFAULTS` completo.
2. Perfil com `simulation` parcial → preserva valores do operador e backfila apenas as sub-keys ausentes.

Save permanece strict — POST sem `simulation` ou sem alguma sub-key → 400.

### Default = disabled em ambos os perfis

Per plan §A.5: `enabled=false` em live **e** replay. Replay opt-in é ação explícita do operador (POST), não acontece no deploy. Garante regressão zero quando A.6 implementar a leitura do bloco.

### Testes (74 total no arquivo; 26 novos)

Cobertura:
- `test_simulation_defaults_disabled_in_both_profiles` — AC#1 (paridade)
- `test_simulation_defaults_in_committed_runtime_json` — AC#1
- `test_simulation_roundtrip_with_enabled_replay` — save/load preserva flags do operador
- `test_simulation_validation_rejects_bad_values` parametrizado (17 casos: bool-as-int, string-as-number, out-of-bounds, conflict_rule inválido, None, etc.) — ACs #3, #4, #5
- `test_simulation_validation_rejects_unknown_subfield` — AC#5 (defesa contra typos)
- `test_simulation_validation_requires_all_subfields` — AC#5
- `test_simulation_validation_rejects_when_not_object` — AC#5
- `test_load_backfills_missing_simulation_block` — AC#2 (legacy sem bloco)
- `test_load_backfills_missing_simulation_subfields` — AC#2 (legacy com bloco parcial)
- `test_save_rejects_missing_simulation_block` — strict save

### Verificação

Full suite: **431 passed, 19 skipped, 1 warning** (zero regressões; +28 testes vs baseline A.4).

### Pendência (não bloqueante)

Frontend ainda não exibe/edita o bloco `simulation`. Não é necessário pra A.6 (engine consome direto via `get_profile("replay")["simulation"]`). Pode entrar como tarefa cosmética separada quando A.6/A.7 estiver consolidado.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Slice A.5 entregue: `simulation` block aninhado em cada perfil (live/replay) do `runtime_config`, com validators strict e backfill tolerante para configs legados.

**O que funciona:**
- DEFAULTS de `simulation` em ambos os perfis: `enabled=false`, slippages=5.0pt, cost_rt=1.0, intra_bar/exit_at_level=true, conflict_rule=sl_first
- Save endpoint exige o bloco completo (POST sem `simulation` → 400)
- GET tolera configs antigos: bloco ausente → SIMULATION_DEFAULTS; bloco parcial → preserva flags do operador e backfila sub-keys
- Type-checks rigorosos: `enabled` precisa ser bool (não int/string); floats não aceitam bool; `conflict_rule` é enum
- 26 testes novos cobrem todos os 6 ACs

**Próximo slice (A.6):** `TradeEngine.evaluate()` recebe `simulation_profile=None` opcional. Quando ativo: slippage no entry/exit, intra-bar SL/TP via H/L, custo round-trip no PnL, conflict_rule pra TP+SL no mesmo candle. No-op quando `enabled=False` (regressão bit-exata).

**Não bloqueante:** frontend ainda não tem UI pro bloco `simulation` (operador edita via POST direto até A.6 estabilizar a leitura).
<!-- SECTION:FINAL_SUMMARY:END -->
