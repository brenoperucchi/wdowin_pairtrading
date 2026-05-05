# Directory Structure

```
wdo win pair trading/
├── core/                       # Lógica de negócio e cálculos quantitativos
│   ├── config.py               # Constantes (Kalman, Johansen, NWE, Portas)
│   ├── hmm_background.py       # Thread M30 p/ Regimes de Mercado (HMM)
│   ├── kalman_filter.py        # Classe KalmanBetaFilter 
│   ├── mt5_client.py           # Conexão com IPC da B3/MT5
│   ├── signals.py              # Cálculos matemáticos core (Z-Score, Beta OLS, NWE)
│   └── trade_engine.py         # Avaliação de sinal multi-strat e DB Logging
├── regime-dashboard/           # Aplicação Frontend UI (React)
│   └── src/
│       ├── components/         # Módulos gráficos (ZScoreChart, IndexChart, Panels)
│       ├── App.jsx             # Loop React de consumo do Firebase
│       └── firebase.js         # Cliente Web Firebase
├── data/                       # Arquivos de backtest e históricos exportados
├── server.py                   # Entrypoint FastAPI e loop do Firebase Sync
└── trades.db                   # SQLite armazenando as operações (Paper Trading)
```
