# core/config.py
"""
WIN×WDO Setup Matador v4 — Centralized Configuration
==================================================
All trading parameters validated in backtest (2021-2026, 100k bars OOS).
WDO: Kalman Filter (KQ=1e-4, KR=1e2, KW=40) + NWE contra-trend
DI:  Kalman Filter (KQ=1e-3, KR=1e1, KW=60) + NWE contra-trend
CONS: z-scores WDO+DI alinhados (SEM filtro NWE)

Infrastructure constants (ports, paths, timeframes) merged from server.py.
"""
import MetaTrader5 as mt5

# ─── Infrastructure ─────────────────────────────────────────────────────────
# NOTE: "MetaTrader 5 Terminal" path causes IPC timeout due to Windows Service
# conflict (RegimeSupervisor holds PID in Session 0). Use "MetaTrader 5" (XP Demo)
# which has all B3 symbols (WIN$N, WDO$N, DI1$N) and runs in user Session 1.
MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"

# ─── Symbols ────────────────────────────────────────────────────────────────
SYMBOL_A = "WIN$N"
SYMBOL_B = "WDO$N"

# ─── Timeframe & Windows ────────────────────────────────────────────────────
TIMEFRAME = mt5.TIMEFRAME_M5
WINDOW = 90
BARS = 250
KALMAN_BURN_IN = 2000
BETA_INITIAL = -22.5

# ─── WDO Pair Trading (WIN×WDO) — Kalman Filter ─────────────────────────────
WDO_KALMAN_Q = 1e-4             # Kalman trans_cov
WDO_KALMAN_R = 1e2              # Kalman obs_cov
WDO_KALMAN_W = 40               # Z-score rolling window
BETA_REF_BARS = 2240
BETA_REF_5D_BARS = 560
BETA_ALERT_PCT = 10.0
BETA_REF_WINDOW = 80
BETA_DELTA_MAX = 25.0
RHO_MIN = -0.40

# ─── Setup Matador: Entry ────────────────────────────────────────────────────
Z_ENTRY = 1.4          # Entry threshold
Z_ANOMALY = 4.0        # Anomaly threshold — don't trade
Z_ATTENTION = 1.2      # Attention zone display only

# ─── Setup Matador: BUY (V2 Kalman) ─────────────────────────────────────────
BUY_SL = 300           # Stop loss in WIN points
BUY_TP = 800           # Take profit in WIN points
BUY_BE_ACT = 300       # Breakeven activation (pts in favor)
BUY_BE_LOCK = 0        # Breakeven lock level (pts)

# ─── Setup Matador: SELL (V1 OLS) ───────────────────────────────────────────
SELL_SL = 300
SELL_TP = 800
SELL_BE_ACT = 300
SELL_BE_LOCK = 0

# ─── Sizing ─────────────────────────────────────────────────────────────────
WIN_CONTRACTS = 2
WIN_PV = 0.20          # R$/point/contract

# ─── Session ────────────────────────────────────────────────────────────────
ENTRY_START_H = 9
ENTRY_START_M = 0
ENTRY_END_H = 15
ENTRY_END_M = 0
FORCE_CLOSE_H = 17
FORCE_CLOSE_M = 40

# ─── Server ─────────────────────────────────────────────────────────────────
CACHE_TTL = 2.0
TIME_OFFSET = 3 * 3600

# ─── DI Pair Trading (WIN×DI) — Kalman Filter ───────────────────────────────
DI_SYMBOL = "DI1$N"            # Contrato contínuo DI futuro
DI_KALMAN_Q = 1e-3             # Kalman trans_cov (adaptação rápida)
DI_KALMAN_R = 1e1              # Kalman obs_cov (baixa suavização)
DI_KALMAN_W = 60               # Z-score rolling window
DI_BETA_INITIAL = -10000.0     # Beta inicial WIN/DI (escala: WIN~135k, DI~13.5)
DI_BARS = 250                  # Barras para buscar do MT5
DI_BETA_REF_BARS = 2240        # Barras para beta referência 20d
DI_Z_ENTRY = 1.4               # Threshold de entrada
DI_Z_ANOMALY = 4.0             # Threshold de anomalia
DI_Z_ATTENTION = 1.2           # Zona de atenção

# ─── Johansen Gate (cointegration validation only) ──────────────────────────
JOH_WINDOW = 150               # Rolling window para teste de Johansen
JOH_RECHECK_BARS = 12          # Recalcular a cada N barras (~1h em M5)
JOH_BETA_TOLERANCE = 0.30      # Tolerância beta consistency (30%)

# ─── NWE (Nadaraya-Watson Envelope) — Validated OOS 2022-2026 ───────────────
NWE_BANDWIDTH = 8              # Kernel bandwidth
NWE_LOOKBACK = 95              # Lookback window (bars)
NWE_BAND_MULT = 0.10           # Adaptive band multiplier (fraction of band width)
NWE_MULT_MAE = 3.0             # MAE multiplier for bands

