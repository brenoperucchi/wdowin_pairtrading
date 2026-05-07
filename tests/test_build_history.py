"""Tests for server._build_history (live-bar transformation + session/today filter).

Covers TASK-3 AC #2 corollary: lock down the merge logic that runs on every V2
poll and feeds the dashboard chart.
"""
from datetime import datetime, timedelta

import numpy as np
import pytest

from core.config import TIME_OFFSET
from server import _build_history


def _utc_ts_for_local(dt: datetime) -> int:
    """server._build_history adds TIME_OFFSET to bar_times to derive local time;
    inverse here so a desired local datetime maps back to the input timestamp."""
    return int(dt.timestamp()) - TIME_OFFSET


def _mk_bars(local_dts):
    times = np.array([_utc_ts_for_local(dt) for dt in local_dts], dtype=np.int64)
    z = np.linspace(-1.0, 1.0, len(local_dts))
    spread = np.linspace(40.0, 50.0, len(local_dts))
    return times, z, spread


def test_filters_today_only():
    today = datetime.now().replace(hour=10, minute=30, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    times, z, spread = _mk_bars([yesterday, today])

    out = _build_history(times, z, spread)
    assert len(out) == 1
    assert out[0]["date"] == today.strftime("%Y-%m-%d")
    assert out[0]["bar_time"] == "10:30"


def test_filters_session_window():
    today = datetime.now().date()
    in_session = datetime.combine(today, datetime.min.time()).replace(hour=10, minute=0)
    after_session = datetime.combine(today, datetime.min.time()).replace(hour=19, minute=0)
    times, z, spread = _mk_bars([in_session, after_session])

    out = _build_history(times, z, spread)
    assert len(out) == 1
    assert out[0]["bar_time"] == "10:00"


def test_di_map_lookup_merges_z_di():
    today = datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)
    times, z, spread = _mk_bars([today])
    local_ts = int(times[0]) + TIME_OFFSET
    di_map = {local_ts: 0.42}

    out = _build_history(times, z, spread, di_map=di_map)
    assert len(out) == 1
    assert out[0]["z_di"] == 0.42


def test_nwe_blocking_buy_signal_when_up():
    """If NWE trend is up and z_wdo is negative (buy direction), sig_wdo should be zeroed."""
    today = datetime.now().replace(hour=11, minute=30, second=0, microsecond=0)
    times = np.array([_utc_ts_for_local(today)], dtype=np.int64)
    z = np.array([-2.0])  # buy signal
    spread = np.array([42.0])
    win_prices = np.array([130000.0])
    nwe_data = (
        np.array([130100.0]),  # center
        np.array([130250.0]),  # upper
        np.array([129950.0]),  # lower
        np.array([True]),       # is_up → buy blocked
    )

    out = _build_history(times, z, spread, win_prices=win_prices, nwe_data=nwe_data)
    assert len(out) == 1
    assert out[0]["sig_wdo"] == 0
    assert out[0]["z_raw_wdo"] == 0
    assert out[0]["z_unfiltered_wdo"] == -2.0  # original preserved


def test_nwe_does_not_block_when_signal_aligned_with_trend():
    """If NWE up and z_wdo positive (sell direction), sig should pass (not blocked by buy gate)."""
    today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    times = np.array([_utc_ts_for_local(today)], dtype=np.int64)
    z = np.array([2.0])  # sell signal
    spread = np.array([45.0])
    # Position win_price below npu so isSellBlocked = win < npu = True. To NOT block sell:
    # set win > npu. With center=130100, upper=130250: envW=150, npu = 130250 - 30 = 130220.
    win_prices = np.array([130230.0])
    nwe_data = (
        np.array([130100.0]),
        np.array([130250.0]),
        np.array([129950.0]),
        np.array([True]),  # is_up → not blocked by !is_up branch
    )

    out = _build_history(times, z, spread, win_prices=win_prices, nwe_data=nwe_data)
    # sell-side: not blocked because is_up=True (not !is_up) AND win > npu
    assert out[0]["sig_wdo"] == 1
    assert out[0]["z_raw_wdo"] == 2.0
