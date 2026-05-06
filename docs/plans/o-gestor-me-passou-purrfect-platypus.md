# Plano: Trades do Backtest/Setup no Dashboard

## Context

O gestor pediu para "equalizar o setup/backtest com histograma com trades mostrados no dashboard". Hoje, trades existem no SQLite (`matador_ops`) mas aparecem apenas na tabela do `PerformancePanel`. Os scripts de backtest mostram trades sobrepostos nos gráficos. O objetivo é plotar marcadores de entrada e saída no histograma de sinais, no gráfico de Z-score e no gráfico de preço — paridade visual com os backtests.

**Pré-requisito:** Os testes existentes em `tests/test_trade_engine.py` estão incompatíveis com a assinatura atual (`z_wdo`/`z_di` e retorno multi-strategy). Corrigi-los é o primeiro passo antes de qualquer nova funcionalidade.

---

## Fase 0 — Corrigir Testes Existentes da TradeEngine

**Arquivo:** `tests/test_trade_engine.py`
- Atualizar assinatura do `evaluate()` de `z` → `z_wdo`/`z_di`
- Atualizar asserts de retorno para estrutura multi-strategy atual
- Rodar `pytest tests/test_trade_engine.py -v` antes de avançar

---

## Fase 1 — Backend: `get_trades_for_date()` + `trades_today` na API

**Arquivo:** `core/trade_engine.py`
- Adicionar método `get_trades_for_date(date_str: str) -> list[dict]`
- Query: `WHERE date(timestamp_in) = ?`
- Inclui trades OPEN e CLOSED
- Campos retornados:

```python
{
    "id": int,
    "strategy": str,           # "CONS_BASE" | "WDO_NWE" | "DI_NWE"
    "direction": str,          # "BUY" | "SELL"
    "timestamp_in": str,       # ISO "2026-05-06T10:05:12"
    "timestamp_out": str|None, # ISO ou None se aberto
    "time_in": str,            # "10:05:12"
    "time_out": str|None,      # "10:22:44" ou None
    "z_in": float,
    "price_win_in": float,
    "price_win_out": float|None,
    "pnl_brl": float|None,
    "exit_reason": str|None,
    "status": str              # "OPEN" | "CLOSED"
}
```

**Arquivo:** `server.py`
- Após montar o resultado final do `/api/v2/regime`, adicionar:
  ```python
  result["trades_today"] = trade_engine.get_trades_for_date(
      datetime.now().strftime("%Y-%m-%d")
  )
  ```
- Sem alterar schema SQLite

---

## Fase 2 — Frontend: State + Helper de Alinhamento

**`App.jsx`**
- Adicionar `const [todayTrades, setTodayTrades] = useState([])`
- Preencher tanto no polling local quanto no fluxo Firebase: `setTodayTrades(data.trades_today ?? [])`
- Passar `todayTrades` para `SignalHistogram`, `ZScoreChart` e `IndexChart`

**Helper de alinhamento (inline em App.jsx ou arquivo utils):**
- Para cada trade, encontrar a barra M5 mais próxima (anterior) no array `history` usando `bar_time`
- `time_in` (HH:MM:SS) → truncar para HH:MM, buscar correspondência no `history[].bar_time`
- Se cair entre candles, usar a barra anterior disponível mais próxima

---

## Fase 3 — Frontend: Marcadores nos Gráficos

### `SignalHistogram.jsx` (prioridade 1 — pedido principal)
- Aceitar prop `trades`
- Renderizar marcadores na base de cada barra alinhada:
  - Entrada BUY: `▲` com cor da estratégia (CONS=`#00d4ff`, WDO=`#c8a444`, DI=`#8a6dff`)
  - Entrada SELL: `▼` invertido
  - Saída: quadrado `■` com cor da estratégia
- Tooltip no hover: estratégia, direção, Z de entrada, motivo de saída, PnL

### `ZScoreChart.jsx`
- Aceitar prop `trades`
- Entradas: `ReferenceDot` no ponto `(bar_time, z_in)` — círculo preenchido com cor da estratégia
- Saídas: `ReferenceDot` no `(bar_time_out, z_da_barra_alinhada)` — círculo vazio com stroke

### `IndexChart.jsx`
- Aceitar prop `trades`
- Entradas: `ReferenceDot` em `(bar_time, price_win_in)`
- Saídas: `ReferenceDot` em `(bar_time_out, price_win_out ?? win_price_da_barra_alinhada)`
- Mesma paleta de cores por estratégia

---

## Fase 4 — Testes

### `tests/test_trade_engine.py` — novos testes para `get_trades_for_date`:
```python
def test_get_trades_for_date_banco_vazio(tmp_path): ...
def test_get_trades_for_date_retorna_open_e_closed(tmp_path): ...
def test_get_trades_for_date_filtra_outra_data(tmp_path): ...
def test_get_trades_for_date_preserva_timestamps_e_precos(tmp_path): ...
```

### `tests/test_signals.py` — apenas se tocarmos `signals.py`:
- Adicionar `test_calc_zscore_*` somente se `calc_zscore` for modificado

---

## Arquivos Críticos

| Arquivo | Mudança |
|---------|---------|
| `tests/test_trade_engine.py` | Corrigir assinatura + 4 novos testes |
| `core/trade_engine.py` | + `get_trades_for_date()` |
| `server.py` | + campo `trades_today` na resposta de `/api/v2/regime` |
| `regime-dashboard/src/App.jsx` | + state `todayTrades`, helper de alinhamento, passa prop |
| `regime-dashboard/src/components/SignalHistogram.jsx` | + prop `trades`, marcadores |
| `regime-dashboard/src/components/ZScoreChart.jsx` | + prop `trades`, ReferenceDots |
| `regime-dashboard/src/components/IndexChart.jsx` | + prop `trades`, ReferenceDots |

---

## Decisões e Premissas

- **Marcadores históricos fora do dia atual:** fora da v1
- **Fonte oficial dos trades para plotagem:** `matador_ops` via `trades_today`; `/api/performance` continua exclusivo do `PerformancePanel`
- **Sem dependência nova:** usar Recharts (`ReferenceDot`, `ReferenceLine`) já instalado
- **Schema SQLite:** sem alterações

---

## Verificação

1. `pytest tests/ -v` — testes corrigidos + novos passam, nenhum quebrado
2. `uvicorn server:app --host 0.0.0.0 --port 8080 --reload`
3. `cd regime-dashboard && npm run dev`
4. `GET /api/v2/regime` inclui `trades_today` (array, pode estar vazio fora do pregão)
5. Dashboard `localhost:5174`:
   - Marcadores aparecem no histograma nas barras corretas
   - Dots de entrada visíveis no ZScoreChart na posição `z_in`
   - Marcadores de preço visíveis no IndexChart
   - Hover mostra tooltip com dados do trade
   - Trade aberto (sem `time_out`) mostra entrada sem saída
6. `npm run lint` e `npm run build` — zero erros
