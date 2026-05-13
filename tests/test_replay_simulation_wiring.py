"""Tests for Slice A.7 — replay wires simulation_profile + OHLC into engine.

Covers TASK-17.7 acceptance criteria:
  1. CLI flags --sim-* override runtime_config
  2. win_high/win_low are read from bar_history and forwarded to engine.evaluate
  3. META event payload carries the simulation_profile actually used
  4. Bar without OHLC + sim_intra_bar still runs (engine handles graceful fallback)
  5. Replay with sim disabled produces same trade-relevant summary as pre-A.7
"""
from __future__ import annotations

import json
import os
import sqlite3
import time

import pytest

import scripts.replay_execution_timeline as replay
from core import runtime_config
from core.config import BUY_TP
from core.trade_engine import TradeEngine
from server import init_bar_history, save_bar_history


REPLAY_DATE = "2026-05-12"


def _ts_for(bar_time: str, date_str: str = REPLAY_DATE) -> int:
    return int(time.mktime(time.strptime(f"{date_str} {bar_time}", "%Y-%m-%d %H:%M")))


def _seed_bar(
    db_path: str,
    *,
    bar_time: str,
    ts: int,
    date_str: str = REPLAY_DATE,
    win_price: float = 130000.0,
    wdo_price: float = 5500.0,
    di_price: float = 12.5,
    z_wdo: float = 0.4,
    z_di: float = -0.6,
    eg_pvalue: float = 0.04,
    rho: float = -0.85,
    rho_level: int = 0,
    beta_value: float = 23.5,
    beta_delta_pct: float = 2.0,
    win_open: float | None = None,
    win_high: float | None = None,
    win_low: float | None = None,
) -> None:
    save_bar_history(
        timestamp=ts,
        date_str=date_str,
        bar_time=bar_time,
        win_price=win_price,
        wdo_price=wdo_price,
        di_price=di_price,
        spread_wdo=42.0,
        spread_di=-3.1,
        z_wdo=z_wdo,
        z_di=z_di,
        nwe_center=130100.0,
        nwe_upper=130250.0,
        nwe_lower=129950.0,
        nwe_is_up=True,
        eg_pvalue=eg_pvalue,
        rho=rho,
        rho_level=rho_level,
        beta_value=beta_value,
        beta_delta_pct=beta_delta_pct,
        win_open=win_open,
        win_high=win_high,
        win_low=win_low,
        db_path=db_path,
    )


@pytest.fixture
def source_db(tmp_path):
    p = tmp_path / "source.db"
    init_bar_history(str(p))
    return str(p)


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "replays"
    d.mkdir()
    return str(d)


@pytest.fixture
def persisted_eg(monkeypatch):
    monkeypatch.setattr(
        replay.ReplayEgComputer,
        "pvalue_for",
        lambda _self, row: row.get("eg_pvalue"),
    )


# ─── AC #1 — CLI flags override runtime_config ──────────────────────────────

def test_cli_sim_flags_parse_all_seven():
    args = replay._parse_args(
        [
            "--date", REPLAY_DATE,
            "--sim-enabled",
            "--sim-entry-slip", "7.5",
            "--sim-exit-slip", "8.0",
            "--sim-cost-rt", "2.25",
            "--sim-intra-bar",
            "--sim-exit-at-level",
            "--sim-conflict-rule", "tp_first",
        ]
    )

    assert args.sim_enabled is True
    assert args.sim_entry_slip == 7.5
    assert args.sim_exit_slip == 8.0
    assert args.sim_cost_rt == 2.25
    assert args.sim_intra_bar is True
    assert args.sim_exit_at_level is True
    assert args.sim_conflict_rule == "tp_first"


def test_cli_no_sim_flags_negate_booleans():
    args = replay._parse_args(
        [
            "--date", REPLAY_DATE,
            "--no-sim-enabled",
            "--no-sim-intra-bar",
            "--no-sim-exit-at-level",
        ]
    )

    assert args.sim_enabled is False
    assert args.sim_intra_bar is False
    assert args.sim_exit_at_level is False


def test_cli_sim_flags_default_to_none_when_unset():
    args = replay._parse_args(["--date", REPLAY_DATE])

    assert args.sim_enabled is None
    assert args.sim_entry_slip is None
    assert args.sim_exit_slip is None
    assert args.sim_cost_rt is None
    assert args.sim_intra_bar is None
    assert args.sim_exit_at_level is None
    assert args.sim_conflict_rule is None


def test_resolve_replay_profile_applies_simulation_overrides():
    profile = replay.resolve_replay_profile(
        simulation_overrides={
            "enabled": True,
            "entry_slippage_pts": 10.0,
            "conflict_rule": "tp_first",
        },
    )

    assert profile.simulation["enabled"] is True
    assert profile.simulation["entry_slippage_pts"] == 10.0
    assert profile.simulation["conflict_rule"] == "tp_first"
    # Untouched keys retain runtime_config defaults
    assert profile.simulation["exit_slippage_pts"] == runtime_config.SIMULATION_DEFAULTS["exit_slippage_pts"]


def test_resolve_replay_profile_simulation_overrides_skips_none_values():
    profile = replay.resolve_replay_profile(
        simulation_overrides={
            "enabled": True,
            "entry_slippage_pts": None,
            "exit_slippage_pts": None,
        },
    )

    assert profile.simulation["enabled"] is True
    # None values must NOT clobber the configured defaults
    assert profile.simulation["entry_slippage_pts"] == runtime_config.SIMULATION_DEFAULTS["entry_slippage_pts"]
    assert profile.simulation["exit_slippage_pts"] == runtime_config.SIMULATION_DEFAULTS["exit_slippage_pts"]


def test_main_forwards_simulation_overrides_to_run_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("BAR_HISTORY_BACKEND", "postgres")  # bypass source-file check
    captured: dict = {}

    def fake_run_replay(
        *,
        date_str,
        source_db,
        out_dir,
        config_path,
        overrides,
        simulation_overrides,
    ):
        captured["simulation_overrides"] = simulation_overrides
        captured["overrides"] = overrides
        return {"replay_date": date_str, "bars_total": 0, "bars_processed": 0}

    monkeypatch.setattr(replay, "run_replay", fake_run_replay)

    rc = replay.main(
        [
            "--date", REPLAY_DATE,
            "--out", str(tmp_path / "out"),
            "--sim-enabled",
            "--sim-entry-slip", "7.5",
            "--sim-conflict-rule", "worst",
        ]
    )

    assert rc == 0
    sim = captured["simulation_overrides"]
    assert sim["enabled"] is True
    assert sim["entry_slippage_pts"] == 7.5
    assert sim["conflict_rule"] == "worst"
    # Untouched flags pass through as None (resolver skips them)
    assert sim["exit_slippage_pts"] is None
    assert sim["intra_bar_sl_tp"] is None


# ─── AC #2 — OHLC read from bar_history and forwarded to engine ─────────────

def test_replay_forwards_win_high_low_to_engine(source_db, out_dir, persisted_eg, monkeypatch):
    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        win_open=129995.0,
        win_high=130120.0,
        win_low=129880.0,
    )
    captured_kwargs: list[dict] = []
    real_evaluate = TradeEngine.evaluate

    def spy_evaluate(self, *args, **kwargs):
        captured_kwargs.append(dict(kwargs))
        return real_evaluate(self, *args, **kwargs)

    monkeypatch.setattr(TradeEngine, "evaluate", spy_evaluate)
    replay.run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)

    assert captured_kwargs, "engine.evaluate was never called"
    last = captured_kwargs[-1]
    assert last["win_high"] == 130120.0
    assert last["win_low"] == 129880.0
    assert last["simulation_profile"] is not None
    assert "enabled" in last["simulation_profile"]


def test_replay_forwards_none_when_bar_lacks_ohlc(source_db, out_dir, persisted_eg, monkeypatch):
    _seed_bar(source_db, bar_time="10:00", ts=_ts_for("10:00"))  # no OHLC
    captured_kwargs: list[dict] = []
    real_evaluate = TradeEngine.evaluate

    def spy_evaluate(self, *args, **kwargs):
        captured_kwargs.append(dict(kwargs))
        return real_evaluate(self, *args, **kwargs)

    monkeypatch.setattr(TradeEngine, "evaluate", spy_evaluate)
    replay.run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=out_dir)

    assert captured_kwargs
    last = captured_kwargs[-1]
    assert last["win_high"] is None
    assert last["win_low"] is None


# ─── AC #3 — META event payload carries simulation_profile ──────────────────

def test_meta_event_payload_includes_simulation_profile(source_db, out_dir, persisted_eg):
    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        win_high=130120.0,
        win_low=129880.0,
    )
    summary = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides={
            "enabled": True,
            "entry_slippage_pts": 6.0,
            "conflict_rule": "tp_first",
        },
    )

    runtime_profile = summary["runtime_profile"]
    assert "simulation" in runtime_profile
    sim = runtime_profile["simulation"]
    assert sim["enabled"] is True
    assert sim["entry_slippage_pts"] == 6.0
    assert sim["conflict_rule"] == "tp_first"

    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")
    conn = sqlite3.connect(replay_db)
    row = conn.execute(
        "SELECT payload_json FROM execution_timeline WHERE event = 'REPLAY_SUMMARY'"
    ).fetchone()
    conn.close()
    assert row is not None
    payload = json.loads(row[0])
    assert payload["runtime_profile"]["simulation"]["enabled"] is True
    assert payload["runtime_profile"]["simulation"]["entry_slippage_pts"] == 6.0


# ─── AC #4 — sim intra-bar enabled but bar lacks OHLC → graceful fallback ───

def test_replay_intra_bar_enabled_without_ohlc_does_not_crash(source_db, out_dir, persisted_eg):
    """Legacy bars (no OHLC) under sim+intra_bar must process without crashing.

    The engine falls back to close-only exit checks when H/L are absent. We
    verify (a) the loop completes, (b) the trade opens against close prices,
    (c) no DATA-phase MISSING_OHLC event is emitted because OHLC is optional,
    and (d) a DATA warning records that intra-bar fidelity degraded.
    """
    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        z_wdo=-2.1,
        z_di=-1.5,
    )
    # Push close well past TP so close-only fallback can still register TP
    # even after entry slippage shaves a few points off pts_favor.
    _seed_bar(
        source_db,
        bar_time="10:05",
        ts=_ts_for("10:05"),
        win_price=130000.0 + BUY_TP + 100.0,
        z_wdo=0.0,
        z_di=0.0,
    )

    summary = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides={
            "enabled": True,
            "intra_bar_sl_tp": True,
            "entry_slippage_pts": 0.0,
            "exit_slippage_pts": 0.0,
            "cost_per_contract_rt_brl": 0.0,
        },
    )

    assert summary["bars_processed"] == 2
    assert summary["trades_opened"] == 1
    assert summary["trades_closed"] == 1
    assert summary["warnings_by_reason"] == {"DATA:INTRA_BAR_DEGRADED": 2}

    # No DATA-phase MISSING_OHLC event — OHLC is optional, not required.
    # Instead we audit the close-only degradation explicitly.
    replay_db = os.path.join(out_dir, f"execution_timeline_{REPLAY_DATE}.db")
    conn = sqlite3.connect(replay_db)
    missing = conn.execute(
        "SELECT COUNT(*) FROM execution_timeline "
        "WHERE phase='DATA' AND event LIKE 'MISSING_%'"
    ).fetchone()[0]
    warning_rows = conn.execute(
        "SELECT status, severity, message, payload_json FROM execution_timeline "
        "WHERE phase='DATA' AND event='INTRA_BAR_DEGRADED' "
        "ORDER BY closed_bar_ts"
    ).fetchall()
    conn.close()
    assert missing == 0
    assert len(warning_rows) == 2
    assert {row[0] for row in warning_rows} == {"WARN"}
    assert {row[1] for row in warning_rows} == {"warning"}
    assert "close-only" in warning_rows[0][2]
    payload = json.loads(warning_rows[0][3])
    assert payload["fallback"] == "close_only"
    assert payload["missing_fields"] == ["win_high", "win_low"]


# ─── AC #5 — sim disabled = trade-relevant baseline ─────────────────────────

def test_replay_sim_disabled_matches_unset_baseline(source_db, out_dir, persisted_eg):
    """Two replays of the same source produce identical PnL/trade counts when
    (a) no simulation_overrides supplied and (b) sim.enabled=False explicit."""
    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        z_wdo=-2.1,
        z_di=-1.5,
        win_high=130100.0,
        win_low=129900.0,
    )
    _seed_bar(
        source_db,
        bar_time="10:05",
        ts=_ts_for("10:05"),
        win_price=130000.0 + BUY_TP,
        z_wdo=0.0,
        z_di=0.0,
        win_high=130000.0 + BUY_TP + 50.0,
        win_low=130000.0 + 200.0,
    )

    baseline = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
    )

    sim_off = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides={
            "enabled": False,
            "entry_slippage_pts": 50.0,  # would matter only if enabled
            "exit_slippage_pts": 50.0,
            "cost_per_contract_rt_brl": 25.0,
        },
    )

    # Trade-relevant fields must match bit-exactly when sim disabled
    assert sim_off["trades_opened"] == baseline["trades_opened"]
    assert sim_off["trades_closed"] == baseline["trades_closed"]
    assert sim_off["pnl_paper_brl"] == baseline["pnl_paper_brl"]
    # Runtime profile structure shape is stable across both runs
    assert "simulation" in baseline["runtime_profile"]
    assert "simulation" in sim_off["runtime_profile"]
    assert sim_off["runtime_profile"]["simulation"]["enabled"] is False
    assert baseline["runtime_profile"]["simulation"]["enabled"] is False


def test_replay_sim_enabled_reduces_pnl_by_slippage_and_cost(source_db, out_dir, persisted_eg):
    """Smoke test: sim enabled with slip+cost must reduce realized PnL vs baseline."""
    _seed_bar(
        source_db,
        bar_time="10:00",
        ts=_ts_for("10:00"),
        z_wdo=-2.1,
        z_di=-1.5,
        win_high=130100.0,
        win_low=129900.0,
    )
    _seed_bar(
        source_db,
        bar_time="10:05",
        ts=_ts_for("10:05"),
        win_price=130000.0 + BUY_TP,
        z_wdo=0.0,
        z_di=0.0,
        win_high=130000.0 + BUY_TP + 50.0,
        win_low=130000.0 + 200.0,
    )

    baseline = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
    )
    enabled = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides={
            "enabled": True,
            "entry_slippage_pts": 5.0,
            "exit_slippage_pts": 5.0,
            "cost_per_contract_rt_brl": 1.0,
        },
    )

    assert baseline["trades_closed"] == 1
    assert enabled["trades_closed"] == 1
    # Costs + slippage chew into PnL — must be strictly less
    assert enabled["pnl_paper_brl"] < baseline["pnl_paper_brl"]
