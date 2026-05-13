"""Tests for server._build_history (live-bar transformation + session/today filter).

Covers TASK-3 AC #2 corollary: lock down the merge logic that runs on every V2
poll and feeds the dashboard chart.
"""
from datetime import datetime, timedelta

import numpy as np
import pytest

import server
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


def test_price_arrays_merge_wdo_and_di_prices():
    today = datetime.now().replace(hour=11, minute=5, second=0, microsecond=0)
    times, z, spread = _mk_bars([today])

    out = _build_history(
        times,
        z,
        spread,
        win_prices=np.array([130000.0]),
        wdo_prices=np.array([5500.5]),
        di_prices=np.array([13.12]),
    )

    assert len(out) == 1
    assert out[0]["win_price"] == 130000.0
    assert out[0]["wdo_price"] == 5500.5
    assert out[0]["di_price"] == 13.12


def test_closed_di_z_from_cache_uses_closed_bar_not_current(monkeypatch):
    closed_local = datetime.now().replace(hour=11, minute=5, second=0, microsecond=0)
    open_local = closed_local + timedelta(minutes=5)
    closed_raw_ts = int(closed_local.timestamp()) - TIME_OFFSET

    monkeypatch.setattr(
        server,
        "_di_cache",
        {
            "current_z": 9.99,
            "history": [
                {
                    "date": closed_local.strftime("%Y-%m-%d"),
                    "bar_time": closed_local.strftime("%H:%M"),
                    "z": -1.23,
                },
                {
                    "date": open_local.strftime("%Y-%m-%d"),
                    "bar_time": open_local.strftime("%H:%M"),
                    "z": 9.99,
                },
            ],
        },
    )

    assert server._closed_di_z_from_cache(closed_raw_ts, fallback=0.0) == -1.23


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


def test_build_history_attaches_ohlc_when_arrays_provided():
    """OHLC arrays parallel to win_prices/wdo_prices/di_prices flow into entry dict."""
    today = datetime.now().replace(hour=11, minute=10, second=0, microsecond=0)
    times = np.array([_utc_ts_for_local(today)], dtype=np.int64)
    z = np.array([0.0])
    spread = np.array([42.0])

    out = _build_history(
        times, z, spread,
        win_prices=np.array([130000.0]),
        wdo_prices=np.array([5500.5]),
        di_prices=np.array([13.12]),
        win_opens=np.array([129995.0]),
        win_highs=np.array([130020.0]),
        win_lows=np.array([129980.0]),
        wdo_opens=np.array([5500.0]),
        wdo_highs=np.array([5502.0]),
        wdo_lows=np.array([5499.0]),
        di_opens=np.array([13.10]),
        di_highs=np.array([13.15]),
        di_lows=np.array([13.08]),
    )
    assert len(out) == 1
    e = out[0]
    assert e["win_open"] == 129995.0
    assert e["win_high"] == 130020.0
    assert e["win_low"] == 129980.0
    assert e["wdo_open"] == 5500.0
    assert e["wdo_high"] == 5502.0
    assert e["wdo_low"] == 5499.0
    assert e["di_open"] == 13.10
    assert e["di_high"] == 13.15
    assert e["di_low"] == 13.08


def test_build_history_di_ohlc_map_fallback():
    """When DI arrays are absent (regime_v2 path), di_ohlc_map fills DI OHLC."""
    today = datetime.now().replace(hour=11, minute=15, second=0, microsecond=0)
    times = np.array([_utc_ts_for_local(today)], dtype=np.int64)
    z = np.array([0.0])
    spread = np.array([42.0])
    local_ts = int(times[0]) + TIME_OFFSET
    di_price_map = {local_ts: 13.12}
    di_ohlc_map = {local_ts: (13.10, 13.15, 13.08)}

    out = _build_history(
        times, z, spread,
        di_price_map=di_price_map,
        di_ohlc_map=di_ohlc_map,
    )
    assert len(out) == 1
    e = out[0]
    assert e["di_price"] == 13.12
    assert e["di_open"] == 13.10
    assert e["di_high"] == 13.15
    assert e["di_low"] == 13.08


def test_build_history_ohlc_arrays_optional():
    """Calling without OHLC arrays leaves OHLC keys absent (graceful)."""
    today = datetime.now().replace(hour=11, minute=20, second=0, microsecond=0)
    times = np.array([_utc_ts_for_local(today)], dtype=np.int64)
    out = _build_history(
        times, np.array([0.0]), np.array([42.0]),
        win_prices=np.array([130000.0]),
    )
    assert len(out) == 1
    e = out[0]
    assert "win_open" not in e
    assert "win_high" not in e
    assert "win_low" not in e
