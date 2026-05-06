---
id: TASK-1.1
title: Fase 0 — Corrigir suite de testes da TradeEngine (assinatura z_wdo/z_di)
status: Done
assignee: []
created_date: '2026-05-06 17:57'
updated_date: '2026-05-06 20:13'
labels:
  - test
  - bug
  - backend
milestone: Trades no Dashboard
dependencies: []
references:
  - tests/test_trade_engine.py
  - core/trade_engine.py
  - core/config.py
parent_task_id: TASK-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

Os testes em `tests/test_trade_engine.py` foram escritos para uma versão anterior do `TradeEngine`. A assinatura atual do método `evaluate()` mudou de `z_buy`/`z_sell` para `z_wdo`/`z_di`, e o retorno passou a ser multi-strategy (dict com chave `strategies`). Os testes atuais falham ou testam comportamentos que não existem mais da forma descrita.

Esta task é **pré-requisito** de todas as demais do milestone — precisamos ter uma suite verde antes de adicionar código novo.

## O que verificar

Ler `core/trade_engine.py` para entender a assinatura atual de `evaluate()`:

```python
def evaluate(self, z_wdo: float, z_di: float,
             win_price: float, wdo_price: float,
             rho: float, beta_safe: bool, hmm_state: str,
             hour: int, minute: int,
             beta_value: float = 0.0,
             nwe_is_up: bool = True,
             nwe_upper: float = 0.0,
             nwe_lower: float = 0.0,
             bar_close_confirmed: bool = True) -> dict
```

O retorno é `_build_portfolio_result()`:
```python
{
    "action": str,        # ação dominante
    "holding": bool,
    "exit_reason": str|None,
    "pnl": float|None,
    "strategies": {
        "CONS_BASE": {"action", "open_trade", "exit_reason", "pnl"},
        "WDO_NWE":   {...},
        "DI_NWE":    {...},
    }
}
```

## O que mudar nos testes

- Renomear `z_buy` → `z_wdo` e `z_sell` → `z_di` em todas as chamadas a `evaluate()`
- Atualizar asserts de `result["open_trade"]` → `result["strategies"]["CONS_BASE"]["open_trade"]`
- `test_hmm_bull_blocks_entry`: HMM BULL não existe mais como gate global na engine — verificar se foi removido e ajustar o teste conforme o comportamento atual
- `test_outside_session_no_entry`: session start é `ENTRY_START_H:ENTRY_START_M` (ver `core/config.py`), não necessariamente 10:00 — corrigir o horário do teste
- Manter a cobertura existente de SL, TP, BE e performance report
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pytest tests/test_trade_engine.py -v retorna 0 falhas
- [ ] #2 Todas as chamadas a evaluate() usam z_wdo/z_di (nenhum z_buy/z_sell restante)
- [ ] #3 Asserts de open_trade acessam result["strategies"][strategy]["open_trade"]
- [ ] #4 Cobertura de SL, TP, BE e performance_report mantida (nenhum teste removido sem substituto)
- [ ] #5 pytest tests/ -v (suite completa) continua verde
<!-- AC:END -->
