import sqlite3
import core.trade_engine as te
from core.config import (
    LIVE_DEVIATION,
    LIVE_MAGIC_BASE,
    LIVE_ORDERS,
    LIVE_SYMBOL_WIN,
    MAGIC_BY_STRATEGY,
    SYMBOL_A,
)
from core.trade_engine import STRATEGIES, TradeEngine


def _gate(allowed=True, reasons=None):
    return {
        "allowed": allowed,
        "reasons": list(reasons) if reasons else [],
        "checks": {},
        "informational": {"joh_open": True, "hmm_state": None, "eg_pvalue": 0.02},
    }


def _columns(db_path):
    conn = sqlite3.connect(db_path)
    rows = conn.execute("PRAGMA table_info(matador_ops)").fetchall()
    conn.close()
    return {row[1]: row for row in rows}


def test_live_orders_default_keeps_engine_paper_only():
    assert LIVE_ORDERS is False
    assert LIVE_SYMBOL_WIN == SYMBOL_A
    assert LIVE_DEVIATION > 0
    assert LIVE_MAGIC_BASE == 770000


def test_magic_by_strategy_is_unique_and_stable():
    assert set(MAGIC_BY_STRATEGY) == set(STRATEGIES)
    assert MAGIC_BY_STRATEGY == {
        "CONS_BASE": 770001,
        "WDO_NWE": 770002,
        "DI_NWE": 770003,
    }
    assert len(set(MAGIC_BY_STRATEGY.values())) == len(STRATEGIES)


def test_matador_ops_live_columns_created_on_fresh_db(tmp_path):
    db_path = tmp_path / "trades.db"
    TradeEngine(str(db_path))

    cols = _columns(db_path)
    assert cols["mt5_ticket_in"][2].upper() == "INTEGER"
    assert cols["mt5_ticket_out"][2].upper() == "INTEGER"
    assert cols["mt5_magic"][2].upper() == "INTEGER"
    assert cols["live"][2].upper() == "INTEGER"
    assert cols["live"][4] == "0"


def test_matador_ops_live_migration_is_idempotent_on_legacy_db(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE matador_ops (id INTEGER PRIMARY KEY AUTOINCREMENT)")
    conn.commit()
    conn.close()

    TradeEngine(str(db_path))
    TradeEngine(str(db_path))

    cols = _columns(db_path)
    for name in ("strategy", "mt5_ticket_in", "mt5_ticket_out", "mt5_magic", "live"):
        assert name in cols


def test_open_trade_paper_persists_live_zero_and_no_mt5_ticket(tmp_path):
    db_path = tmp_path / "trades.db"
    engine = TradeEngine(str(db_path))

    result = engine.evaluate(
        z_wdo=-2.1,
        z_di=-1.5,
        win_price=130000,
        wdo_price=5800,
        rho=-0.75,
        gate=_gate(),
        hmm_state="CHOP",
        hour=11,
        minute=0,
    )

    assert result["action"] == "BUY_WIN"
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status, strategy, live, mt5_ticket_in, mt5_ticket_out, mt5_magic "
        "FROM matador_ops"
    ).fetchone()
    conn.close()

    assert row == ("OPEN", "CONS_BASE", 0, None, None, None)


def test_open_trade_live_persists_ticket_magic_and_fill_price(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    engine = TradeEngine(str(db_path))

    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(
        te,
        "send_market_order",
        lambda *args, **kwargs: {
            "ok": True,
            "ticket": 111222,
            "retcode": 10009,
            "message": "done",
            "price": 130025.0,
        },
    )

    result = engine.evaluate(
        z_wdo=-2.1,
        z_di=-1.5,
        win_price=130000,
        wdo_price=5800,
        rho=-0.75,
        gate=_gate(),
        hmm_state="CHOP",
        hour=11,
        minute=0,
    )

    assert result["action"] == "BUY_WIN"
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT live, mt5_ticket_in, mt5_magic, price_win_in FROM matador_ops"
    ).fetchone()
    conn.close()

    assert row == (1, 111222, MAGIC_BY_STRATEGY["CONS_BASE"], 130025.0)


def test_open_trade_live_failure_does_not_insert(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    engine = TradeEngine(str(db_path))

    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(
        te,
        "send_market_order",
        lambda *args, **kwargs: {
            "ok": False,
            "ticket": None,
            "retcode": 10004,
            "message": "requote",
            "price": None,
        },
    )

    result = engine.evaluate(
        z_wdo=-2.1,
        z_di=-1.5,
        win_price=130000,
        wdo_price=5800,
        rho=-0.75,
        gate=_gate(),
        hmm_state="CHOP",
        hour=11,
        minute=0,
    )

    assert result["action"] == "ORDER_FAILED"
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM matador_ops").fetchone()[0]
    conn.close()
    assert count == 0


def test_close_trade_live_success_updates_ticket_out_and_fill_pnl(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    engine = TradeEngine(str(db_path))

    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(
        te,
        "send_market_order",
        lambda *args, **kwargs: {
            "ok": True,
            "ticket": 111222,
            "retcode": 10009,
            "message": "done",
            "price": 130000.0,
        },
    )
    engine.evaluate(
        z_wdo=-2.1,
        z_di=-1.5,
        win_price=130000,
        wdo_price=5800,
        rho=-0.75,
        gate=_gate(),
        hmm_state="CHOP",
        hour=11,
        minute=0,
    )

    monkeypatch.setattr(
        te,
        "close_position_by_ticket",
        lambda ticket, magic, comment="": {
            "ok": True,
            "ticket": 222333,
            "retcode": 10009,
            "message": "done",
            "price": 129675.0,
        },
    )
    result = engine.evaluate(
        z_wdo=0.0,
        z_di=0.0,
        win_price=129700,
        wdo_price=5800,
        rho=-0.75,
        gate=_gate(),
        hmm_state="CHOP",
        hour=11,
        minute=5,
    )

    assert result["action"] == "CLOSE"
    assert result["pnl"] == -130.0
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT status, mt5_ticket_out, price_win_out, pnl_brl FROM matador_ops"
    ).fetchone()
    conn.close()
    assert row == ("CLOSED", 222333, 129675.0, -130.0)


def test_close_trade_live_failure_keeps_trade_open(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    engine = TradeEngine(str(db_path))

    monkeypatch.setattr(te, "LIVE_ORDERS", True)
    monkeypatch.setattr(
        te,
        "send_market_order",
        lambda *args, **kwargs: {
            "ok": True,
            "ticket": 111222,
            "retcode": 10009,
            "message": "done",
            "price": 130000.0,
        },
    )
    engine.evaluate(
        z_wdo=-2.1,
        z_di=-1.5,
        win_price=130000,
        wdo_price=5800,
        rho=-0.75,
        gate=_gate(),
        hmm_state="CHOP",
        hour=11,
        minute=0,
    )

    monkeypatch.setattr(
        te,
        "close_position_by_ticket",
        lambda ticket, magic, comment="": {
            "ok": False,
            "ticket": ticket,
            "retcode": 10006,
            "message": "timeout",
            "price": None,
        },
    )
    result = engine.evaluate(
        z_wdo=0.0,
        z_di=0.0,
        win_price=129700,
        wdo_price=5800,
        rho=-0.75,
        gate=_gate(),
        hmm_state="CHOP",
        hour=11,
        minute=5,
    )

    assert result["action"] == "CLOSE_FAILED"
    assert result["holding"] is True
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT status, mt5_ticket_out FROM matador_ops").fetchone()
    conn.close()
    assert row == ("OPEN", None)
