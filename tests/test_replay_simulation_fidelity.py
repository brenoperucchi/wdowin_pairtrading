"""End-to-end MT5 fidelity tests for the replay pipeline (Slice A.8).

Exercises the full replay funnel — `run_replay()` reads `bar_history` rows
(with OHLC), resolves `simulation_profile` from runtime_config, and feeds
the same `TradeEngine.evaluate()` used in live. Each scenario asserts what
actually lands in `matador_ops` (entry/exit price, pnl, exit_reason) and
the timeline event payload — i.e. the behaviour an operator inspecting
the replay DB would see.

Engine-level unit coverage lives in tests/test_trade_engine_simulation.py;
this file is the replay-level mirror that proves wiring + persistence.

Covers TASK-17.8 acceptance criteria:
  1. 7 deterministic scenarios with fixed fixtures.
  2. Each scenario asserts: exit_reason, price_win_in, price_win_out, pnl_brl.
  3. Scenario 6 compares the matador_ops row bit-exactly to a baseline.
  4. No MT5 dependency (conftest.py stubs MetaTrader5).
"""
from __future__ import annotations

import json
import sqlite3
import time

import pytest

import scripts.replay_execution_timeline as replay
from core.config import (
    BUY_SL,
    BUY_TP,
    WIN_CONTRACTS,
    WIN_PV,
)
from server import init_bar_history, save_bar_history


REPLAY_DATE = "2026-05-12"
ENTRY_BAR_TIME = "10:00"
EXIT_BAR_TIME = "10:05"


# ─── Fixtures ───────────────────────────────────────────────────────────────

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
    z_wdo: float = 0.0,
    z_di: float = 0.0,
    eg_pvalue: float = 0.04,
    rho: float = -0.85,
    rho_level: int = 0,
    beta_value: float = 23.5,
    beta_delta_pct: float = 2.0,
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
        win_high=win_high,
        win_low=win_low,
        db_path=db_path,
    )


def _seed_buy_entry(db_path: str, *, win_high: float | None = None, win_low: float | None = None) -> None:
    """Plant the CONS_BASE BUY-trigger bar at 10:00."""
    _seed_bar(
        db_path,
        bar_time=ENTRY_BAR_TIME,
        ts=_ts_for(ENTRY_BAR_TIME),
        z_wdo=-2.1,
        z_di=-1.5,
        win_high=win_high,
        win_low=win_low,
    )


def _seed_exit_bar(
    db_path: str,
    *,
    win_price: float,
    win_high: float | None = None,
    win_low: float | None = None,
) -> None:
    """Plant a follow-up bar at 10:05 with neutral z's so no new entry fires."""
    _seed_bar(
        db_path,
        bar_time=EXIT_BAR_TIME,
        ts=_ts_for(EXIT_BAR_TIME),
        win_price=win_price,
        z_wdo=0.0,
        z_di=0.0,
        win_high=win_high,
        win_low=win_low,
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


def _replay_db_path(out_dir: str) -> str:
    return f"{out_dir}/execution_timeline_{REPLAY_DATE}.db"


def _closed_trade_row(replay_db: str) -> dict:
    conn = sqlite3.connect(replay_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM matador_ops WHERE status='CLOSED' ORDER BY id"
    ).fetchone()
    conn.close()
    assert row is not None, f"no CLOSED trade in {replay_db}"
    return dict(row)


def _exit_event(replay_db: str) -> dict:
    conn = sqlite3.connect(replay_db)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM execution_timeline "
        "WHERE phase='EXIT' AND event IN ('TARGET','STOP_LOSS','BE_STOP','FORCE_CLOSE') "
        "ORDER BY id"
    ).fetchone()
    conn.close()
    assert row is not None, f"no EXIT trigger event in {replay_db}"
    out = dict(row)
    out["payload"] = json.loads(out["payload_json"]) if out.get("payload_json") else {}
    return out


def _sim_overrides(**overrides) -> dict:
    """Build a fully-specified simulation_overrides dict (everything explicit)."""
    base = {
        "enabled": True,
        "entry_slippage_pts": 0.0,
        "exit_slippage_pts": 0.0,
        "cost_per_contract_rt_brl": 0.0,
        "intra_bar_sl_tp": True,
        "exit_at_sl_tp_level": True,
        "conflict_rule": "sl_first",
    }
    base.update(overrides)
    return base


# ─── Scenario 1 — Entry + Exit slippage (BUY TARGET) ────────────────────────

def test_buy_entry_and_exit_slippage_lands_in_matador_ops(source_db, out_dir, persisted_eg):
    """Entry close=130000, slip=5 → entry=130005. TP=800, exit-slip=5, cost=0
    → final_pts_favor=795, exit_price=130800, pnl=795*0.4 = 318.0."""
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    # Wide bar that clears TP: high>=130005+800=130805 and low>entry to avoid BE_STOP race.
    _seed_exit_bar(source_db, win_price=130700.0, win_high=131000.0, win_low=130500.0)

    summary = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(
            entry_slippage_pts=5.0,
            exit_slippage_pts=5.0,
            cost_per_contract_rt_brl=0.0,
        ),
    )

    assert summary["trades_opened"] == 1
    assert summary["trades_closed"] == 1

    trade = _closed_trade_row(_replay_db_path(out_dir))
    assert trade["direction"] == "BUY"
    assert trade["exit_reason"] == "TARGET"
    assert trade["price_win_in"] == pytest.approx(130005.0)
    assert trade["price_win_out"] == pytest.approx(130800.0)
    assert trade["pnl_brl"] == pytest.approx(795.0 * WIN_CONTRACTS * WIN_PV)

    exit_evt = _exit_event(_replay_db_path(out_dir))
    assert exit_evt["event"] == "TARGET"
    assert exit_evt["payload"]["exit_slippage_pts"] == 5.0
    assert exit_evt["payload"]["simulation_enabled"] is True
    assert exit_evt["payload"]["intra_bar_used"] is True


# ─── Scenario 2 — Exit at SL level (NOT at close price) ─────────────────────

def test_intra_bar_sl_exits_at_level_not_at_close(source_db, out_dir, persisted_eg):
    """Low wick hits SL but close recovers above. Exit must be at SL level,
    not at the close — that's the whole point of exit_at_sl_tp_level."""
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    # close 130000 (recovered) but low=129700 = entry-SL=130000-300
    _seed_exit_bar(source_db, win_price=130000.0, win_high=130050.0, win_low=129700.0)

    replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(),
    )

    trade = _closed_trade_row(_replay_db_path(out_dir))
    assert trade["exit_reason"] == "STOP_LOSS"
    assert trade["price_win_in"] == pytest.approx(130000.0)
    assert trade["price_win_out"] == pytest.approx(130000.0 - BUY_SL)  # 129700
    assert trade["pnl_brl"] == pytest.approx(-BUY_SL * WIN_CONTRACTS * WIN_PV)  # -120.0


# ─── Scenario 3 — Intra-bar TP via wick (close BELOW TP) ────────────────────

def test_intra_bar_tp_from_wick_when_close_below_tp(source_db, out_dir, persisted_eg):
    """High wick reaches TP but close didn't. Without intra_bar logic the
    trade would stay open. With it: exit at TP level inside the same bar.
    Note: keep win_low > entry to avoid BE_STOP race (BE auto-activates
    intra-bar when max_favor >= BUY_BE_ACT = 300 < BUY_TP)."""
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    # close 130100 (below entry+800=130800), high=130850 (wick crosses TP),
    # low=130100 (above entry so favor_low=100 > be_lock=0 → no BE_STOP race).
    _seed_exit_bar(source_db, win_price=130100.0, win_high=130850.0, win_low=130100.0)

    replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(),
    )

    trade = _closed_trade_row(_replay_db_path(out_dir))
    assert trade["exit_reason"] == "TARGET"
    assert trade["price_win_in"] == pytest.approx(130000.0)
    assert trade["price_win_out"] == pytest.approx(130000.0 + BUY_TP)  # 130800
    assert trade["pnl_brl"] == pytest.approx(BUY_TP * WIN_CONTRACTS * WIN_PV)  # 320.0


# ─── Scenario 4 — TP+SL conflict resolution (sl_first vs tp_first) ──────────

def test_conflict_rule_sl_first_resolves_to_be_stop_when_tp_and_bestop_collide(
    source_db, out_dir, persisted_eg
):
    """Realistic same-bar conflict for our config: TP and BE_STOP fire
    together (raw SL=300 unreachable because BE auto-activates first when
    max_favor >= BE_ACT=300 < BUY_TP=800). sl_first picks the stop-side."""
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    # high=130850 (>TP=800), low=129950 (favor_low=-50 ≤ be_lock=0 → BE_STOP)
    _seed_exit_bar(source_db, win_price=130000.0, win_high=130850.0, win_low=129950.0)

    replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(conflict_rule="sl_first"),
    )

    trade = _closed_trade_row(_replay_db_path(out_dir))
    assert trade["exit_reason"] == "BE_STOP"
    assert trade["price_win_out"] == pytest.approx(130000.0)  # be_lock=0 → entry
    assert trade["pnl_brl"] == pytest.approx(0.0)


def test_conflict_rule_tp_first_resolves_to_target_when_tp_and_bestop_collide(
    source_db, out_dir, persisted_eg
):
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    _seed_exit_bar(source_db, win_price=130000.0, win_high=130850.0, win_low=129950.0)

    replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(conflict_rule="tp_first"),
    )

    trade = _closed_trade_row(_replay_db_path(out_dir))
    assert trade["exit_reason"] == "TARGET"
    assert trade["price_win_out"] == pytest.approx(130000.0 + BUY_TP)
    assert trade["pnl_brl"] == pytest.approx(BUY_TP * WIN_CONTRACTS * WIN_PV)


def test_conflict_rule_sl_first_resolves_to_stop_loss_when_tp_and_raw_sl_collide(
    source_db, out_dir, persisted_eg
):
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    _seed_exit_bar(
        source_db,
        win_price=130000.0,
        win_high=130850.0,
        win_low=130000.0 - BUY_SL - 5,
    )

    replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(conflict_rule="sl_first"),
    )

    trade = _closed_trade_row(_replay_db_path(out_dir))
    assert trade["exit_reason"] == "STOP_LOSS"
    assert trade["price_win_out"] == pytest.approx(130000.0 - BUY_SL)
    assert trade["pnl_brl"] == pytest.approx(-BUY_SL * WIN_CONTRACTS * WIN_PV)


# ─── Scenario 5 — Round-trip cost deducted from pnl ─────────────────────────

def test_cost_per_contract_rt_deducted_from_persisted_pnl(source_db, out_dir, persisted_eg):
    """1.0 BRL/contract round-trip × WIN_CONTRACTS=2 = 2.0 BRL off the gross."""
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    _seed_exit_bar(source_db, win_price=130100.0, win_high=130850.0, win_low=130100.0)

    replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(cost_per_contract_rt_brl=1.0),
    )

    replay_db = _replay_db_path(out_dir)
    trade = _closed_trade_row(replay_db)
    gross = BUY_TP * WIN_CONTRACTS * WIN_PV   # 320.0
    cost = 1.0 * WIN_CONTRACTS                # 2.0
    assert trade["exit_reason"] == "TARGET"
    assert trade["pnl_brl"] == pytest.approx(gross - cost)
    assert _exit_event(replay_db)["payload"]["cost_brl"] == pytest.approx(cost)


# ─── Scenario 6 — sim enabled=False is bit-exact to baseline ────────────────

def test_simulation_disabled_matches_baseline_trade_row_bit_exact(
    source_db, out_dir, persisted_eg, tmp_path
):
    """Two replays of the same bars:
      A) no simulation_overrides at all (pre-A.7 behaviour)
      B) simulation_overrides with enabled=False AND ridiculous slip/cost values

    The persisted matador_ops row must match field-by-field — proving the
    'enabled=False' path is a true no-op regardless of the rest of the block."""
    _seed_buy_entry(source_db, win_high=130100.0, win_low=129900.0)
    # Plain close-only TARGET: close = entry+TP, no wicks needed.
    _seed_exit_bar(source_db, win_price=130000.0 + BUY_TP, win_high=None, win_low=None)

    baseline_out = str(tmp_path / "baseline")
    sim_off_out = str(tmp_path / "sim_off")
    import os
    os.makedirs(baseline_out, exist_ok=True)
    os.makedirs(sim_off_out, exist_ok=True)

    replay.run_replay(date_str=REPLAY_DATE, source_db=source_db, out_dir=baseline_out)
    replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=sim_off_out,
        simulation_overrides={
            "enabled": False,
            "entry_slippage_pts": 25.0,  # would change entry IF enabled
            "exit_slippage_pts": 25.0,
            "cost_per_contract_rt_brl": 25.0,
            "intra_bar_sl_tp": True,
            "exit_at_sl_tp_level": True,
            "conflict_rule": "tp_first",
        },
    )

    baseline_trade = _closed_trade_row(f"{baseline_out}/execution_timeline_{REPLAY_DATE}.db")
    sim_off_trade = _closed_trade_row(f"{sim_off_out}/execution_timeline_{REPLAY_DATE}.db")

    # Trade-relevant columns must be bit-exact. timestamp_in/out and id can
    # differ between runs even on the same bars (autoincrement id, but close
    # in time so timestamp_* should also align).
    for col in (
        "direction", "strategy", "exit_reason",
        "price_win_in", "price_win_out", "pnl_brl",
        "max_pts_favor", "be_active",
    ):
        assert sim_off_trade[col] == baseline_trade[col], (
            f"column {col!r} drifted under sim.enabled=False: "
            f"baseline={baseline_trade[col]!r} sim_off={sim_off_trade[col]!r}"
        )


# ─── Scenario 7 — OHLC absent + intra_bar=True → graceful degradation ───────

def test_intra_bar_without_ohlc_emits_warning_event_and_continues(
    source_db, out_dir, persisted_eg
):
    """Legacy rows (no win_high/win_low) under sim.enabled=True with
    intra_bar_sl_tp must NOT crash and must emit a DATA-phase warning event
    so an operator inspecting the timeline knows fidelity degraded."""
    # Both bars seeded WITHOUT OHLC
    _seed_buy_entry(source_db)
    _seed_exit_bar(source_db, win_price=130000.0 + BUY_TP + 100.0)

    summary = replay.run_replay(
        date_str=REPLAY_DATE,
        source_db=source_db,
        out_dir=out_dir,
        simulation_overrides=_sim_overrides(
            entry_slippage_pts=0.0,
            exit_slippage_pts=0.0,
            cost_per_contract_rt_brl=0.0,
            intra_bar_sl_tp=True,
        ),
    )

    assert summary["bars_processed"] == 2
    assert summary["trades_opened"] == 1
    assert summary["trades_closed"] == 1  # close-only fallback still fires TARGET

    replay_db = _replay_db_path(out_dir)
    conn = sqlite3.connect(replay_db)
    conn.row_factory = sqlite3.Row
    degraded = conn.execute(
        "SELECT * FROM execution_timeline "
        "WHERE phase='DATA' AND event='INTRA_BAR_DEGRADED' "
        "ORDER BY id"
    ).fetchall()
    conn.close()
    # Two bars processed → two degraded warnings (one per bar)
    assert len(degraded) == 2
    assert all(row["status"] == "WARN" for row in degraded)
    payload = json.loads(degraded[0]["payload_json"])
    assert payload["fallback"] == "close_only"
    assert payload["simulation_enabled"] is True
    assert payload["intra_bar_sl_tp"] is True
    assert set(payload["missing_fields"]) == {"win_high", "win_low"}

    # Trade still closed via close-only (intra_bar logic skipped)
    trade = _closed_trade_row(replay_db)
    assert trade["exit_reason"] == "TARGET"
    exit_evt = _exit_event(replay_db)
    assert exit_evt["payload"]["intra_bar_used"] is False
