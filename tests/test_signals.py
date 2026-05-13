# tests/test_signals.py
"""Tests for core.signals — pure computation functions."""
import numpy as np
from core.signals import (
    calc_beta_ols, calc_half_life, calc_zscore,
    get_signal, get_rho_status, get_beta_status
)


def test_calc_beta_ols_returns_float():
    a = np.array([100.0, 101.0, 102.0, 103.0, 104.0])
    b = np.array([50.0, 50.5, 51.0, 51.5, 52.0])
    beta = calc_beta_ols(a, b)
    assert isinstance(beta, float)


def test_calc_beta_ols_positive_correlation():
    np.random.seed(42)
    b = np.cumsum(np.random.randn(100)) + 100
    a = 2.0 * b + np.random.randn(100) * 0.1
    beta = calc_beta_ols(a, b)
    assert 1.9 < beta < 2.1


def test_calc_half_life_mean_reverting():
    np.random.seed(42)
    spread = np.zeros(200)
    for i in range(1, 200):
        spread[i] = 0.8 * spread[i-1] + np.random.randn()
    hl = calc_half_life(spread)
    assert 0 < hl < 50  # Should be finite for mean-reverting


def test_calc_half_life_short_series():
    assert calc_half_life(np.array([1.0, 2.0])) == 0.0


def test_get_rho_status_levels():
    assert get_rho_status(-0.80)["level"] == 0  # FORTE
    assert get_rho_status(-0.60)["level"] == 1  # ATENÇÃO
    assert get_rho_status(-0.45)["level"] == 2  # FRACA
    assert get_rho_status(-0.20)["level"] == 3  # QUEBRADA


def test_get_beta_status_levels():
    assert get_beta_status(3.0)["level"] == 0   # ESTÁVEL
    assert get_beta_status(10.0)["level"] == 1  # DERIVANDO
    assert get_beta_status(20.0)["level"] == 2  # INSTÁVEL
    assert get_beta_status(30.0)["level"] == 3  # BREAKDOWN


def test_get_signal_anomaly():
    sig = get_signal(4.5)
    assert sig["id"] == "anomalia"


def test_get_signal_neutral():
    sig = get_signal(0.3)
    assert sig["id"] == "neutro"


def test_get_signal_attention_zone():
    sig = get_signal(1.2)
    assert sig["id"] == "atencao"


def test_get_signal_hmm_bull_no_block():
    """HMM BULL is no longer a block gate in get_signal() — signal passes through."""
    sig = get_signal(2.0, hmm_state="BULL")
    assert sig["id"] != "bloqueioHMM"
    assert sig["id"] in ("compraWdo", "compraWin", "vendeWdo", "vendeWin", "atencao", "anomalia", "neutro")


# ─── TASK-16.2: profile-injected thresholds ─────────────────────────────────


def test_get_signal_z_entry_kwarg_lowers_entry_threshold():
    """z_entry=1.0 promotes z=1.3 from attention → entry."""
    sig_default = get_signal(1.3)            # 1.3 < default Z_ENTRY=1.4 but >= Z_ATTENTION=1.2 → atencao
    sig_lowered = get_signal(1.3, z_entry=1.0, z_attention=0.5)
    assert sig_default["id"] == "atencao"
    assert sig_lowered["id"] == "compraWdo"  # z > z_entry on the long-spread side


def test_get_signal_z_entry_kwarg_raises_entry_threshold():
    """z_entry=2.0 demotes z=1.6 from entry → attention."""
    sig_default = get_signal(1.6)            # 1.6 > default Z_ENTRY=1.4 → compraWdo
    sig_raised = get_signal(1.6, z_entry=2.0, z_attention=1.0)
    assert sig_default["id"] == "compraWdo"
    assert sig_raised["id"] == "atencao"


def test_get_signal_z_attention_kwarg_shrinks_attention_band():
    """z_attention=0.5 promotes z=0.6 from neutro → atencao."""
    sig_default = get_signal(0.6)
    sig_tight = get_signal(0.6, z_attention=0.5)
    assert sig_default["id"] == "neutro"
    assert sig_tight["id"] == "atencao"


def test_get_signal_none_kwargs_fall_back_to_globals():
    """Both kwargs as None must reproduce the legacy module-global behaviour."""
    bare = get_signal(1.3)
    forwarded = get_signal(1.3, z_entry=None, z_attention=None)
    assert bare["id"] == forwarded["id"]
