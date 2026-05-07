# SPEC — WIN×WDO Pair Trading System
## Technical Specification

**Versão**: 2.0  
**Data**: Abril 2026  

---

## 1. Arquitetura

```
┌──────────────────────────────────────────────────────────────┐
│  MetaTrader 5 Terminal (broker)                              │
│  ├─ WIN$N, WDO$N, DI1$N M5 bars (live)                       │
└──────────────────┬───────────────────────────────────────────┘
                   │ copy_rates_from_pos()
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Backend (Python 3.10+ · FastAPI · port 8080)                │
│                                                              │
│  server.py (thin controller)                                 │
│  ├─ GET /api/v2/regime   → Kalman WDO, DI, Johansen Cointeg  │
│  ├─ GET /api/performance → métricas de trades                │
│  └─ GET /health          → status MT5                        │
│                                                              │
│  firebase_push_loop()    → Syncs live state to Firebase RTDB │
│                                                              │
│  core/                                                       │
│  ├─ config.py           → parâmetros centralizados           │
│  ├─ signals.py          → calc_beta_ols, calc_zscore,        │
│  │                        get_signal, get_rho_status         │
│  ├─ mt5_client.py       → connect_mt5, fetch_bars,           │
│  │                        beta state machine                 │
│  ├─ kalman_filter.py    → KalmanBetaFilter (beta adaptativo) │
│  └─ trade_engine.py     → TradeEngine (Setup Matador)        │
│                                                              │
│  trades.db (SQLite)                                          │
└──────────────────┬───────────────────────────────────────────┘
                   │ HTTP JSON (polling 2.5s)
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Frontend (React · Vite · port 5174)                         │
│                                                              │
│  src/App.jsx                                                 │
│  src/components/                                             │
│  ├─ ZScoreChart.jsx          → Recharts AreaChart            │
│  ├─ IndexChart.jsx           → Price chart with NWE          │
│  ├─ SignalHistogram.jsx      → Histogram of signal consensus │
│  ├─ RegimeHealthPanel.jsx    → ρ correlação + Δβ gauges      │
│  ├─ PerformancePanel.jsx     → métricas + tabela de trades   │
│  ├─ SetupMatadorPanel.jsx    → cards BUY/SELL do engine      │
│  └─ TradingGuide.jsx         → regras de referência          │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Pipeline de Dados

### 2.1 Fluxo V5 (Kalman + Johansen) — `/api/v2/regime`

```
MT5 → N barras M5 (WIN, WDO, DI)
  ├─ KalmanBetaFilter.update() iterativo (WINxWDO) → k_z
  ├─ KalmanBetaFilter.update() iterativo (WINxDI) → di_z
  ├─ calc_nwe_with_bands(WIN) → NWE Bounds
  ├─ Johansen Cointegration Test (WINxWDO) → johansen_gate
  ├─ TradeEngine.evaluate(k_z, di_z, nwe, johansen_gate)
  └─ Response JSON com dual z-scores + history + health
```

### 2.2 Filtro de Kalman (Beta Adaptativo)

```python
# Modelo de estado:
#   beta[t] = beta[t-1] + noise     (random walk com Q=1e-5)
#   y[t] = beta[t] * x[t] + noise   (observação com R=1e-3)
#
# Atualização a cada barra:
#   predict → P_prior = P + Q
#   update  → K = P_prior * x / (x² * P_prior + R)
#             beta = beta + K * (y - x * beta)
#             P = (1 - K * x) * P_prior
```

### 2.3 Beta (legado: state machine V1, atualmente recomputado inline)

```
Antes (V1, removido):
  Hora em hora 09:30..17:30 → recalcula OLS, compara com anterior, salva em beta_ultimo.json às 17h.

Agora (V2):
  A cada poll → calc_beta_ols(window=WINDOW) inline a partir das barras correntes.
  beta_ultimo.json existe em disco mas não é mais lido nem escrito pelo runtime.
  Será removido (ou substituído por cache real) quando o slice de risk_gate landar.
```



## 3. Setup Matador — Parâmetros Validados

### 3.1 Entrada

| Condição | BUY (Compra WIN) | SELL (Vende WIN) |
|---|---|---|
| Z-Score WDO trigger | Kalman z ≤ -1.4 | Kalman z ≥ +1.2 |
| Z-Score DI trigger | Kalman z DI ≤ -1.4 | Kalman z DI ≥ +1.4 |
| NWE Bounds | WIN Close < Lower Band | N/A |
| Cointegração | Johansen Eigen Statistic > 90% | Johansen Eigen Statistic > 90% |
| Horário | 10:00 - 16:00 | 10:00 - 16:00 |

### 3.2 Saída

| Parâmetro | BUY | SELL |
|---|---|---|
| Take Profit | 500 pts | 1400 pts |
| Stop Loss | 350 pts | 300 pts |
| Break-Even ativação | 400 pts a favor | 800 pts a favor |
| Break-Even lock | 50 pts | 200 pts |
| Force close | 17:40 | 17:40 |

### 3.3 Sizing

- WIN: 2 contratos × R$0.20/pt = R$0.40/pt
- WDO: ignorado (opera apenas WIN no Setup Matador)

---

## 4. Schema do Banco de Dados

### 4.1 `matador_ops` (Trade Engine)

```sql
CREATE TABLE matador_ops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_in DATETIME,
    status TEXT,              -- 'OPEN' | 'CLOSED'
    direction TEXT,           -- 'BUY' | 'SELL'
    z_in REAL,
    z_source TEXT,            -- 'V2_KALMAN' | 'V1_OLS'
    rho_in REAL,
    beta_in REAL,
    qty_win INTEGER,
    price_win_in REAL,
    price_wdo_in REAL,
    timestamp_out DATETIME,
    exit_reason TEXT,         -- 'TARGET'|'STOP_LOSS'|'BE_STOP'|'FORCE_CLOSE'|'STOP_Z'
    price_win_out REAL,
    price_wdo_out REAL,
    pnl_brl REAL,
    max_pts_favor REAL DEFAULT 0.0,
    be_active INTEGER DEFAULT 0
);
```

### 4.2 `operations` (Legado V1)

```sql
-- Tabela legada mantida para compatibilidade com dashboard antigo
-- Novos trades usam exclusivamente matador_ops
```

---

## 5. Estrutura de Diretórios

```
wdo win pair trading/
├── core/                    # Motor de produção (6 módulos)
├── research/                # 21 scripts de backtest e otimização
├── data/
│   ├── historical/          # CSVs M1 WIN+WDO (2021-2026, ~93MB)
│   ├── heatmaps/            # PNGs de otimização
│   ├── reports/             # Relatórios de backtest
│   └── trades/              # CSVs de backtests
├── regime-dashboard/        # Frontend React/Vite
│   └── src/components/      # Componentes extraídos (7)
├── tests/                   # 24 testes unitários
├── .planning/               # Planejamento do agente
│   ├── docs/                # PRD, SPEC, Roadmap, Decisions
│   ├── codebase/            # Documentação estrutural
│   └── todos/               # Listas de tarefas
├── server.py                # Thin controller (~480 linhas)
├── ecosystem.config.js      # Configuração PM2 para processos
├── trades.db                # SQLite de operações
└── beta_ultimo.json         # Legado V1: arquivo presente em disco, não lido/escrito pelo runtime atual
```

---

## 6. Testes

| Suite | Count | Cobertura |
|---|---|---|
| `test_config.py` | 3 | Parâmetros Setup Matador, BE, sizing |
| `test_signals.py` | 10 | Beta OLS, half-life, rho/beta status, signals |
| `test_kalman_filter.py` | 1 | Convergência do filtro Kalman |
| `test_trade_engine.py` | 10 | Entry/exit logic, session, anomaly, BE, performance |
| **Total** | **24** | Engine + Signals + Config |

Execução: `python -m pytest tests/ -v`
