# SPEC — WIN×WDO Pair Trading System
## Technical Specification

**Versão**: 2.0  
**Data**: Abril 2026  

---

## 1. Arquitetura

```
┌──────────────────────────────────────────────────────────────┐
│  MetaTrader 5 Terminal (broker)                              │
│  ├─ WIN$N M5 bars (live)                                     │
│  └─ WIN$N M30 bars (HMM thread)                             │
└──────────────────┬───────────────────────────────────────────┘
                   │ copy_rates_from_pos()
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Backend (Python 3.10+ · FastAPI · port 8080)                │
│                                                              │
│  server.py (thin controller)                                 │
│  ├─ GET /api/v2/regime   → Kalman + OLS dual z-score         │
│  ├─ GET /api/regime      → V1 OLS (legado)                   │
│  ├─ GET /api/performance → métricas de trades                │
│  └─ GET /health          → status MT5                        │
│                                                              │
│  core/                                                       │
│  ├─ config.py           → parâmetros centralizados           │
│  ├─ signals.py          → calc_beta_ols, calc_zscore,        │
│  │                        get_signal, get_rho_status         │
│  ├─ mt5_client.py       → connect_mt5, fetch_bars,           │
│  │                        beta state machine                 │
│  ├─ kalman_filter.py    → KalmanBetaFilter (beta adaptativo) │
│  ├─ trade_engine.py     → TradeEngine (Setup Matador)        │
│  └─ hmm_background.py  → thread HMM M30 (15 min cycle)      │
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

### 2.1 Fluxo V2 (Kalman) — `/api/v2/regime`

```
MT5 → 250 barras M5 (WIN+WDO)
  ├─ KalmanBetaFilter.update() iterativo → spreads[] + betas[]
  ├─ rolling_zscore(spreads, w=40) → z_kalman (BUY decisions)
  ├─ calc_zscore(closes_a, closes_b, beta_ols) → z_ols (SELL decisions)
  ├─ TradeEngine.evaluate(z_buy=z_kalman, z_sell=z_ols)
  └─ Response JSON com dual z-scores + history
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

### 2.3 Beta State Machine

```
Hora em hora (09:30, 10:30, ..., 17:30):
  ├─ Recalcula beta OLS (janela completa)
  ├─ Compara com leitura anterior → instável se Δ > 15%
  ├─ Salva em beta_ultimo.json às 17h
  └─ Teste de cointegração Engle-Granger (1x por cálculo)
```

### 2.4 HMM Background Thread

```
A cada 15 minutos:
  ├─ Puxa 1500 barras M30 do WIN$N
  ├─ Calcula features: trend_position, log_returns, norm_vol, ADX
  ├─ Z-score normaliza features (rolling w=50)
  ├─ Treina GaussianHMM(n_components=3, cov=full)
  ├─ Classifica por média de trend_position:
  │   ├─ BULL → max(means[:, 0])   → bloqueia entradas
  │   ├─ BEAR → min(means[:, 0])   → opera normalmente
  │   └─ CHOP → restante           → opera normalmente
  └─ Publica current_hmm_regime (global thread-safe)
```

---

## 3. Setup Matador — Parâmetros Validados

### 3.1 Entrada

| Condição | BUY (Compra WIN) | SELL (Vende WIN) |
|---|---|---|
| Z-Score trigger | Kalman z ≤ -1.8 | OLS z ≥ +1.8 |
| Fonte do z-score | V2 Kalman | V1 OLS |
| Correlação mínima | ρ ≤ -0.40 | ρ ≤ -0.40 |
| Beta estável | Δβ(20d) < 15% | Δβ(20d) < 15% |
| HMM regime | ≠ BULL | ≠ BULL |
| Cointegração | EG p-value < 0.10 | EG p-value < 0.10 |
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
    exit_reason TEXT,         -- 'TARGET'|'STOP_LOSS'|'BE_STOP'|'FORCE_CLOSE'|'STOP_Z'|'STOP_RHO'
    price_win_out REAL,
    price_wdo_out REAL,
    pnl_brl REAL,
    max_pts_favor REAL DEFAULT 0.0,
    be_active INTEGER DEFAULT 0,
    hmm_state TEXT
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
└── beta_ultimo.json         # Beta persistido do dia anterior
```

---

## 6. Testes

| Suite | Count | Cobertura |
|---|---|---|
| `test_config.py` | 3 | Parâmetros Setup Matador, BE, sizing |
| `test_signals.py` | 10 | Beta OLS, half-life, rho/beta status, signals, HMM block |
| `test_kalman_filter.py` | 1 | Convergência do filtro Kalman |
| `test_trade_engine.py` | 10 | Entry/exit logic, session, anomaly, BE, performance |
| **Total** | **24** | Engine + Signals + Config |

Execução: `python -m pytest tests/ -v`
