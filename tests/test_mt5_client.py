"""Tests for core/mt5_client.py order helpers — TASK-2 AC #4/#5.

All MT5 API calls are monkeypatched; no real terminal required.
The helpers must be pure wrappers: no retry, no state, caller owns decisions.
"""
import types
import pytest
import MetaTrader5 as mt5

import core.mt5_client as client


# ─── Factories ──────────────────────────────────────────────────────────────

def _order_result(retcode=10009, order=111222, price=130000.0, comment="done"):
    """Minimal OrderSendResult-like namespace."""
    r = types.SimpleNamespace()
    r.retcode = retcode
    r.order = order
    r.price = price
    r.comment = comment
    return r


def _position(ticket=111222, symbol="WIN$N", pos_type=0, volume=2.0,
              price_open=130000.0, magic=770001, comment=""):
    p = types.SimpleNamespace()
    p.ticket = ticket
    p.symbol = symbol
    p.type = pos_type          # 0=BUY, 1=SELL
    p.volume = volume
    p.price_open = price_open
    p.magic = magic
    p.comment = comment
    return p


# ─── send_market_order ───────────────────────────────────────────────────────

def test_send_market_order_buy_ok(monkeypatch):
    monkeypatch.setattr(mt5, "order_send", lambda req: _order_result())
    res = client.send_market_order("WIN$N", "BUY", 2.0, magic=770001, deviation=50)
    assert res["ok"] is True
    assert res["ticket"] == 111222
    assert res["price"] == 130000.0
    assert res["retcode"] == mt5.TRADE_RETCODE_DONE


def test_send_market_order_sell_ok(monkeypatch):
    monkeypatch.setattr(mt5, "order_send", lambda req: _order_result(order=111333))
    res = client.send_market_order("WIN$N", "SELL", 2.0, magic=770001, deviation=50)
    assert res["ok"] is True
    assert res["ticket"] == 111333


def test_send_market_order_uses_correct_order_type(monkeypatch):
    captured = {}

    def fake_send(req):
        captured["type"] = req["type"]
        return _order_result()

    monkeypatch.setattr(mt5, "order_send", fake_send)
    client.send_market_order("WIN$N", "BUY", 2.0, magic=770001, deviation=50)
    assert captured["type"] == mt5.ORDER_TYPE_BUY

    client.send_market_order("WIN$N", "SELL", 2.0, magic=770001, deviation=50)
    assert captured["type"] == mt5.ORDER_TYPE_SELL


def test_send_market_order_failure_retcode(monkeypatch):
    monkeypatch.setattr(mt5, "order_send", lambda req: _order_result(retcode=10004, comment="requote"))
    res = client.send_market_order("WIN$N", "BUY", 2.0, magic=770001, deviation=50)
    assert res["ok"] is False
    assert res["ticket"] is None
    assert res["price"] is None
    assert res["retcode"] == 10004


def test_send_market_order_none_result(monkeypatch):
    """order_send returning None (terminal unreachable) must not raise."""
    monkeypatch.setattr(mt5, "order_send", lambda req: None)
    monkeypatch.setattr(mt5, "last_error", lambda: (1, "disconnected"))
    res = client.send_market_order("WIN$N", "BUY", 2.0, magic=770001, deviation=50)
    assert res["ok"] is False
    assert res["retcode"] == -1


def test_send_market_order_payload_fields(monkeypatch):
    """Request dict must include required MT5 fields."""
    captured = {}

    def fake_send(req):
        captured.update(req)
        return _order_result()

    monkeypatch.setattr(mt5, "order_send", fake_send)
    client.send_market_order("WIN$N", "BUY", 2.0, magic=770001, deviation=50, comment="CONS_BASE")
    assert captured["action"] == mt5.TRADE_ACTION_DEAL
    assert captured["symbol"] == "WIN$N"
    assert captured["volume"] == 2.0
    assert captured["magic"] == 770001
    assert captured["deviation"] == 50
    assert captured["comment"] == "CONS_BASE"
    assert captured["type_filling"] == mt5.ORDER_FILLING_RETURN


# ─── close_position_by_ticket ────────────────────────────────────────────────

def test_close_position_buy_ok(monkeypatch):
    pos = _position(ticket=111222, pos_type=mt5.POSITION_TYPE_BUY)
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [pos])
    monkeypatch.setattr(mt5, "order_send", lambda req: _order_result(order=222333, price=130500.0))
    res = client.close_position_by_ticket(111222, magic=770001)
    assert res["ok"] is True
    assert res["ticket"] == 222333
    assert res["price"] == 130500.0


def test_close_position_sell_uses_buy_counter_side(monkeypatch):
    """Closing a SELL position must submit ORDER_TYPE_BUY."""
    pos = _position(ticket=111333, pos_type=mt5.POSITION_TYPE_SELL)
    captured = {}

    def fake_send(req):
        captured["type"] = req["type"]
        return _order_result(order=111333)

    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [pos])
    monkeypatch.setattr(mt5, "order_send", fake_send)
    res = client.close_position_by_ticket(111333, magic=770001)
    assert res["ok"] is True
    assert captured["type"] == mt5.ORDER_TYPE_BUY


def test_close_position_not_found(monkeypatch):
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [])
    res = client.close_position_by_ticket(999999, magic=770001)
    assert res["ok"] is False
    assert res["message"] == "POSITION_NOT_FOUND"
    assert res["ticket"] == 999999


def test_close_position_failure_retcode(monkeypatch):
    pos = _position(ticket=111222)
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [pos])
    monkeypatch.setattr(mt5, "order_send", lambda req: _order_result(retcode=10006, comment="timeout"))
    res = client.close_position_by_ticket(111222, magic=770001)
    assert res["ok"] is False
    assert res["retcode"] == 10006
    assert res["price"] is None


def test_close_position_order_send_none(monkeypatch):
    pos = _position(ticket=111222)
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [pos])
    monkeypatch.setattr(mt5, "order_send", lambda req: None)
    monkeypatch.setattr(mt5, "last_error", lambda: (1, "disconnected"))
    res = client.close_position_by_ticket(111222, magic=770001)
    assert res["ok"] is False
    assert res["retcode"] == -1


def test_close_position_includes_position_id_in_request(monkeypatch):
    """Request must include 'position' key so MT5 routes the close correctly."""
    pos = _position(ticket=111222, pos_type=mt5.POSITION_TYPE_BUY)
    captured = {}

    def fake_send(req):
        captured.update(req)
        return _order_result()

    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [pos])
    monkeypatch.setattr(mt5, "order_send", fake_send)
    client.close_position_by_ticket(111222, magic=770001, comment="SL_EXIT")
    assert captured["position"] == 111222
    assert captured["comment"] == "SL_EXIT"
    assert captured["magic"] == 770001


# ─── list_open_positions ─────────────────────────────────────────────────────

def test_list_open_positions_no_filter(monkeypatch):
    positions = [
        _position(ticket=1, symbol="WIN$N", pos_type=mt5.POSITION_TYPE_BUY, magic=770001),
        _position(ticket=2, symbol="WIN$N", pos_type=mt5.POSITION_TYPE_SELL, magic=770002),
    ]
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: positions)
    result = client.list_open_positions()
    assert len(result) == 2
    assert result[0]["type"] == "BUY"
    assert result[1]["type"] == "SELL"


def test_list_open_positions_filter_by_symbol(monkeypatch):
    def fake_get(**kw):
        assert kw.get("symbol") == "WIN$N"
        return [_position(symbol="WIN$N")]

    monkeypatch.setattr(mt5, "positions_get", fake_get)
    result = client.list_open_positions(symbol="WIN$N")
    assert len(result) == 1
    assert result[0]["symbol"] == "WIN$N"


def test_list_open_positions_filter_by_magic(monkeypatch):
    positions = [
        _position(ticket=1, magic=770001),
        _position(ticket=2, magic=770002),
        _position(ticket=3, magic=770001),
    ]
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: positions)
    result = client.list_open_positions(magic=770001)
    tickets = [r["ticket"] for r in result]
    assert tickets == [1, 3]


def test_list_open_positions_empty(monkeypatch):
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [])
    assert client.list_open_positions() == []


def test_list_open_positions_none_from_api(monkeypatch):
    """positions_get returning None must not raise — treated as empty."""
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: None)
    assert client.list_open_positions() == []


def test_list_open_positions_exception_returns_empty(monkeypatch):
    """positions_get raising must return empty list, not propagate."""
    def boom(**kw):
        raise RuntimeError("terminal not connected")

    monkeypatch.setattr(mt5, "positions_get", boom)
    result = client.list_open_positions()
    assert result == []


def test_list_open_positions_dict_keys(monkeypatch):
    pos = _position(ticket=5, symbol="WIN$N", price_open=130000.0, magic=770001)
    monkeypatch.setattr(mt5, "positions_get", lambda **kw: [pos])
    result = client.list_open_positions()
    assert set(result[0].keys()) == {"ticket", "symbol", "type", "volume", "price_open", "magic", "comment"}
