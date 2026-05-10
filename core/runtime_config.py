"""Runtime-tunable risk-gate parameters with two profiles (live, replay).

Persisted to ``config/runtime.json``. Read by the live engine on each poll
(hot-reload) and by the replay script on startup. Defaults are returned
inline when the file is missing — we do not auto-create on first read so
fresh checkouts behave identically to old ones.

Five tunables per profile:
    eg_threshold (float)        Engle-Granger pvalue gate. Block when pvalue >= this.
    eg_bars (int)               Window size used to recompute EG pvalue.
    eg_recalc (str)             "bar" or "daily". When "daily" the pvalue
                                computed at the daily reference time is reused
                                for the rest of the session.
    rho_breakdown_level (int)   Block when rho_status['level'] >= this.
    beta_delta_max (float)      Block when |beta_delta_pct| >= this.

Validation is strict (raises ValueError) so the API endpoint can return a
meaningful 400 without partially writing the file.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

# ─── Locations ──────────────────────────────────────────────────────────────
# Resolve ``config/runtime.json`` relative to the repo root (parent of ``core``).
_REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = _REPO_ROOT / "config" / "runtime.json"

PROFILES = ("live", "replay")
FIELDS = (
    "eg_threshold",
    "eg_bars",
    "eg_recalc",
    "rho_breakdown_level",
    "beta_delta_max",
)
EG_RECALC_VALUES = ("bar", "daily")

# ─── Defaults ───────────────────────────────────────────────────────────────
# live mirrors current production constants (risk_gate.EG_PVALUE_THRESHOLD,
# core.config.BARS, BETA_DELTA_MAX, RHO_BREAKDOWN_LEVEL).
# replay starts wider than live (500 bars / daily recalc) while remaining
# cheap enough for interactive replay runs.
DEFAULTS: dict[str, dict[str, Any]] = {
    "live": {
        "eg_threshold": 0.10,
        "eg_bars": 250,
        "eg_recalc": "bar",
        "rho_breakdown_level": 2,
        "beta_delta_max": 25.0,
    },
    "replay": {
        "eg_threshold": 0.10,
        "eg_bars": 500,
        "eg_recalc": "daily",
        "rho_breakdown_level": 2,
        "beta_delta_max": 25.0,
    },
}

_lock = threading.Lock()


def _validate_profile(name: str, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"profile '{name}' must be an object")

    extra = set(payload) - set(FIELDS)
    if extra:
        raise ValueError(
            f"profile '{name}' has unknown fields: {sorted(extra)}"
        )
    missing = set(FIELDS) - set(payload)
    if missing:
        raise ValueError(
            f"profile '{name}' is missing fields: {sorted(missing)}"
        )

    eg_threshold = payload["eg_threshold"]
    if not isinstance(eg_threshold, (int, float)) or isinstance(eg_threshold, bool):
        raise ValueError(f"{name}.eg_threshold must be a number")
    eg_threshold = float(eg_threshold)
    if not (0.0 < eg_threshold <= 1.0):
        raise ValueError(f"{name}.eg_threshold must be in (0, 1]")

    eg_bars = payload["eg_bars"]
    if not isinstance(eg_bars, int) or isinstance(eg_bars, bool):
        raise ValueError(f"{name}.eg_bars must be an integer")
    if eg_bars < 60:
        raise ValueError(f"{name}.eg_bars must be >= 60")
    if eg_bars > 100_000:
        raise ValueError(f"{name}.eg_bars must be <= 100000")

    eg_recalc = payload["eg_recalc"]
    if eg_recalc not in EG_RECALC_VALUES:
        raise ValueError(
            f"{name}.eg_recalc must be one of {list(EG_RECALC_VALUES)}"
        )

    rho_level = payload["rho_breakdown_level"]
    if not isinstance(rho_level, int) or isinstance(rho_level, bool):
        raise ValueError(f"{name}.rho_breakdown_level must be an integer")
    if not (1 <= rho_level <= 3):
        raise ValueError(f"{name}.rho_breakdown_level must be in [1, 3]")

    beta_delta = payload["beta_delta_max"]
    if not isinstance(beta_delta, (int, float)) or isinstance(beta_delta, bool):
        raise ValueError(f"{name}.beta_delta_max must be a number")
    beta_delta = float(beta_delta)
    if not (0.0 < beta_delta <= 100.0):
        raise ValueError(f"{name}.beta_delta_max must be in (0, 100]")

    return {
        "eg_threshold": eg_threshold,
        "eg_bars": eg_bars,
        "eg_recalc": eg_recalc,
        "rho_breakdown_level": rho_level,
        "beta_delta_max": beta_delta,
    }


def _validate(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    extra = set(payload) - set(PROFILES)
    if extra:
        raise ValueError(f"unknown profiles: {sorted(extra)}")
    missing = set(PROFILES) - set(payload)
    if missing:
        raise ValueError(f"missing profiles: {sorted(missing)}")
    return {name: _validate_profile(name, payload[name]) for name in PROFILES}


def load_runtime_config(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Return the persisted config, or DEFAULTS when the file is missing.

    A file with malformed JSON or invalid values raises ValueError so the
    operator notices instead of silently falling back to defaults.
    """
    target = Path(path) if path is not None else CONFIG_PATH
    with _lock:
        if not target.exists():
            return copy.deepcopy(DEFAULTS)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"runtime config at {target} is not valid JSON: {exc}")
        return _validate(raw)


def save_runtime_config(
    payload: dict[str, Any], path: Path | str | None = None
) -> dict[str, dict[str, Any]]:
    """Validate and atomically persist the config. Returns the normalised value."""
    target = Path(path) if path is not None else CONFIG_PATH
    normalised = _validate(payload)
    with _lock:
        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: create tmp in the same directory then os.replace.
        fd, tmp_name = tempfile.mkstemp(
            prefix=".runtime.", suffix=".json", dir=str(target.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(normalised, fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(tmp_name, target)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    return normalised


def get_profile(name: str, path: Path | str | None = None) -> dict[str, Any]:
    """Convenience accessor — load_runtime_config()[name] with validation."""
    if name not in PROFILES:
        raise ValueError(f"unknown profile {name!r}; expected one of {list(PROFILES)}")
    return load_runtime_config(path)[name]
