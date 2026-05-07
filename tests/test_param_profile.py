"""TASK-3 AC #5 — manifest smoke test + parse-and-compare.

`docs/PARAM_PROFILE.md` documents every canonical live constant. This
test asserts:
  1. The doc exists with the required sections (smoke test).
  2. The shape/type of each canonical constant in `core/config.py`
     matches the manifest (rename / type-change guard).
  3. **Every value pinned in Section 1 of the doc equals
     `getattr(cfg, NAME)`.** This is the sync guard added in codex
     round-6: previously the doc could drift silently from
     `core/config.py` because the test only checked shapes.

Section-1 tables in the manifest are written in a parser-friendly
format — one constant per row — so this test can reconstruct the
expected mapping with a single regex pass.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core import config as cfg


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = REPO_ROOT / "docs" / "PARAM_PROFILE.md"


# Names that MUST appear in the manifest's Section 1. If any are missing
# from the parsed table, the manifest is incomplete and the test fails.
REQUIRED_IN_MANIFEST = [
    # Bar / data window — backtest must match live or it isn't comparing
    # the same signal.
    "TIMEFRAME", "WINDOW", "BARS", "DI_BARS",
    # Kalman tuning (WDO + DI run independent filters)
    "WDO_KALMAN_Q", "WDO_KALMAN_R", "WDO_KALMAN_W",
    "DI_KALMAN_Q", "DI_KALMAN_R", "DI_KALMAN_W",
    # Johansen test
    "JOH_WINDOW", "JOH_RECHECK_BARS",
    # Entry / signal
    "Z_ENTRY", "Z_ANOMALY", "Z_ATTENTION",
    "DI_Z_ENTRY", "DI_Z_ANOMALY", "DI_Z_ATTENTION",
    # SL / TP / BE
    "BUY_SL", "BUY_TP", "BUY_BE_ACT", "BUY_BE_LOCK",
    "SELL_SL", "SELL_TP", "SELL_BE_ACT", "SELL_BE_LOCK",
    # Sizing
    "WIN_CONTRACTS", "WIN_PV",
    # Execution costs (validation backtest)
    "WIN_SLIPPAGE_PTS", "B3_COST_PER_CONTRACT_RT",
    # Regime
    "BETA_INITIAL", "RHO_MIN", "BETA_DELTA_MAX", "KALMAN_BURN_IN",
    # Session
    "ENTRY_START_H", "ENTRY_START_M",
    "ENTRY_END_H", "ENTRY_END_M",
    "FORCE_CLOSE_H", "FORCE_CLOSE_M",
    # Operational risk
    "MAX_TRADES_PER_DAY", "DAILY_LOSS_LIMIT_BRL",
    "LOSS_COOLDOWN_MIN", "BLOCK_ON_MT5_DISCONNECT",
    # NWE
    "NWE_BANDWIDTH", "NWE_LOOKBACK", "NWE_BAND_MULT", "NWE_MULT_MAE",
    # Symbols
    "SYMBOL_A", "SYMBOL_B", "DI_SYMBOL",
]


# ── Parser ──────────────────────────────────────────────────────────────────

# Match table rows of the form: | `NAME` | value | optional notes |
# The doc wraps constant names in backticks. We only parse rows whose first
# cell is a backticked identifier — narrative tables (script status, etc.)
# don't match this shape.
_ROW_RE = re.compile(
    r"^\|\s*`([A-Z][A-Z0-9_]*)`\s*\|\s*([^|]+?)\s*\|",
    re.MULTILINE,
)


def _coerce(raw: str):
    """Parse a markdown cell into a Python value.

    Order matters: bool before int (since `True`/`False` aren't ints in
    Python's `isinstance` sense for our asserts), then int before float
    (we want exact int equality for hour/minute fields).
    """
    s = raw.strip().strip("`")
    if s in ("True", "False"):
        return s == "True"
    # Strip thousands separators just in case (none today, future-proofing).
    s_clean = s.replace(",", "")
    try:
        return int(s_clean)
    except ValueError:
        pass
    try:
        return float(s_clean)
    except ValueError:
        pass
    # Fall through: treat as a string (e.g. "WIN$N").
    return s


def _parse_canonical(text: str) -> dict[str, object]:
    """Extract the {NAME: value} map from Section 1 of the manifest.

    Section 1 ends where Section 2 begins (`## 2.`). We restrict the
    regex search to the slice before that header so script-status tables
    can never bleed into the canonical map.
    """
    end = text.find("\n## 2.")
    if end == -1:
        raise AssertionError("Section 2 marker missing — manifest malformed")
    section1 = text[:end]
    out: dict[str, object] = {}
    for m in _ROW_RE.finditer(section1):
        name, raw_val = m.group(1), m.group(2)
        out[name] = _coerce(raw_val)
    return out


@pytest.fixture(scope="module")
def manifest_values() -> dict[str, object]:
    assert DOC_PATH.exists(), f"Manifest missing: {DOC_PATH}"
    return _parse_canonical(DOC_PATH.read_text(encoding="utf-8"))


# ── Smoke / structure tests ─────────────────────────────────────────────────

def test_param_profile_doc_exists():
    """The manifest doc must be present in the repo with required sections."""
    assert DOC_PATH.exists(), f"Manifest missing: {DOC_PATH}"
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "Canonical live profile" in text
    assert "Research script status" in text
    assert "core/config.py" in text


def test_all_required_constants_in_manifest(manifest_values):
    """Every constant on the required list must appear in Section 1."""
    missing = [n for n in REQUIRED_IN_MANIFEST if n not in manifest_values]
    assert not missing, (
        f"Manifest Section 1 is missing constants: {missing}. "
        "Add a row to docs/PARAM_PROFILE.md or remove from REQUIRED_IN_MANIFEST."
    )


def test_canonical_values_match_config(manifest_values):
    """**Sync guard.** Each pinned value in Section 1 must equal cfg.NAME.

    If `core/config.py` changes a value, this test fails with a clear
    diff and forces a manifest update — closing the silent-drift hole
    flagged by codex round-6.
    """
    mismatches: list[str] = []
    for name, doc_val in manifest_values.items():
        if not hasattr(cfg, name):
            mismatches.append(f"{name}: manifest pins {doc_val!r} but cfg has no such attribute")
            continue
        cfg_val = getattr(cfg, name)
        # Compare with type tolerance: int 0 vs float 0.0 in the doc is fine
        # so long as the numeric value matches. Booleans and strings must
        # match exactly. We never want int/bool conflation, though, since
        # bool is a subclass of int in Python.
        if isinstance(cfg_val, bool) or isinstance(doc_val, bool):
            ok = cfg_val == doc_val and isinstance(cfg_val, bool) == isinstance(doc_val, bool)
        elif isinstance(cfg_val, (int, float)) and isinstance(doc_val, (int, float)):
            ok = float(cfg_val) == float(doc_val)
        else:
            ok = cfg_val == doc_val
        if not ok:
            mismatches.append(
                f"{name}: manifest={doc_val!r} ({type(doc_val).__name__}), "
                f"config={cfg_val!r} ({type(cfg_val).__name__})"
            )
    assert not mismatches, (
        "docs/PARAM_PROFILE.md is out of sync with core/config.py:\n  "
        + "\n  ".join(mismatches)
    )


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
