"""TASK-3 AC #5 — manifest smoke test.

`docs/PARAM_PROFILE.md` documents every canonical live constant. This
test asserts that those names still exist in `core/config.py` with the
expected type and a sane range, so a rename, deletion, or type change
fails CI before the manifest silently drifts.

The test is intentionally narrow: it does NOT pin exact values (live
calibration changes — the manifest doc tracks current values). It pins
*shapes*. A shape mismatch means the manifest needs an update.
"""
from pathlib import Path

import pytest

from core import config as cfg


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_param_profile_doc_exists():
    """The manifest doc must be present in the repo."""
    doc = REPO_ROOT / "docs" / "PARAM_PROFILE.md"
    assert doc.exists(), f"Manifest missing: {doc}"
    text = doc.read_text(encoding="utf-8")
    # Spot-check that the three required sections are present.
    assert "Canonical live profile" in text
    assert "Research script status" in text
    assert "core/config.py" in text


# ── Entry / signal thresholds ───────────────────────────────────────────────

def test_z_thresholds_ordered_and_positive():
    assert isinstance(cfg.Z_ENTRY, (int, float))
    assert isinstance(cfg.Z_ANOMALY, (int, float))
    assert isinstance(cfg.Z_ATTENTION, (int, float))
    # Strict ordering — anomaly must be the largest, attention the smallest.
    # If this changes, signal logic in core/signals.py has to be reviewed.
    assert 0 < cfg.Z_ATTENTION < cfg.Z_ENTRY < cfg.Z_ANOMALY


def test_di_z_thresholds_present_and_ordered():
    assert 0 < cfg.DI_Z_ATTENTION < cfg.DI_Z_ENTRY < cfg.DI_Z_ANOMALY


# ── SL / TP / BE ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", [
    "BUY_SL", "BUY_TP", "BUY_BE_ACT", "BUY_BE_LOCK",
    "SELL_SL", "SELL_TP", "SELL_BE_ACT", "SELL_BE_LOCK",
])
def test_sl_tp_be_constants_present_and_int_like(name):
    val = getattr(cfg, name)
    assert isinstance(val, (int, float)), f"{name} must be numeric"
    assert val >= 0, f"{name} must be non-negative"


def test_sl_tp_relationship():
    """TP must exceed SL on both sides — otherwise expectancy is upside-down."""
    assert cfg.BUY_TP > cfg.BUY_SL
    assert cfg.SELL_TP > cfg.SELL_SL


# ── Sizing ──────────────────────────────────────────────────────────────────

def test_sizing_constants():
    assert isinstance(cfg.WIN_CONTRACTS, int) and cfg.WIN_CONTRACTS > 0
    assert isinstance(cfg.WIN_PV, (int, float)) and cfg.WIN_PV > 0


# ── Regime / hedge ratio ────────────────────────────────────────────────────

def test_regime_constants():
    assert isinstance(cfg.BETA_INITIAL, (int, float))
    assert isinstance(cfg.RHO_MIN, (int, float))
    # rho is a correlation; valid range [-1, 1].
    assert -1.0 <= cfg.RHO_MIN <= 1.0
    assert isinstance(cfg.BETA_DELTA_MAX, (int, float))
    assert cfg.BETA_DELTA_MAX > 0
    assert isinstance(cfg.KALMAN_BURN_IN, int) and cfg.KALMAN_BURN_IN > 0


# ── Session ─────────────────────────────────────────────────────────────────

def test_session_hours_in_valid_range():
    for h_name in ("ENTRY_START_H", "ENTRY_END_H", "FORCE_CLOSE_H"):
        h = getattr(cfg, h_name)
        assert isinstance(h, int) and 0 <= h <= 23, f"{h_name} out of range"
    for m_name in ("ENTRY_START_M", "ENTRY_END_M", "FORCE_CLOSE_M"):
        m = getattr(cfg, m_name)
        assert isinstance(m, int) and 0 <= m <= 59, f"{m_name} out of range"


def test_session_window_ordered():
    """Entry start < Entry end < Force close."""
    start = cfg.ENTRY_START_H * 60 + cfg.ENTRY_START_M
    end = cfg.ENTRY_END_H * 60 + cfg.ENTRY_END_M
    fc = cfg.FORCE_CLOSE_H * 60 + cfg.FORCE_CLOSE_M
    assert start < end < fc


# ── Operational risk (TASK-3 AC #11) ────────────────────────────────────────

def test_operational_risk_constants():
    assert isinstance(cfg.MAX_TRADES_PER_DAY, int) and cfg.MAX_TRADES_PER_DAY > 0
    assert isinstance(cfg.DAILY_LOSS_LIMIT_BRL, (int, float)) and cfg.DAILY_LOSS_LIMIT_BRL > 0
    assert isinstance(cfg.LOSS_COOLDOWN_MIN, (int, float)) and cfg.LOSS_COOLDOWN_MIN > 0
    assert isinstance(cfg.BLOCK_ON_MT5_DISCONNECT, bool)


# ── NWE filter ──────────────────────────────────────────────────────────────

def test_nwe_constants_present():
    assert isinstance(cfg.NWE_BANDWIDTH, (int, float)) and cfg.NWE_BANDWIDTH > 0
    assert isinstance(cfg.NWE_LOOKBACK, int) and cfg.NWE_LOOKBACK > 0
    assert isinstance(cfg.NWE_BAND_MULT, (int, float)) and 0 < cfg.NWE_BAND_MULT <= 1.0
    assert isinstance(cfg.NWE_MULT_MAE, (int, float)) and cfg.NWE_MULT_MAE > 0


# ── Symbols & infra ─────────────────────────────────────────────────────────

def test_symbol_constants():
    assert cfg.SYMBOL_A == "WIN$N"
    assert cfg.SYMBOL_B == "WDO$N"
    assert cfg.DI_SYMBOL == "DI1$N"
    # Sanity: no full-size DOL contract sneaking in (research/README.md
    # documents that DOL ≡ WDO in this codebase).
    assert "DOL$" not in cfg.SYMBOL_B
