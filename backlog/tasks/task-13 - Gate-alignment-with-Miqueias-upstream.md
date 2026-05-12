---
id: TASK-13
title: Gate alignment with Miqueias upstream
status: Done
assignee: []
created_date: '2026-05-11 18:55'
updated_date: '2026-05-11 21:09'
labels:
  - gate
  - risk
  - alignment
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Investigação em 2026-05-11 comparando nosso `risk_gate` com o upstream (https://github.com/miqueiasa1/wdowin_pairtrading server.py:608) revelou 3 gaps onde nosso sistema opera mais permissivo que o reference:

1. **`beta_delta_max` default mais frouxo** — nosso runtime_config usa `25.0`, mas upstream bloqueia em `beta_status.level >= 2` = `|Δβ| >= 15%`. Em regime "morno" (15–25% drift) a gente abre trade que o upstream segura.
2. **`beta_unstable` não é hard-block** — upstream inclui `beta_unstable` no `safe_to_trade`. Nosso `_update_beta_state` calcula esse flag mas só expõe como metadata no payload; o `risk_gate` ignora.
3. **`Z_ANOMALY` (4.0) hardcoded** — não é editável via /CONFIG. Operador não consegue afrouxar/apertar sem editar `core/config.py`.

Esta task é guarda-chuva; cada gap vira uma subtarefa independente para review slice-by-slice.

## Não-escopo

- Mudar a tabela de classificação rho/beta em `core/signals.py` (essa permanece hardcoded; só o gate enforce muda).
- Reescrever `risk_gate` (mantém estrutura atual; só adiciona/ajusta kwargs).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Subtarefas 13.1, 13.2, 13.3 todas concluídas e revisadas
- [x] #2 CLAUDE.md `Regime health gates` reflete o estado final do código após as três slices
- [x] #3 Memória `feedback_slice_review_ritual` respeitada: cada subtarefa parou para review antes da próxima começar
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
## TASK-13 — Gate alignment with Miqueias upstream (Done)

Todos os 3 slices completados em 2026-05-11. Os 3 gaps identificados foram fechados:

### Slice 1 (TASK-13.1) — `beta_delta_max` default 25 → 15
- `runtime_config.DEFAULTS.live.beta_delta_max = 15.0` (replay já era 15.0).
- Teste `test_defaults_beta_delta_max_aligned_with_upstream`.

### Slice 2 (TASK-13.2) — `Z_ANOMALY` parametrizado via /CONFIG
- 7º campo do runtime_config: `z_anomaly` (default 4.0).
- `risk_gate` aceita kwarg com fallback para `core.config.Z_ANOMALY`.
- Slideover renderiza com validação `(0, 10]`.
- Replay script ganhou o campo na `ReplayRuntimeProfile`.

### Slice 3 (TASK-13.3) — `beta_unstable` como hard-block
- State machine `_win_beta_state` em server.py (bar-over-bar via `closed_bar_ts`).
- `risk_gate` ganhou kwarg `beta_unstable: bool` → reason `BETA_UNSTABLE`.
- Replay paridade: `beta_state` dict thread-through `_process_bar`.

### Estado final do gate (CLAUDE.md atualizado)

```
- rho_status.level >= rho_breakdown_level (default 2) → RHO_BREAKDOWN
- |Δβ| >= beta_delta_max (default 15.0 ambos profiles) → BETA_DRIFT
- eg_pvalue >= eg_threshold (default 0.10) → EG_NOT_COINTEGRATED (per-strategy)
- |z| >= z_anomaly (default 4.0) → Z_ANOMALY
- beta_unstable=True (bar-over-bar Δβ > 15%) → BETA_UNSTABLE
```

Tudo paridade com upstream `safe_to_trade and not beta_unstable`.

### Verificação cumulativa

- 308 pytest passed (+8 vs antes do TASK-13).
- npm run lint clean.
- npm run build 782.83 KB OK.
- Replay 2026-05-08 ainda produz SELL DI_NWE 10:15 → 10:35 BE_STOP -34 BRL.

### Slice-by-slice ritual

Cada subtarefa parou para review antes da próxima começar (memória `feedback_slice_review_ritual` respeitada): aprovação manual entre 13.1→13.2, 13.2→13.3, e agora fechamento da parent.
<!-- SECTION:FINAL_SUMMARY:END -->
