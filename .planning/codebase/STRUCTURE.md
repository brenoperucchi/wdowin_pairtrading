# Project Structure

wdo win pair trading/
│
├── ecosystem.config.js                # PM2 process manager config for backend/frontend
│
├── server.py                          # FastAPI app — thin controller (~500 lines)
│                                      #   GET /api/v2/regime (V5 Kalman + Johansen)
│                                      #   GET /api/performance
│                                      #   firebase_push_loop() (RTDB Sync)
│
├── core/                              # Production runtime modules
│   ├── __init__.py                    # Package init
│   ├── config.py                      # All trading parameters (63 lines)
│   │                                  #   Symbols, timeframes, SL/TP/BE, session hours
│   ├── mt5_client.py                  # MT5 connection & data fetching (76 lines)
│   │                                  #   connect_mt5(), fetch_bars(), beta persistence
│   ├── signals.py                     # Pure computation functions (147 lines)
│   │                                  #   calc_beta_ols(), calc_zscore(), get_signal()
│   │                                  #   get_rho_status(), get_beta_status()
│   ├── kalman_filter.py               # Kalman beta/spread filter (68 lines)
│   │                                  #   KalmanBetaFilter class + rolling_zscore()
│   └── trade_engine.py               # Trade lifecycle manager (265 lines)
│                                      #   TradeEngine class: evaluate(), SL/TP/BE logic
│
├── research/                          # Offline research & ML pipeline
│   ├── models/                        # ML directional models
│   │   ├── __init__.py
│   │   ├── features.py                # Shared feature engineering (210 lines)
│   │   │                              #   compute_features(), make_target()
│   │   │                              #   17+ features: local, macro, spread
│   │   ├── hmm_direction.py           # HMM directional model (111 lines)
│   │   │                              #   3-state, maps regime → BUY/SELL/FLAT
│   │   ├── lstm_direction.py          # LSTM directional model (210 lines)
│   │   │                              #   Sequence-to-class, PyTorch, early stopping
│   │   └── xgb_direction.py           # XGBoost directional model (124 lines)
│   │                                  #   Tabular classifier with feature importance
│   │
│   ├── data_prep.py                   # Resample M1→M30, merge VIX/DXY
│   ├── wfa_runner.py                  # Walk-Forward Analysis orchestrator (236 lines)
│   │                                  #   12-month train / 3-month test / 3-month step
│   ├── backtest.py                    # Original pair trading backtest
│   ├── backtest_ml_zscore.py          # Combined ML+ZScore backtest
│   ├── backtest_pa.py                 # Price action backtest variant
│   ├── backtest_win.py                # WIN-only backtest
│   ├── compare_models.py             # Model comparison report + plots
│   ├── equity_curve.py               # Equity curve visualizer
│   ├── equity_split.py               # BUY/SELL equity split analysis
│   ├── tune_all_models.py            # Grid search (1800 configs, parallel)
│   ├── tune_lstm.py                   # LSTM hyperparameter tuning
│   ├── tune_lstm_v2.py               # LSTM v2 tuning (optimized)
│   ├── tune_single.py                # Single-model tuner utility
│   ├── hmm_strategy_filter.py        # HMM as strategy filter analysis
│   ├── hmm_win_classifier.py         # HMM WIN classifier
│   ├── hmm_zscore_optimizer.py       # HMM + z-score combined optimizer
│   ├── optimize_*.py                  # Various parameter optimizers (6 files)
│   ├── plot_*.py                      # Various plotting scripts (5 files)
│   ├── updater.py                     # Data update utility
│   └── _*.py                          # Internal helper scripts (6 files)
│
├── regime-dashboard/                  # React frontend (Vite)
│   ├── package.json                   # React 19, Recharts 3.8, Vite 8
│   ├── vite.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.jsx                   # React entry point
│   │   ├── App.jsx                    # Main application (~464 lines)
│   │   │                              #   Firebase RTDB connection, state, signal routing
│   │   ├── App.css                    # Global styles (dark financial theme)
│   │   ├── index.css                  # Base CSS
│   │   └── components/
│   │       ├── SetupMatadorPanel.jsx  # Trade engine status display
│   │       ├── ZScoreChart.jsx        # Area chart (dual z-scores)
│   │       ├── IndexChart.jsx         # Price chart with Nadaraya-Watson Envelope (NWE)
│   │       ├── SignalHistogram.jsx    # Signal strength visualizer
│   │       ├── RegimeHealthPanel.jsx  # ρ + β health indicators
│   │       ├── PerformancePanel.jsx   # Win rate, PnL, trade table
│   │       └── TradingGuide.jsx       # Trading rules reference
│   ├── dist/                          # Production build output
│   └── public/                        # Static assets
│
├── data/                              # All data files
│   ├── historical/                    # Raw M1 CSVs from MT5 (~400MB)
│   │   ├── WIN$N_M1_*.csv
│   │   ├── WDO$N_M1_*.csv
│   │   ├── VIX_M1_*.csv
│   │   ├── DXY_M1_*.csv
│   │   ├── XAUUSD_M1_*.csv
│   │   └── XTIUSD_M1_*.csv
│   ├── processed/                     # ML-ready datasets
│   │   ├── dataset_m30.parquet        # Unified M30 dataset (~1MB)
│   │   ├── dataset_m5_backtest.parquet # M5 backtest dataset (~6MB)
│   │   └── wfa_results/              # WFA OOS predictions by model
│   ├── trades/                        # Backtest trade logs (CSV)
│   ├── reports/                       # Analysis reports + plots (16 files)
│   └── heatmaps/                      # Parameter optimization heatmaps (7 PNG)
│
├── tests/                             # Unit tests (pytest)
│   ├── test_config.py                 # Config validation tests
│   ├── test_kalman_filter.py          # Kalman filter tests
│   ├── test_signals.py                # Signal computation tests
│   └── test_trade_engine.py           # Trade engine tests
│
├── .planning/
│   ├── docs/                          # Project documentation
│   │   ├── PRD.md                     # Product Requirements Document
│   │   ├── SPEC.md                    # System and frontend specifications
│   │   ├── SPEC_ML_DIRECTION.md       # ML direction models spec
│   │   ├── DECISIONS.md               # Decision log (D001-D008)
│   │   └── ROADMAP.md                 # Development roadmap
│   ├── codebase/                      # Agentic codebase documentation
│   └── todos/                         # Workflow tasks
│
├── trades.db                          # SQLite database (production trades)
├── beta_ultimo.json                   # Last known beta value
├── README.md                          # Project documentation
└── .gitignore
```

## Key File Sizes & Complexity

| File | Lines | Role | Complexity |
|---|---|---|---|
| `server.py` | 500 | Thin API controller | Medium — orchestrates core modules + Firebase RTDB sync |
| `core/trade_engine.py` | 330 | Trade lifecycle | Medium — state machine with SL/TP/BE + DI rules |
| `core/signals.py` | 147 | Pure math | Low — stateless functions |
| `research/models/features.py` | 210 | Feature engineering | High — 17+ features with technical indicators |
| `research/models/lstm_direction.py` | 210 | LSTM model | High — PyTorch training loop |
| `research/wfa_runner.py` | 236 | WFA orchestrator | Medium — manages train/test windows |
| `research/tune_all_models.py` | 23665 | Grid search | Very High — parallel processing, 1800 configs |
| `regime-dashboard/src/App.jsx` | 531 | Dashboard UI | High — polling, state, memory leak protections, audio alerts |
| `regime-dashboard/src/components/IndexChart.jsx` | 200 | Charting | Medium — Recharts with NWE calculations |

## Module Coupling

```
server.py → core/config.py (parameters)
          → core/mt5_client.py (data)
          → core/signals.py (computation)
          → core/kalman_filter.py (V2 estimation)
          → core/trade_engine.py (trade management)

research/wfa_runner.py → research/models/features.py
                       → research/models/hmm_direction.py
                       → research/models/lstm_direction.py
                       → research/models/xgb_direction.py

App.jsx → SetupMatadorPanel, ZScoreChart, IndexChart, SignalHistogram, 
          RegimeHealthPanel, PerformancePanel, TradingGuide (components)
```
