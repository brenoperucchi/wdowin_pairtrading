# trade_engine.py
"""
WIN×WDO Setup Matador v4 — Multi-Strategy Trade Engine
=====================================================
Portfolio with 3 independent strategy slots:
  1. CONS_BASE  — Consensus (WDO Kalman + DI Kalman, SEM filtro NWE)
  2. WDO_NWE    — WDO Kalman + NWE band proximity filter
  3. DI_NWE     — DI Kalman + NWE band proximity filter

Each slot manages its own position independently. Paper mode only persists
signals/trades locally; live mode dispatches WIN orders through MT5 helpers.
"""
import logging
import sqlite3
from datetime import datetime
from uuid import uuid4
from core.config import (
    Z_ENTRY, Z_ANOMALY, Z_ATTENTION,
    BUY_SL, BUY_TP, BUY_BE_ACT, BUY_BE_LOCK,
    SELL_SL, SELL_TP, SELL_BE_ACT, SELL_BE_LOCK,
    WIN_CONTRACTS, WIN_PV,
    ENTRY_START_H, ENTRY_START_M, ENTRY_END_H, ENTRY_END_M,
    FORCE_CLOSE_H, FORCE_CLOSE_M,
    RHO_MIN,
    NWE_BAND_MULT,
    LIVE_ORDERS, LIVE_SYMBOL_WIN, LIVE_DEVIATION, MAGIC_BY_STRATEGY,
)
from core.execution_timeline import init_timeline_table, record_event
from core.risk_gate import operational_checks, WITHIN_POLL_OP_REASONS

STRATEGIES = ["CONS_BASE", "WDO_NWE", "DI_NWE"]

logger = logging.getLogger(__name__)


def send_market_order(*args, **kwargs):
    """Lazy MT5 import so paper-mode TradeEngine stays importable on Linux/CI."""
    from core.mt5_client import send_market_order as _send_market_order
    return _send_market_order(*args, **kwargs)


def close_position_by_ticket(*args, **kwargs):
    """Lazy MT5 import so paper-mode TradeEngine stays importable on Linux/CI."""
    from core.mt5_client import close_position_by_ticket as _close_position_by_ticket
    return _close_position_by_ticket(*args, **kwargs)


class TradeEngine:
    def __init__(self, db_path: str = "trades.db"):
        self.db_path = db_path
        self._last_gate_block_log: dict[str, tuple[str, tuple[str, ...]]] = {}
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute('''
            CREATE TABLE IF NOT EXISTS matador_ops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_in DATETIME,
                status TEXT,
                direction TEXT,
                z_in REAL,
                z_source TEXT,
                strategy TEXT DEFAULT 'CONS_BASE',
                rho_in REAL,
                beta_in REAL,
                qty_win INTEGER,
                price_win_in REAL,
                price_wdo_in REAL,
                timestamp_out DATETIME,
                exit_reason TEXT,
                price_win_out REAL,
                price_wdo_out REAL,
                pnl_brl REAL,
                max_pts_favor REAL DEFAULT 0.0,
                be_active INTEGER DEFAULT 0,
                hmm_state TEXT,
                mt5_ticket_in INTEGER,
                mt5_ticket_out INTEGER,
                mt5_magic INTEGER,
                live INTEGER DEFAULT 0
            )
        ''')
        migrations = [
            ("strategy", "TEXT DEFAULT 'CONS_BASE'"),
            ("mt5_ticket_in", "INTEGER"),
            ("mt5_ticket_out", "INTEGER"),
            ("mt5_magic", "INTEGER"),
            ("live", "INTEGER DEFAULT 0"),
        ]
        for column, ddl in migrations:
            try:
                c.execute(f"ALTER TABLE matador_ops ADD COLUMN {column} {ddl}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        conn.commit()
        conn.close()
        init_timeline_table(self.db_path)

    def _get_open_trades(self):
        """Returns dict of open trades keyed by strategy."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "SELECT id, direction, z_source, strategy, price_win_in, price_wdo_in, "
            "max_pts_favor, be_active, mt5_ticket_in, mt5_magic, live "
            "FROM matador_ops WHERE status='OPEN'"
        )
        rows = c.fetchall()
        conn.close()

        result = {s: None for s in STRATEGIES}
        for row in rows:
            strat = row[3] or "CONS_BASE"
            result[strat] = {
                "id": row[0], "direction": row[1], "z_source": row[2],
                "strategy": strat,
                "price_win_in": row[4], "price_wdo_in": row[5],
                "max_pts_favor": row[6], "be_active": bool(row[7]),
                "mt5_ticket_in": row[8], "mt5_magic": row[9],
                "live": bool(row[10] or 0),
            }
        return result

    def _in_session(self, hour, minute):
        t = hour * 60 + minute
        start = ENTRY_START_H * 60 + ENTRY_START_M
        end = ENTRY_END_H * 60 + ENTRY_END_M
        return start <= t <= end

    def _is_force_close(self, hour, minute):
        t = hour * 60 + minute
        fc = FORCE_CLOSE_H * 60 + FORCE_CLOSE_M
        return t >= fc

    def evaluate(self, z_wdo: float, z_di: float,
                 win_price: float, wdo_price: float,
                 rho: float, gate: dict, hmm_state: str,
                 hour: int, minute: int,
                 beta_value: float = 0.0,
                 nwe_is_up: bool = True,
                 nwe_upper: float = 0.0,
                 nwe_lower: float = 0.0,
                 closed_bar_ts: int | None = None,
                 entry_win_price: float | None = None,
                 entry_wdo_price: float | None = None,
                 now_dt: datetime | None = None) -> dict:
        """
        Main evaluation loop. Called every poll (~2.5s).
        Evaluates all 3 strategies independently and returns combined result.

        ``gate`` is the dict returned by ``core.risk_gate.risk_gate(...)``. It
        consolidates bar-close, session, rho, beta-drift, z-anomaly and
        Engle-Granger checks. Operational portions of the gate
        (MAX_TRADES_REACHED, DAILY_LOSS_LIMIT, LOSS_COOLDOWN) are
        **recomputed inside this method** because exits processed during this
        same poll change those stats — without recomputing, a STOP_LOSS in
        slot A would leave slot B free to bypass LOSS_COOLDOWN within the
        same evaluate() call. MT5_DISCONNECTED stays in the input gate (it
        doesn't change mid-poll).

        ``hmm_state`` is recorded on opened trades for postmortem; it does
        not gate entries (informational only — TASK-3 AC #4 decision).

        ``entry_win_price`` / ``entry_wdo_price`` let the server evaluate and
        persist entries against the confirmed closed bar while still using
        live prices above for intra-bar SL/TP exit checks.

        ``now_dt`` defaults to wall-clock time for live operation. Replay
        passes the closed bar timestamp here so daily limits, cooldown, and
        persisted trade timestamps follow the replayed session clock.
        """
        entry_win_price = win_price if entry_win_price is None else entry_win_price
        entry_wdo_price = wdo_price if entry_wdo_price is None else entry_wdo_price
        now_dt = now_dt or datetime.now()

        open_trades = self._get_open_trades()
        results: dict = {}
        # Market-side reasons that do NOT change within a single poll.
        # Within-poll operational reasons get recomputed in phase 2 below.
        market_reasons = [
            r for r in gate.get("reasons", [])
            if r not in WITHIN_POLL_OP_REASONS
        ]

        # ── Phase 1: exits for slots with open trades ─────────────────────
        for strat in STRATEGIES:
            trade = open_trades[strat]
            if trade is not None:
                results[strat] = self._check_exits(
                    trade, win_price, wdo_price, hour, minute, z_wdo, z_di, strat,
                    closed_bar_ts, now_dt
                )

        # ── Refresh operational stats post-exits (within-poll consistency) ─
        # If phase 1 just stop-lossed a trade, the next slot's entry attempt
        # MUST see LOSS_COOLDOWN active. count/pnl/cooldown are queried fresh
        # against the just-committed db state.
        today_str = now_dt.strftime("%Y-%m-%d")
        trades_today_now = self.count_trades_today(today_str)
        daily_pnl_now = self.pnl_today(today_str)
        minutes_since_loss_now = self.minutes_since_last_loss(now=now_dt)

        # ── Phase 2: entries for slots without open trades ────────────────
        # `opens_this_poll` decrements the trade budget per actual open so
        # multiple slots firing in the same poll cannot bust MAX_TRADES.
        opens_this_poll = 0
        for strat in STRATEGIES:
            if strat in results:
                continue  # phase 1 already produced a result for this slot

            ops_reasons, _ = operational_checks(
                trades_today_count=trades_today_now + opens_this_poll,
                daily_pnl_brl=daily_pnl_now,
                minutes_since_last_loss=minutes_since_loss_now,
                # MT5 connection doesn't change within a poll — its block,
                # if any, is already in market_reasons via the input gate.
                mt5_connected=True,
            )
            all_reasons = market_reasons + ops_reasons
            if all_reasons:
                action = "ANOMALY" if "Z_ANOMALY" in all_reasons else "WAIT"
                # BAR_NOT_CLOSED and OUT_OF_SESSION fire on every poll tick
                # while the M5 bar is still forming — suppress them to avoid
                # filling the log with 3 identical lines per 2.5-second cycle.
                _POLLING_REASONS = {"BAR_NOT_CLOSED", "OUT_OF_SESSION"}
                log_key = (action, tuple(all_reasons))
                if (
                    not _POLLING_REASONS.issuperset(all_reasons)
                    and self._last_gate_block_log.get(strat) != log_key
                ):
                    logger.info(
                        "gate_block strategy=%s action=%s reasons=%s",
                        strat, action, all_reasons,
                    )
                    self._last_gate_block_log[strat] = log_key
                results[strat] = self._result(action, strat, gate_reasons=all_reasons)
                continue
            self._last_gate_block_log.pop(strat, None)

            # ── Strategy-specific entry logic ──
            if strat == "CONS_BASE":
                res = self._eval_consensus(
                    z_wdo, z_di, entry_win_price, entry_wdo_price, rho, beta_value,
                    hmm_state, closed_bar_ts, now_dt
                )
            elif strat == "WDO_NWE":
                res = self._eval_wdo_nwe(
                    z_wdo, entry_win_price, entry_wdo_price, rho, beta_value, hmm_state,
                    nwe_is_up, nwe_upper, nwe_lower, closed_bar_ts, now_dt
                )
            elif strat == "DI_NWE":
                res = self._eval_di_nwe(
                    z_di, entry_win_price, entry_wdo_price, rho, beta_value, hmm_state,
                    nwe_is_up, nwe_upper, nwe_lower, closed_bar_ts, now_dt
                )
            results[strat] = res
            if res.get("open_trade") is not None:
                opens_this_poll += 1

        # Build combined response
        return self._build_portfolio_result(results)

    # ── Strategy evaluators ─────────────────────────────────────────────────

    def _eval_consensus(self, z_wdo, z_di, win_price, wdo_price, rho, beta, hmm,
                        closed_bar_ts=None, now_dt=None):
        """Consensus: requires BOTH z-scores to confirm."""
        # BUY
        if (z_wdo <= -Z_ENTRY and z_di <= -Z_ATTENTION) or \
           (z_wdo <= -Z_ATTENTION and z_di <= -Z_ENTRY):
            return self._open_trade("BUY", "CONSENSO", z_wdo,
                                    win_price, wdo_price, rho, beta, hmm, "CONS_BASE",
                                    closed_bar_ts, now_dt)
        # SELL
        if (z_wdo >= Z_ENTRY and z_di >= Z_ATTENTION) or \
           (z_wdo >= Z_ATTENTION and z_di >= Z_ENTRY):
            return self._open_trade("SELL", "CONSENSO", z_wdo,
                                    win_price, wdo_price, rho, beta, hmm, "CONS_BASE",
                                    closed_bar_ts, now_dt)

        return self._result("WAIT", "CONS_BASE")

    def _eval_wdo_nwe(self, z_wdo, win_price, wdo_price, rho, beta, hmm,
                      nwe_is_up, nwe_upper, nwe_lower, closed_bar_ts=None,
                      now_dt=None):
        """WDO Isolado + NWE adaptive band multiplier filter."""
        sig_buy = z_wdo <= -Z_ENTRY
        sig_sell = z_wdo >= Z_ENTRY

        # NWE filter: contra-tendência + adaptive proximity
        band_width = nwe_upper - nwe_lower if (nwe_upper > 0 and nwe_lower > 0) else 0
        if band_width < 1e-10:
            band_width = 1.0

        if sig_buy:
            if nwe_is_up:
                sig_buy = False  # NWE bullish → don't buy (already trending up)
            elif nwe_lower > 0:
                if win_price > nwe_lower + band_width * NWE_BAND_MULT:
                    sig_buy = False  # Too far from lower band

        if sig_sell:
            if not nwe_is_up:
                sig_sell = False  # NWE bearish → don't sell (already trending down)
            elif nwe_upper > 0:
                if win_price < nwe_upper - band_width * NWE_BAND_MULT:
                    sig_sell = False  # Too far from upper band

        if sig_buy:
            return self._open_trade("BUY", "WDO_KALMAN", z_wdo,
                                    win_price, wdo_price, rho, beta, hmm, "WDO_NWE",
                                    closed_bar_ts, now_dt)
        if sig_sell:
            return self._open_trade("SELL", "WDO_KALMAN", z_wdo,
                                    win_price, wdo_price, rho, beta, hmm, "WDO_NWE",
                                    closed_bar_ts, now_dt)

        return self._result("WAIT", "WDO_NWE")

    def _eval_di_nwe(self, z_di, win_price, wdo_price, rho, beta, hmm,
                     nwe_is_up, nwe_upper, nwe_lower, closed_bar_ts=None,
                     now_dt=None):
        """DI Isolado + NWE adaptive band multiplier filter."""
        sig_buy = z_di <= -Z_ENTRY
        sig_sell = z_di >= Z_ENTRY

        # NWE filter: contra-tendência + adaptive proximity
        band_width = nwe_upper - nwe_lower if (nwe_upper > 0 and nwe_lower > 0) else 0
        if band_width < 1e-10:
            band_width = 1.0

        if sig_buy:
            if nwe_is_up:
                sig_buy = False
            elif nwe_lower > 0:
                if win_price > nwe_lower + band_width * NWE_BAND_MULT:
                    sig_buy = False

        if sig_sell:
            if not nwe_is_up:
                sig_sell = False
            elif nwe_upper > 0:
                if win_price < nwe_upper - band_width * NWE_BAND_MULT:
                    sig_sell = False

        if sig_buy:
            return self._open_trade("BUY", "DI_JOHANSEN", z_di,
                                    win_price, wdo_price, rho, beta, hmm, "DI_NWE",
                                    closed_bar_ts, now_dt)
        if sig_sell:
            return self._open_trade("SELL", "DI_JOHANSEN", z_di,
                                    win_price, wdo_price, rho, beta, hmm, "DI_NWE",
                                    closed_bar_ts, now_dt)

        return self._result("WAIT", "DI_NWE")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _result(self, action, strategy, gate_reasons=None):
        return {
            "action": action, "strategy": strategy,
            "open_trade": None, "exit_reason": None, "pnl": None,
            "gate_reasons": list(gate_reasons) if gate_reasons else [],
        }

    def _emit_timeline_event(self, **fields):
        try:
            return record_event(self.db_path, **fields)
        except Exception:
            logger.exception(
                "timeline_emit_failed phase=%s event=%s strategy=%s",
                fields.get("phase"), fields.get("event"), fields.get("strategy"),
            )
            return None

    @staticmethod
    def _event_corr_attempt(attempt_id):
        return f"attempt:{attempt_id}"

    @staticmethod
    def _event_corr_trade(trade_id):
        return f"trade:{trade_id}"

    def _open_trade(self, direction, z_source, z_val,
                     win_price, wdo_price, rho, beta, hmm_state, strategy,
                     closed_bar_ts=None, now_dt=None):
        now_dt = now_dt or datetime.now()
        attempt_id = uuid4().hex
        entry_price = win_price
        mt5_ticket_in = None
        mt5_magic = None
        live = 0
        action = "BUY_WIN" if direction == "BUY" else "SELL_WIN"
        correlation_id = self._event_corr_attempt(attempt_id)

        self._emit_timeline_event(
            timestamp=now_dt.isoformat(timespec="seconds"),
            closed_bar_ts=closed_bar_ts,
            correlation_id=correlation_id,
            attempt_id=attempt_id,
            dedupe_key=f"{correlation_id}:SIGNAL:{action}",
            phase="SIGNAL",
            event=action,
            status="OK",
            severity="info",
            strategy=strategy,
            symbol=LIVE_SYMBOL_WIN,
            metric="abs_z_score",
            value=abs(z_val),
            threshold=Z_ENTRY,
            operator=">=",
            message=f"{strategy} entry signal {action}",
            payload_json={
                "direction": direction,
                "z_source": z_source,
                "z_value": z_val,
                "rho": rho,
                "beta": beta,
                "hmm_state": hmm_state,
                "win_price": win_price,
                "wdo_price": wdo_price,
                "qty_win": WIN_CONTRACTS,
            },
        )

        if LIVE_ORDERS:
            mt5_magic = MAGIC_BY_STRATEGY[strategy]
            order_request = {
                "symbol": LIVE_SYMBOL_WIN,
                "side": direction,
                "volume": WIN_CONTRACTS,
                "magic": mt5_magic,
                "deviation": LIVE_DEVIATION,
                "comment": f"{strategy}/{z_source}",
            }
            self._emit_timeline_event(
                timestamp=now_dt.isoformat(timespec="seconds"),
                closed_bar_ts=closed_bar_ts,
                correlation_id=correlation_id,
                attempt_id=attempt_id,
                dedupe_key=f"{correlation_id}:ORDER:ORDER_REQUEST",
                phase="ORDER",
                event="ORDER_REQUEST",
                status="OK",
                severity="info",
                strategy=strategy,
                symbol=LIVE_SYMBOL_WIN,
                message=f"{strategy} MT5 order request",
                payload_json=order_request,
            )
            order = send_market_order(
                order_request["symbol"],
                order_request["side"],
                order_request["volume"],
                magic=order_request["magic"],
                deviation=order_request["deviation"],
                comment=order_request["comment"],
            )
            if not order.get("ok"):
                self._emit_timeline_event(
                    timestamp=now_dt.isoformat(timespec="seconds"),
                    closed_bar_ts=closed_bar_ts,
                    correlation_id=correlation_id,
                    attempt_id=attempt_id,
                    dedupe_key=f"{correlation_id}:EXECUTION:EXECUTION_REJECTED",
                    phase="EXECUTION",
                    event="EXECUTION_REJECTED",
                    status="FAILED",
                    severity="operational_block",
                    strategy=strategy,
                    symbol=LIVE_SYMBOL_WIN,
                    message=f"{strategy} MT5 order rejected",
                    payload_json={
                        "ticket": order.get("ticket"),
                        "price": order.get("price"),
                        "retcode": order.get("retcode"),
                        "message": order.get("message"),
                    },
                )
                logger.error(
                    "order_open_failed strategy=%s direction=%s retcode=%s message=%s",
                    strategy, direction, order.get("retcode"), order.get("message"),
                )
                return self._result(
                    "ORDER_FAILED",
                    strategy,
                    gate_reasons=[f"ORDER_SEND_FAILED:{order.get('message')}"],
                )
            self._emit_timeline_event(
                timestamp=now_dt.isoformat(timespec="seconds"),
                closed_bar_ts=closed_bar_ts,
                correlation_id=correlation_id,
                attempt_id=attempt_id,
                dedupe_key=f"{correlation_id}:EXECUTION:EXECUTION_FILLED",
                phase="EXECUTION",
                event="EXECUTION_FILLED",
                status="OK",
                severity="info",
                strategy=strategy,
                symbol=LIVE_SYMBOL_WIN,
                message=f"{strategy} MT5 order filled",
                payload_json={
                    "ticket": order.get("ticket"),
                    "price": order.get("price"),
                    "retcode": order.get("retcode"),
                    "message": order.get("message"),
                },
            )
            mt5_ticket_in = order.get("ticket")
            entry_price = order.get("price") or win_price
            live = 1

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT INTO matador_ops
            (timestamp_in, status, direction, z_in, z_source, strategy, rho_in, beta_in,
             qty_win, price_win_in, price_wdo_in, hmm_state, mt5_ticket_in, mt5_magic, live)
            VALUES (?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (now_dt.isoformat(), direction, z_val, z_source, strategy,
              rho, beta, WIN_CONTRACTS, entry_price, wdo_price, hmm_state,
              mt5_ticket_in, mt5_magic, live))
        conn.commit()
        trade_id = c.lastrowid
        conn.close()

        return {
            "action": action, "strategy": strategy,
            "open_trade": {"id": trade_id, "direction": direction,
                           "z_source": z_source, "price_win_in": entry_price,
                           "strategy": strategy, "mt5_ticket_in": mt5_ticket_in,
                           "live": bool(live), "attempt_id": attempt_id},
            "exit_reason": None, "pnl": None,
        }

    def _check_exits(
        self, trade, win_price, wdo_price, hour, minute, z_wdo, z_di,
        strategy, closed_bar_ts=None, now_dt=None,
    ):
        now_dt = now_dt or datetime.now()
        is_buy = trade["direction"] == "BUY"
        sl = BUY_SL if is_buy else SELL_SL
        tp = BUY_TP if is_buy else SELL_TP
        be_act = BUY_BE_ACT if is_buy else SELL_BE_ACT
        be_lock = BUY_BE_LOCK if is_buy else SELL_BE_LOCK

        entry_px = trade["price_win_in"]
        pts_favor = (win_price - entry_px) if is_buy else (entry_px - win_price)

        max_favor = trade["max_pts_favor"]
        be_active = trade["be_active"]

        # Update max favor
        if pts_favor > max_favor:
            max_favor = pts_favor
            self._update_field(trade["id"], "max_pts_favor", max_favor)

        # BE activation
        if not be_active and max_favor >= be_act:
            be_active = True
            self._update_field(trade["id"], "be_active", 1)

        # Exit checks
        reason = None
        if pts_favor >= tp:
            reason = "TARGET"
        elif be_active and pts_favor <= be_lock:
            reason = "BE_STOP"
        elif not be_active and pts_favor <= -sl:
            reason = "STOP_LOSS"

        if self._is_force_close(hour, minute):
            reason = "FORCE_CLOSE"

        if reason:
            pnl = pts_favor * WIN_CONTRACTS * WIN_PV
            close_result = self._close_trade(trade, reason, win_price, wdo_price, pnl, now_dt)
            trade_id = trade["id"]
            correlation_id = self._event_corr_trade(trade_id)
            exit_status = "OK" if close_result["ok"] else "FAILED"
            exit_severity = "info" if close_result["ok"] else "operational_block"
            self._emit_timeline_event(
                timestamp=now_dt.isoformat(timespec="seconds"),
                closed_bar_ts=closed_bar_ts,
                correlation_id=correlation_id,
                dedupe_key=f"{correlation_id}:EXIT:{reason}:{exit_status}",
                trade_id=trade_id,
                phase="EXIT",
                event=reason,
                status=exit_status,
                severity=exit_severity,
                strategy=strategy,
                symbol=LIVE_SYMBOL_WIN,
                message=f"{strategy} exit trigger {reason}",
                payload_json={
                    "reason": reason,
                    "direction": trade["direction"],
                    "price_win_in": trade["price_win_in"],
                    "price_win_out": close_result.get("price_win_out", win_price),
                    "price_wdo_out": wdo_price,
                    "pts_favor": pts_favor,
                    "pnl_brl": close_result.get("pnl"),
                    "live": bool(trade.get("live")),
                    "mt5_ticket_in": trade.get("mt5_ticket_in"),
                    "mt5_ticket_out": close_result.get("mt5_ticket_out"),
                    "retcode": close_result.get("retcode"),
                    "message": close_result.get("message"),
                },
            )
            if not close_result["ok"]:
                failure_minute = now_dt.strftime("%Y%m%d%H%M")
                self._emit_timeline_event(
                    timestamp=now_dt.isoformat(timespec="seconds"),
                    closed_bar_ts=closed_bar_ts,
                    correlation_id=correlation_id,
                    dedupe_key=f"{correlation_id}:EXIT:CLOSE_FAILED:{reason}:{failure_minute}",
                    trade_id=trade_id,
                    phase="EXIT",
                    event="CLOSE_FAILED",
                    status="FAILED",
                    severity="operational_block",
                    strategy=strategy,
                    symbol=LIVE_SYMBOL_WIN,
                    message=f"{strategy} close order failed",
                    payload_json={
                        "reason": reason,
                        "ticket": close_result.get("ticket"),
                        "retcode": close_result.get("retcode"),
                        "message": close_result.get("message"),
                    },
                )
                return {
                    "action": "CLOSE_FAILED", "strategy": strategy,
                    "open_trade": trade, "exit_reason": reason,
                    "pnl": None,
                }
            return {
                "action": "CLOSE", "strategy": strategy,
                "open_trade": None, "exit_reason": reason,
                "pnl": close_result["pnl"],
            }

        return {
            "action": "HOLDING", "strategy": strategy,
            "open_trade": trade, "exit_reason": None, "pnl": None,
        }

    def _update_field(self, trade_id, field, value):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(f"UPDATE matador_ops SET {field}=? WHERE id=?", (value, trade_id))
        conn.commit()
        conn.close()

    def _close_trade(self, trade, reason, win_out, wdo_out, pnl, now_dt=None):
        now_dt = now_dt or datetime.now()
        trade_id = trade["id"]
        price_win_out = win_out
        realized_pnl = pnl
        mt5_ticket_out = None

        if LIVE_ORDERS and trade.get("live"):
            mt5_ticket_in = trade.get("mt5_ticket_in")
            mt5_magic = trade.get("mt5_magic") or MAGIC_BY_STRATEGY.get(trade["strategy"])
            if not mt5_ticket_in:
                logger.error("order_close_missing_ticket trade_id=%s strategy=%s", trade_id, trade["strategy"])
                return {
                    "ok": False,
                    "pnl": None,
                    "ticket": None,
                    "retcode": None,
                    "message": "MISSING_MT5_TICKET",
                    "price_win_out": win_out,
                    "mt5_ticket_out": None,
                }

            order = close_position_by_ticket(mt5_ticket_in, mt5_magic, comment=reason)
            if not order.get("ok"):
                logger.error(
                    "order_close_failed trade_id=%s ticket=%s retcode=%s message=%s",
                    trade_id, mt5_ticket_in, order.get("retcode"), order.get("message"),
                )
                return {
                    "ok": False,
                    "pnl": None,
                    "ticket": order.get("ticket"),
                    "retcode": order.get("retcode"),
                    "message": order.get("message"),
                    "price_win_out": win_out,
                    "mt5_ticket_out": None,
                }

            price_win_out = order.get("price") or win_out
            mt5_ticket_out = order.get("ticket")
            is_buy = trade["direction"] == "BUY"
            pts_favor = (
                price_win_out - trade["price_win_in"]
                if is_buy else trade["price_win_in"] - price_win_out
            )
            realized_pnl = pts_favor * WIN_CONTRACTS * WIN_PV

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute(
            "UPDATE matador_ops SET status='CLOSED', timestamp_out=?, "
            "exit_reason=?, price_win_out=?, price_wdo_out=?, pnl_brl=?, "
            "mt5_ticket_out=? WHERE id=?",
            (
                now_dt.isoformat(), reason, price_win_out, wdo_out,
                realized_pnl, mt5_ticket_out, trade_id,
            )
        )
        conn.commit()
        conn.close()
        return {
            "ok": True,
            "pnl": round(realized_pnl, 2),
            "message": "OK",
            "retcode": order.get("retcode") if LIVE_ORDERS and trade.get("live") else None,
            "ticket": mt5_ticket_out,
            "price_win_out": price_win_out,
            "mt5_ticket_out": mt5_ticket_out,
        }

    def _build_portfolio_result(self, results: dict) -> dict:
        """Combine all 3 strategy results into a unified response."""
        # Legacy compat: pick the most "active" action for the main field
        actions = [r["action"] for r in results.values()]
        main_action = "WAIT"
        for a in ["BUY_WIN", "SELL_WIN", "CLOSE", "ORDER_FAILED", "CLOSE_FAILED"]:
            if a in actions:
                main_action = a
                break
        if main_action == "WAIT":
            for a in ["HOLDING", "ANOMALY", "HMM_BLOCKED"]:
                if a in actions:
                    main_action = a
                    break

        # Any open trade?
        any_holding = any(r.get("open_trade") is not None for r in results.values())

        return {
            "action": main_action,
            "holding": any_holding,
            "exit_reason": next((r["exit_reason"] for r in results.values() if r.get("exit_reason")), None),
            "pnl": next((r["pnl"] for r in results.values() if r.get("pnl") is not None), None),
            "strategies": results,
        }

    # ── Trades for date ─────────────────────────────────────────────────────

    def get_trades_for_date(self, date_str: str) -> list:
        """Return all trades (OPEN and CLOSED) for the given date (YYYY-MM-DD)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, strategy, direction, "
            "timestamp_in, "
            "strftime('%H:%M:%S', timestamp_in) as time_in, "
            "timestamp_out, "
            "strftime('%H:%M:%S', timestamp_out) as time_out, "
            "z_in, price_win_in, price_win_out, pnl_brl, exit_reason, status "
            "FROM matador_ops "
            "WHERE date(timestamp_in) = ? "
            "ORDER BY timestamp_in",
            (date_str,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Operational risk stats (TASK-3 AC #11) ──────────────────────────────

    def count_trades_today(self, date_str: str) -> int:
        """Count trades opened today (OPEN + CLOSED). Used by MAX_TRADES gate."""
        conn = sqlite3.connect(self.db_path)
        n = conn.execute(
            "SELECT COUNT(*) FROM matador_ops WHERE date(timestamp_in) = ?",
            (date_str,)
        ).fetchone()[0]
        conn.close()
        return int(n)

    def pnl_today(self, date_str: str) -> float:
        """Sum of pnl_brl for trades CLOSED today. Used by DAILY_LOSS gate.

        Uses `timestamp_out` (close time), not `timestamp_in`, because a
        trade opened yesterday but closed today should count toward today's
        loss budget — the realized P&L belongs to the day it printed.
        """
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl_brl), 0.0) FROM matador_ops "
            "WHERE status='CLOSED' AND date(timestamp_out) = ?",
            (date_str,)
        ).fetchone()
        conn.close()
        return float(row[0] or 0.0)

    def minutes_since_last_loss(self, now: datetime | None = None):
        """Minutes since the most recent STOP_LOSS exit. Returns None if
        there's no STOP_LOSS in history. Used by LOSS_COOLDOWN gate.
        """
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT timestamp_out FROM matador_ops "
            "WHERE status='CLOSED' AND exit_reason='STOP_LOSS' "
            "ORDER BY timestamp_out DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row or not row[0]:
            return None
        try:
            ts = datetime.fromisoformat(row[0])
        except Exception:
            return None
        ref = now or datetime.now()
        delta = ref - ts
        return delta.total_seconds() / 60.0

    # ── Performance API ─────────────────────────────────────────────────────

    @staticmethod
    def _fmt_datetime(raw):
        """Format a raw ISO datetime string to HH:MM:SS."""
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%H:%M:%S")
        except Exception:
            return str(raw)

    @staticmethod
    def _fmt_date(raw):
        """Extract date part (dd/mm) from an ISO datetime string."""
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%d/%m")
        except Exception:
            return None

    def get_performance(self, limit: int = 50) -> dict:
        """Return performance stats for the dashboard — grouped by strategy."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # Per-strategy stats
        strategy_stats = {}
        for strat in STRATEGIES:
            c.execute(
                "SELECT exit_reason, pnl_brl FROM matador_ops "
                "WHERE status='CLOSED' AND strategy=?", (strat,)
            )
            closed = c.fetchall()
            total = len(closed)
            wins = sum(1 for r, _ in closed if r == "TARGET")
            total_pnl = sum(p for _, p in closed if p is not None)
            win_rate = (wins / total * 100) if total > 0 else 0

            c.execute(
                "SELECT COUNT(*) FROM matador_ops WHERE status='OPEN' AND strategy=?",
                (strat,)
            )
            open_count = c.fetchone()[0]

            strategy_stats[strat] = {
                "total_closed": total,
                "open_trades": open_count,
                "wins": wins,
                "losses": total - wins,
                "win_rate_pct": round(win_rate, 1),
                "accumulated_pnl": round(total_pnl, 2),
            }

        # Portfolio totals
        c.execute("SELECT exit_reason, pnl_brl FROM matador_ops WHERE status='CLOSED'")
        all_closed = c.fetchall()
        total_all = len(all_closed)
        wins_all = sum(1 for r, _ in all_closed if r == "TARGET")
        pnl_all = sum(p for _, p in all_closed if p is not None)
        wr_all = (wins_all / total_all * 100) if total_all > 0 else 0

        c.execute("SELECT COUNT(*) FROM matador_ops WHERE status='OPEN'")
        open_all = c.fetchone()[0]

        # Recent trades (all strategies)
        c.execute(
            "SELECT id, timestamp_in, timestamp_out, status, direction, z_in, "
            "z_source, strategy, rho_in, qty_win, exit_reason, pnl_brl, hmm_state "
            "FROM matador_ops ORDER BY id DESC LIMIT ?", (limit,)
        )
        recent = c.fetchall()
        conn.close()

        trades_list = []
        for r in recent:
            trades_list.append({
                "id": r[0],
                "date_in": self._fmt_date(r[1]),
                "time_in": self._fmt_datetime(r[1]),
                "time_out": self._fmt_datetime(r[2]),
                "status": r[3],
                "direction": r[4],
                "z_in": round(r[5], 2) if r[5] else 0,
                "z_source": r[6] or "",
                "strategy": r[7] or "CONS_BASE",
                "rho_in": round(r[8], 2) if r[8] else 0,
                "qty_win": r[9],
                "exit_reason": r[10] or "-",
                "pnl_brl": round(r[11], 2) if r[11] is not None else 0.0,
                "hmm_state": r[12] or "",
            })

        return {
            "total_closed_trades": total_all,
            "open_trades": open_all,
            "win_rate_pct": round(wr_all, 1),
            "wins": wins_all,
            "losses": total_all - wins_all,
            "accumulated_pnl": round(pnl_all, 2),
            "strategies": strategy_stats,
            "trades": trades_list,
        }
