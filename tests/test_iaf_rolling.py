import json
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

# Import the functions we want to test
from server import calculate_directional_efficiency, calculate_flow_acceleration

def test_calculate_directional_efficiency_lookback():
    # Construct 10 mock database rows
    # i=0 to 4: price increases, XP net increases (positive influence)
    # i=5 to 9: price increases, XP net decreases (negative influence)
    rows_mock = []
    
    xp_nets = [0, 100, 200, 300, 400, 300, 200, 100, 0, -100]
    prices = [130000 + i * 100 for i in range(10)]
    
    for i in range(10):
        flow = {
            "WIN": {
                "XP": {"net": xp_nets[i]}
            }
        }
        row = MagicMock()
        # Bind flow and idx at definition time using argument defaults to avoid closure issues
        row.__getitem__.side_effect = lambda key, idx=i, f=flow: {
            "win_price": prices[idx],
            "flow_json": json.dumps(f)
        }[key]
        rows_mock.append(row)

    with patch("sqlite3.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows_mock
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Test 1: Full-day calculation (none lookback)
        # Expected:
        # Changes:
        # i=1: dPrice=100, dNet=100 -> product = 10000
        # i=2: dPrice=100, dNet=100 -> product = 10000
        # i=3: dPrice=100, dNet=100 -> product = 10000
        # i=4: dPrice=100, dNet=100 -> product = 10000
        # i=5: dPrice=100, dNet=-100 -> product = -10000
        # i=6: dPrice=100, dNet=-100 -> product = -10000
        # i=7: dPrice=100, dNet=-100 -> product = -10000
        # i=8: dPrice=100, dNet=-100 -> product = -10000
        # i=9: dPrice=100, dNet=-100 -> product = -10000
        # Num sum = 40000 - 50000 = -10000
        # Den sum = 40000 + 50000 = 90000
        # Efficiency = (-10000 / 90000) * 100 = -11.1
        eff_all = calculate_directional_efficiency()
        assert eff_all["WIN"]["XP"] == -11.1

        # Test 2: 5-bar lookback (last 5 rows, i.e., index 5 to 9)
        # Index 5 is used as the baseline (no change accumulated)
        # Changes accumulated at:
        # i=6: dPrice=100, dNet=-100 -> product = -10000
        # i=7: dPrice=100, dNet=-100 -> product = -10000
        # i=8: dPrice=100, dNet=-100 -> product = -10000
        # i=9: dPrice=100, dNet=-100 -> product = -10000
        # Num sum = -40000
        # Den sum = 40000
        # Efficiency = (-40000 / 40000) * 100 = -100.0
        eff_5 = calculate_directional_efficiency(lookback_bars=5)
        assert eff_5["WIN"]["XP"] == -100.0

def test_calculate_flow_acceleration_rolling_dominance():
    # Construct 6 mock database rows where XP is dominant (efficiency >= 40%) in short-term
    # but could be negative/different overall
    rows_mock = []
    
    xp_nets = [0, 100, 200, 300, 400, 500]
    prices = [130000 + i * 100 for i in range(6)]
    
    for i in range(6):
        flow = {
            "WIN": {
                "XP": {"net": xp_nets[i]}
            }
        }
        row = MagicMock()
        row.__getitem__.side_effect = lambda key, idx=i, f=flow: {
            "win_price": prices[idx],
            "flow_json": json.dumps(f)
        }[key]
        rows_mock.append(row)

    with patch("sqlite3.connect") as mock_connect, patch("server.connect_mt5", return_value=False):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows_mock
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Under the hood:
        # short_term_eff = calculate_directional_efficiency(lookback_bars=5)
        # XP efficiency should be 100.0. XP is dominant!
        # lots_per_unit = 100.0
        # XP pressure = (500 - 400) * 1.0 = 100.0
        # iaf = (100.0 / 100.0) * 100.0 * 5.0 = 500.0 -> clamped to 100.0
        iaf = calculate_flow_acceleration()
        assert iaf["WIN"] == 100.0
