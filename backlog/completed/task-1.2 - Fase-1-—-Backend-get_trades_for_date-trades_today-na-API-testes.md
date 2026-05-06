---
id: TASK-1.2
title: 'Fase 1 — Backend: get_trades_for_date() + trades_today na API + testes'
status: Done
assignee: []
created_date: '2026-05-06 17:58'
updated_date: '2026-05-06 20:13'
labels:
  - backend
  - feature
  - test
milestone: Trades no Dashboard
dependencies:
  - TASK-1.1
references:
  - core/trade_engine.py
  - server.py
  - tests/test_trade_engine.py
parent_task_id: TASK-1
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Contexto

O frontend precisa de uma lista dos trades do dia atual para plotar marcadores nos gráficos. A fonte oficial é a tabela `matador_ops` no SQLite. O endpoint `/api/v2/regime` já é o ponto central de dados do dashboard — o campo `trades_today` deve ser adicionado à sua resposta.

**Não alterar `/api/performance`** — esse endpoint serve exclusivamente o `PerformancePanel` com estatísticas agregadas.

**Depende de TASK-1.1** (testes corrigidos e suite verde antes de adicionar código novo).

## Mudanças em core/trade_engine.py

Adicionar método público:

```python
def get_trades_for_date(self, date_str: str) -> list[dict]:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, strategy, direction, "
        "timestamp_in, "
        "strftime('%H:%M:%S', timestamp_in) as time_in, "
        "timestamp_out, "
        "strftime('%H:%M:%S', timestamp_out) as time_out, "
        "z_in, price_win_in, price_win_out, pnl_brl, exit_reason, status "
        "FROM matador_ops "
        "WHERE date(timestamp_in) = ? "
        "ORDER BY timestamp_in",
        (date_str,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

Campos retornados por trade:
```python
{
    "id": int,
    "strategy": str,           # "CONS_BASE" | "WDO_NWE" | "DI_NWE"
    "direction": str,          # "BUY" | "SELL"
    "timestamp_in": str,       # ISO "2026-05-06T10:05:12"
    "timestamp_out": str|None,
    "time_in": str,            # "10:05:12"
    "time_out": str|None,      # None se trade ainda OPEN
    "z_in": float,
    "price_win_in": float,
    "price_win_out": float|None,
    "pnl_brl": float|None,
    "exit_reason": str|None,
    "status": str              # "OPEN" | "CLOSED"
}
```

## Mudanças em server.py

**ATENÇÃO — nomes corretos do código real:**
- A instância do TradeEngine é `_trade_engine` (linha ~125 do server.py)
- O dict de resposta do endpoint é `res`, não `result` (linha ~785 do server.py)

Adicionar **após** a linha `res["nwe"] = {...}` e **antes** do `return res`:

```python
res["trades_today"] = _trade_engine.get_trades_for_date(
    datetime.now().strftime("%Y-%m-%d")
)
```

**Sem alterar o schema SQLite.**

## Testes em tests/test_trade_engine.py

Adicionar 4 testes (usando o mesmo padrão de fixture `engine(tmp_path)` já existente):

1. `test_get_trades_for_date_banco_vazio` — retorna lista vazia
2. `test_get_trades_for_date_retorna_open_e_closed` — ambos os status incluídos
3. `test_get_trades_for_date_filtra_outra_data` — trade de ontem não aparece
4. `test_get_trades_for_date_preserva_campos` — timestamps ISO, preços, status corretos
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 get_trades_for_date() retorna lista vazia para DB sem trades
- [ ] #2 get_trades_for_date() retorna trades OPEN e CLOSED da data solicitada
- [ ] #3 get_trades_for_date() NÃO retorna trades de outras datas
- [ ] #4 Campos time_in/time_out estão em HH:MM:SS; timestamp_in em ISO 8601 completo
- [ ] #5 price_win_out e pnl_brl são None para trades OPEN
- [ ] #6 GET /api/v2/regime inclui chave trades_today no JSON de resposta
- [ ] #7 trades_today é array vazio quando não há trades no dia
- [ ] #8 4 novos testes passando em pytest tests/test_trade_engine.py -v
<!-- AC:END -->
