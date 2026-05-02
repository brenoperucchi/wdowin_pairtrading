# core/hmm_background.py
"""
HMM regime detection background thread (M30 cycle).

Runs every 15 minutes, classifies WIN market into BULL/BEAR/CHOP
using a 3-state Gaussian HMM on trend-position, returns, volatility,
and ADX features.
"""
import time
import threading
import numpy as np
import pandas as pd
import MetaTrader5 as mt5
from hmmlearn.hmm import GaussianHMM
from ta.volatility import AverageTrueRange
from ta.trend import ADXIndicator, WMAIndicator
from core.config import MT5_PATH

# ─── Shared state — server reads this ───────────────────────────────────────
current_hmm_regime: str = "CALCULANDO"


def _rolling_zscore(s, w=50):
    mu = s.rolling(w).mean()
    sd = s.rolling(w).std() + 1e-6
    return (s - mu) / sd


def _run_loop():
    global current_hmm_regime
    while True:
        try:
            if mt5.terminal_info() is None:
                if MT5_PATH:
                    mt5.initialize(path=MT5_PATH)
                else:
                    mt5.initialize()

            rates = mt5.copy_rates_from_pos("WIN$N", mt5.TIMEFRAME_M30, 0, 1500)
            if rates is not None and len(rates) > 100:
                df = pd.DataFrame(rates)
                df["dt"] = pd.to_datetime(df["time"], unit="s")

                df["hlc3"] = (df["high"] + df["low"] + df["close"]) / 3
                wma_fast = WMAIndicator(close=df["hlc3"], window=20).wma()
                wma_slow = WMAIndicator(close=df["hlc3"], window=40).wma()
                df["basis"] = (wma_fast + wma_slow) / 2

                atr_20 = AverageTrueRange(
                    high=df["high"], low=df["low"], close=df["close"], window=20
                ).average_true_range()
                sm = WMAIndicator(close=atr_20.fillna(0), window=20).wma()
                df["upper"] = df["basis"] + sm
                df["lower"] = df["basis"] - sm

                trail_level = np.zeros(len(df))
                trend = 1
                tl = (
                    df["lower"].iloc[0]
                    if not pd.isna(df["lower"].iloc[0])
                    else df["close"].iloc[0]
                )

                closes = df["close"].values
                uppers = df["upper"].values
                lowers = df["lower"].values

                for i in range(1, len(df)):
                    c = closes[i]
                    u = uppers[i]
                    l = lowers[i]
                    if np.isnan(u) or np.isnan(l):
                        trail_level[i] = c
                        tl = c
                        continue
                    if trend == 1:
                        if c < tl:
                            trend = -1
                            tl = u
                        else:
                            tl = max(tl, l)
                    else:
                        if c > tl:
                            trend = 1
                            tl = l
                        else:
                            tl = min(tl, u)
                    trail_level[i] = tl

                df["trail_level"] = trail_level
                df["atr14"] = AverageTrueRange(
                    high=df["high"], low=df["low"], close=df["close"], window=14
                ).average_true_range()

                df["tpos_raw"] = (df["close"] - df["trail_level"]) / (
                    df["atr14"] + 1e-6
                )
                df["log_ret"] = np.log(
                    df["close"] / df["close"].shift(1)
                ).fillna(0)
                df["norm_vol"] = df["atr14"] / df["close"]
                df["adx"] = ADXIndicator(
                    high=df["high"], low=df["low"], close=df["close"], window=14
                ).adx()
                df.dropna(inplace=True)

                df["obs_tpos"] = _rolling_zscore(df["tpos_raw"])
                df["obs_ret"] = _rolling_zscore(df["log_ret"])
                df["obs_vol"] = _rolling_zscore(df["norm_vol"])
                df["obs_adx"] = _rolling_zscore(df["adx"])
                df.dropna(inplace=True)

                features = ["obs_tpos", "obs_ret", "obs_vol", "obs_adx"]
                X = df[features].values

                transmat_prior = np.ones((3, 3)) + np.eye(3) * 5.0
                model = GaussianHMM(
                    n_components=3,
                    covariance_type="full",
                    n_iter=200,
                    random_state=42,
                    transmat_prior=transmat_prior,
                )
                model.fit(X)

                hidden_states = model.predict(X)
                means = model.means_
                state_idx_bull = np.argmax(means[:, 0])
                state_idx_bear = np.argmin(means[:, 0])
                state_idx_chop = [
                    i
                    for i in range(3)
                    if i not in [state_idx_bull, state_idx_bear]
                ][0]

                state_map = {
                    state_idx_bull: "BULL",
                    state_idx_bear: "BEAR",
                    state_idx_chop: "CHOP",
                }
                current_hmm_regime = state_map[hidden_states[-1]]
                print(
                    f"[HMM IA] Novo ciclo M30 concluido — Estado Vigente: {current_hmm_regime}"
                )
        except Exception as e:
            print(f"[HMM ERROR] Falha no background thread: {e}")
        time.sleep(15 * 60)


def start():
    """Launch the HMM background thread. Call once at server startup."""
    threading.Thread(target=_run_loop, daemon=True).start()
