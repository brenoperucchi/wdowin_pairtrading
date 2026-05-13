"""Runtime-tunable engine parameters with two profiles (live, replay).

Persisted to ``config/runtime.json``. Read by the live engine on each poll
(hot-reload) and by the replay script on startup. Defaults are returned
inline when the file is missing — we do not auto-create on first read so
fresh checkouts behave identically to old ones.

Risk-gate tunables (aligned with Miqueias upstream):
    eg_threshold (float)        Engle-Granger pvalue gate. Block when pvalue >= this.
    eg_bars (int)               Window size used to recompute EG pvalue.
    eg_recalc (str)             "bar" or "daily". When "daily" the pvalue
                                computed at the daily reference time is reused
                                for the rest of the session.
    rho_breakdown_level (int)   Block when rho_status['level'] >= this.
    beta_delta_max (float)      Block when |beta_delta_pct| >= this.
    eg_strategies (list[str])   Strategies that gate on EG; others bypass it.
    z_anomaly (float)           Block when max(|z_wdo|, |z_di|) >= this.

Engine tunables (operational params hot-reloadable, snapshot at trade open):
    window (int)                Rolling window used by signals/regime.
    z_entry (float)             Z-score entry threshold.
    entry_start_h/m (int)       Earliest entry timestamp HH:MM.
    entry_end_h/m (int)         Latest entry timestamp HH:MM.
    force_close_h/m (int)       Force-close timestamp HH:MM.
    buy_sl / buy_tp (int)       BUY stop-loss / take-profit in WIN points.
    buy_be_act / buy_be_lock    BUY breakeven activation / lock levels.
    sell_sl / sell_tp (int)     SELL stop-loss / take-profit.
    sell_be_act / sell_be_lock  SELL breakeven activation / lock levels.

Fidelity simulation sub-block (per profile, replay-only when enabled):
    simulation.{enabled,entry/exit_slippage_pts,cost_per_contract_rt_brl,
                intra_bar_sl_tp,exit_at_sl_tp_level,conflict_rule}

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
    # Risk-gate (Miqueias upstream)
    "eg_threshold",
    "eg_bars",
    "eg_recalc",
    "rho_breakdown_level",
    "beta_delta_max",
    "eg_strategies",
    "z_anomaly",
    # Signals / regime window
    "window",
    "z_entry",
    # Session hours
    "entry_start_h",
    "entry_start_m",
    "entry_end_h",
    "entry_end_m",
    "force_close_h",
    "force_close_m",
    # Per-side trade params (snapshot at _open_trade time)
    "buy_sl",
    "buy_tp",
    "buy_be_act",
    "buy_be_lock",
    "sell_sl",
    "sell_tp",
    "sell_be_act",
    "sell_be_lock",
    # Fidelity simulation sub-block
    "simulation",
)
EG_RECALC_VALUES = ("bar", "daily")
# Mirrors core.trade_engine.STRATEGIES. Duplicated here to avoid importing
# trade_engine at module load (it imports MetaTrader5 transitively).
VALID_STRATEGIES = ("CONS_BASE", "WDO_NWE", "DI_NWE")

# ── simulation sub-block ────────────────────────────────────────────────────
# Lives INSIDE each profile (live/replay) — not as a sibling — so existing
# strict per-profile validation stays sound. Default is "disabled" in BOTH
# profiles: enabling fidelity simulation is an explicit operator action, not
# something that flips on at deploy time.
SIMULATION_FIELDS = (
    "enabled",
    "entry_slippage_pts",
    "exit_slippage_pts",
    "cost_per_contract_rt_brl",
    "intra_bar_sl_tp",
    "exit_at_sl_tp_level",
    "conflict_rule",
)
CONFLICT_RULES = ("sl_first", "tp_first", "worst")
SIMULATION_DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "entry_slippage_pts": 5.0,
    "exit_slippage_pts": 5.0,
    "cost_per_contract_rt_brl": 1.0,
    "intra_bar_sl_tp": True,
    "exit_at_sl_tp_level": True,
    "conflict_rule": "sl_first",
}

# ─── Defaults ───────────────────────────────────────────────────────────────
# Runtime defaults aligned with Miqueias upstream (server.py:608 safe_to_trade):
#   eg_pvalue < 0.10, rho_status["level"] < 2 (rho <= -0.55),
#   |beta_delta_pct| < 15 (== get_beta_status level < 2 boundary).
# Live and replay share the same defaults — operator can still loosen per-profile
# via /CONFIG when investigating, but the unaltered defaults match upstream.
# Engine defaults mirror the legacy constants in core.config so this slice
# ships zero behavior delta — operators can still override per profile via
# /api/runtime-config. Values intentionally identical between live and
# replay until the operator decides to diverge.
_ENGINE_DEFAULTS: dict[str, Any] = {
    "window": 240,
    "z_entry": 1.4,
    "entry_start_h": 9,
    "entry_start_m": 0,
    "entry_end_h": 17,
    "entry_end_m": 25,
    "force_close_h": 17,
    "force_close_m": 40,
    "buy_sl": 300,
    "buy_tp": 800,
    "buy_be_act": 300,
    "buy_be_lock": 0,
    "sell_sl": 300,
    "sell_tp": 800,
    "sell_be_act": 300,
    "sell_be_lock": 0,
}

DEFAULTS: dict[str, dict[str, Any]] = {
    "live": {
        "eg_threshold": 0.10,
        "eg_bars": 2240,
        "eg_recalc": "daily",
        "rho_breakdown_level": 2,
        "beta_delta_max": 15.0,
        # Miqueias's WIN/WDO endpoint checks EG; DI endpoint does not
        # (server.py:608 vs :715 in /tmp/miqueias-wdowin/).
        "eg_strategies": ["CONS_BASE", "WDO_NWE"],
        "z_anomaly": 4.0,
        **copy.deepcopy(_ENGINE_DEFAULTS),
        "simulation": copy.deepcopy(SIMULATION_DEFAULTS),
    },
    "replay": {
        "eg_threshold": 0.10,
        "eg_bars": 2240,
        "eg_recalc": "daily",
        "rho_breakdown_level": 2,
        "beta_delta_max": 15.0,
        "eg_strategies": ["CONS_BASE", "WDO_NWE"],
        "z_anomaly": 4.0,
        **copy.deepcopy(_ENGINE_DEFAULTS),
        "simulation": copy.deepcopy(SIMULATION_DEFAULTS),
    },
}

_lock = threading.Lock()


def _validate_simulation(profile_name: str, payload: Any) -> dict[str, Any]:
    """Validate the ``simulation`` sub-block of a profile.

    Bounds reflect 'plausible MT5 behaviour' rather than absolute physical
    limits — they catch typos (e.g. 500-pt slippage) without painting the
    operator into a corner.
    """
    qualified = f"{profile_name}.simulation"
    if not isinstance(payload, dict):
        raise ValueError(f"{qualified} must be an object")

    extra = set(payload) - set(SIMULATION_FIELDS)
    if extra:
        raise ValueError(f"{qualified} has unknown fields: {sorted(extra)}")
    missing = set(SIMULATION_FIELDS) - set(payload)
    if missing:
        raise ValueError(f"{qualified} is missing fields: {sorted(missing)}")

    enabled = payload["enabled"]
    if not isinstance(enabled, bool):
        raise ValueError(f"{qualified}.enabled must be a bool")

    def _num(field: str, lo: float, hi: float) -> float:
        v = payload[field]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(f"{qualified}.{field} must be a number")
        v = float(v)
        if not (lo <= v <= hi):
            raise ValueError(f"{qualified}.{field} must be in [{lo}, {hi}]")
        return v

    entry_slip = _num("entry_slippage_pts", 0.0, 50.0)
    exit_slip = _num("exit_slippage_pts", 0.0, 50.0)
    cost_rt = _num("cost_per_contract_rt_brl", 0.0, 50.0)

    intra_bar = payload["intra_bar_sl_tp"]
    if not isinstance(intra_bar, bool):
        raise ValueError(f"{qualified}.intra_bar_sl_tp must be a bool")

    exit_at_level = payload["exit_at_sl_tp_level"]
    if not isinstance(exit_at_level, bool):
        raise ValueError(f"{qualified}.exit_at_sl_tp_level must be a bool")

    conflict_rule = payload["conflict_rule"]
    if conflict_rule not in CONFLICT_RULES:
        raise ValueError(
            f"{qualified}.conflict_rule must be one of {list(CONFLICT_RULES)}"
        )

    return {
        "enabled": enabled,
        "entry_slippage_pts": entry_slip,
        "exit_slippage_pts": exit_slip,
        "cost_per_contract_rt_brl": cost_rt,
        "intra_bar_sl_tp": intra_bar,
        "exit_at_sl_tp_level": exit_at_level,
        "conflict_rule": conflict_rule,
    }


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

    eg_strategies = payload["eg_strategies"]
    if not isinstance(eg_strategies, list):
        raise ValueError(f"{name}.eg_strategies must be a list")
    seen: set[str] = set()
    normalised_strats: list[str] = []
    for item in eg_strategies:
        if not isinstance(item, str):
            raise ValueError(
                f"{name}.eg_strategies entries must be strings"
            )
        if item not in VALID_STRATEGIES:
            raise ValueError(
                f"{name}.eg_strategies has unknown strategy {item!r}; "
                f"expected subset of {list(VALID_STRATEGIES)}"
            )
        if item in seen:
            raise ValueError(
                f"{name}.eg_strategies has duplicate {item!r}"
            )
        seen.add(item)
        normalised_strats.append(item)

    z_anomaly = payload["z_anomaly"]
    if not isinstance(z_anomaly, (int, float)) or isinstance(z_anomaly, bool):
        raise ValueError(f"{name}.z_anomaly must be a number")
    z_anomaly = float(z_anomaly)
    if not (0.0 < z_anomaly <= 10.0):
        raise ValueError(f"{name}.z_anomaly must be in (0, 10]")

    def _int_in(field: str, lo: int, hi: int) -> int:
        v = payload[field]
        if not isinstance(v, int) or isinstance(v, bool):
            raise ValueError(f"{name}.{field} must be an integer")
        if not (lo <= v <= hi):
            raise ValueError(f"{name}.{field} must be in [{lo}, {hi}]")
        return v

    window = _int_in("window", 30, 1000)

    z_entry = payload["z_entry"]
    if not isinstance(z_entry, (int, float)) or isinstance(z_entry, bool):
        raise ValueError(f"{name}.z_entry must be a number")
    z_entry = float(z_entry)
    if not (0.1 < z_entry <= 5.0):
        raise ValueError(f"{name}.z_entry must be in (0.1, 5.0]")

    entry_start_h = _int_in("entry_start_h", 0, 23)
    entry_start_m = _int_in("entry_start_m", 0, 59)
    entry_end_h = _int_in("entry_end_h", 0, 23)
    entry_end_m = _int_in("entry_end_m", 0, 59)
    force_close_h = _int_in("force_close_h", 0, 23)
    force_close_m = _int_in("force_close_m", 0, 59)

    buy_sl = _int_in("buy_sl", 10, 5000)
    buy_tp = _int_in("buy_tp", 10, 5000)
    buy_be_act = _int_in("buy_be_act", 0, 5000)
    buy_be_lock = _int_in("buy_be_lock", 0, 5000)
    sell_sl = _int_in("sell_sl", 10, 5000)
    sell_tp = _int_in("sell_tp", 10, 5000)
    sell_be_act = _int_in("sell_be_act", 0, 5000)
    sell_be_lock = _int_in("sell_be_lock", 0, 5000)

    # ── Cross-field validation ──────────────────────────────────────────────
    # Hours must be ordered: entry_start < entry_end <= force_close.
    # Equal start/end leaves the entry window empty (almost certainly a typo);
    # entry_end == force_close is fine (entries close exactly when force-close
    # fires).
    start_min = entry_start_h * 60 + entry_start_m
    end_min = entry_end_h * 60 + entry_end_m
    fc_min = force_close_h * 60 + force_close_m
    if start_min >= end_min:
        raise ValueError(
            f"{name}.entry_start ({entry_start_h:02d}:{entry_start_m:02d}) must be "
            f"earlier than entry_end ({entry_end_h:02d}:{entry_end_m:02d})"
        )
    if end_min > fc_min:
        raise ValueError(
            f"{name}.entry_end ({entry_end_h:02d}:{entry_end_m:02d}) must be at or before "
            f"force_close ({force_close_h:02d}:{force_close_m:02d})"
        )

    # BE / TP semantics per side:
    #   be_lock <= be_act  — can't lock more than you've earned at activation
    #   be_lock <  tp      — equal makes the lock identical to the target
    #   be_act  <= tp      — BE should activate at or before the target
    def _check_be_tp(side: str, tp: int, be_act: int, be_lock: int) -> None:
        if be_lock > be_act:
            raise ValueError(
                f"{name}.{side}_be_lock ({be_lock}) must be <= {side}_be_act ({be_act})"
            )
        if be_lock >= tp:
            raise ValueError(
                f"{name}.{side}_be_lock ({be_lock}) must be < {side}_tp ({tp})"
            )
        if be_act > tp:
            raise ValueError(
                f"{name}.{side}_be_act ({be_act}) must be <= {side}_tp ({tp})"
            )

    _check_be_tp("buy", buy_tp, buy_be_act, buy_be_lock)
    _check_be_tp("sell", sell_tp, sell_be_act, sell_be_lock)

    simulation = _validate_simulation(name, payload["simulation"])

    return {
        "eg_threshold": eg_threshold,
        "eg_bars": eg_bars,
        "eg_recalc": eg_recalc,
        "rho_breakdown_level": rho_level,
        "beta_delta_max": beta_delta,
        "eg_strategies": normalised_strats,
        "z_anomaly": z_anomaly,
        "window": window,
        "z_entry": z_entry,
        "entry_start_h": entry_start_h,
        "entry_start_m": entry_start_m,
        "entry_end_h": entry_end_h,
        "entry_end_m": entry_end_m,
        "force_close_h": force_close_h,
        "force_close_m": force_close_m,
        "buy_sl": buy_sl,
        "buy_tp": buy_tp,
        "buy_be_act": buy_be_act,
        "buy_be_lock": buy_be_lock,
        "sell_sl": sell_sl,
        "sell_tp": sell_tp,
        "sell_be_act": sell_be_act,
        "sell_be_lock": sell_be_lock,
        "simulation": simulation,
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


def validate_runtime_config(payload: Any) -> dict[str, dict[str, Any]]:
    """Public validation helper for callers that need normalisation only."""
    return _validate(payload)


def _backfill_missing_fields(raw: Any) -> Any:
    """Add any missing FIELDS to each profile from DEFAULTS before validation.

    Forward-compat shim for on-disk configs written before a new field was
    introduced (for example, older configs may predate ``eg_strategies`` or
    the ``simulation`` sub-block). Keeps ``save_runtime_config`` strict —
    only the read path is lenient.

    For nested ``simulation``, fields are merged at the sub-key level so a
    partial block on disk gets its missing keys filled (preserves operator
    intent for the fields they did set).
    """
    if not isinstance(raw, dict):
        return raw
    patched = dict(raw)
    for profile in PROFILES:
        section = patched.get(profile)
        if not isinstance(section, dict):
            continue
        merged = dict(section)
        defaults_for_profile = DEFAULTS.get(profile, {})
        for field in FIELDS:
            if field not in merged and field in defaults_for_profile:
                merged[field] = copy.deepcopy(defaults_for_profile[field])
        sim_block = merged.get("simulation")
        if isinstance(sim_block, dict):
            sim_merged = dict(sim_block)
            for sim_field in SIMULATION_FIELDS:
                if sim_field not in sim_merged:
                    sim_merged[sim_field] = copy.deepcopy(
                        SIMULATION_DEFAULTS[sim_field]
                    )
            merged["simulation"] = sim_merged
        patched[profile] = merged
    return patched


def load_runtime_config(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Return the persisted config, or DEFAULTS when the file is missing.

    A file with malformed JSON or invalid values raises ValueError so the
    operator notices instead of silently falling back to defaults. Missing
    fields (from older slices) are backfilled from DEFAULTS so a stale
    on-disk file doesn't 500 the GET endpoint or break the live fallback.
    """
    target = Path(path) if path is not None else CONFIG_PATH
    with _lock:
        if not target.exists():
            return copy.deepcopy(DEFAULTS)
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"runtime config at {target} is not valid JSON: {exc}")
        return _validate(_backfill_missing_fields(raw))


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
