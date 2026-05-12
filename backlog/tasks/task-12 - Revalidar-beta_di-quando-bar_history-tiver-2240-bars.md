---
id: TASK-12
title: Revalidar beta_di quando bar_history tiver >= 2240 bars
status: To Do
assignee: []
created_date: '2026-05-11 01:23'
labels:
  - regime
  - data-quality
  - post-slice-c
dependencies: []
references:
  - scripts/backfill_z_di.py
  - 'core/config.py:DI_BETA_REF_BARS'
  - 'core/signals.py:calc_beta_ols'
  - 'server.py:1839-1849'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Após o fix do z_di flip (Kalman → OLS no `/api/history`, 2026-05-10), o backfill recomputou `bar_history.z_di` para 2026-05-06/07/08. Durante o smoke, observamos um valor suspeito:

- **05-08**: `beta_di = +1537.xx` com janela de **540 bars** apenas
- **05-06 / 05-07**: `beta_di` fortemente negativo (consistente com a correlação WIN×DI)

Para um par negativamente correlacionado (WIN×DI), beta OLS deveria ser negativo. Um beta positivo isolado em um único dia, justamente quando a janela disponível é menor, sugere que **a regressão está distorcida por falta de histórico**.

A referência do Miqueias usa `coint(closes[-2240:])` — janela de 2240 bars. O `DI_BETA_REF_BARS` em `core/config.py` espelha isso, mas o backfill cai para `min(REF, len(history))`, e em 05-08 só havia ~540 bars de WIN/DI persistidos (o write coincidente de WDO+DI só foi corrigido em commit recente).

## Risco

Se o engine live rodar com beta_di distorcido, ele:
1. Inverte a direção do trade DI_NWE (BUY virando SELL e vice-versa)
2. Pode bloquear corretamente via `RHO_BREAKDOWN`, mas se passar, a entrada está errada
3. Z computado vai ficar com magnitude inflada (denominador errado), disparando trades em momentos não-intencionados

## Quando fazer

Quando `bar_history` tiver >= 2240 bars de WIN+DI persistidos simultaneamente (≈ 9 sessões de M5 completas a partir do dia em que o fix do `_persist_bars` começou a salvar WDO/DI). Estimativa: ~2026-05-21.

## Validação esperada

Rodar `scripts/backfill_z_di.py --dates <data>` em uma data dentro da janela completa e conferir:
- `beta_di` impresso é **negativo** (ordem de -0.x a -2.x esperado)
- `z_di` resultante está na mesma escala que `/api/di-regime` em tempo real
- Replay da mesma data abre/fecha trades coerentes com o painel do Miqueias
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Confirmar que bar_history tem >= 2240 bars de (win_price, di_price) não-nulos consecutivos
- [ ] #2 Re-rodar scripts/backfill_z_di.py em uma data DENTRO dessa janela completa e verificar que beta_di é negativo
- [ ] #3 Comparar z_di backfilled com /api/di-regime ao vivo na mesma data — divergência < 5%
- [ ] #4 Documentar em comentário no script (ou doc) qual foi o beta_di final e a janela de bars usada
- [ ] #5 Se valores ainda estiverem suspeitos, investigar se calc_beta_ols precisa de janela rolante diferente da REF_BARS
<!-- AC:END -->
