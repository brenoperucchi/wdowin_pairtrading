# trade_engine.py
"""
WIN×WDO Setup Matador v4 — Multi-Strategy Trade Engine
=====================================================
Portfolio with 3 independent strategy slots:
  1. CONS_BASE  — Consensus (WDO Kalman + DI Kalman, SEM filtro NWE)
  2. WDO_NWE    — WDO Kalman + NWE band proximity filter
  3. DI_NWE     — DI Kalman + NWE band proximity filter

Each slot manages its own position independently.
No orders are dispatched to MT5 — signal-only + paper tracking.
"""
import sqlite3
from datetime import datetime
from core.config import (
    Z_ENTRY, Z_ANOMALY, Z_ATTENTION,
    DI_Z_ENTRY, DI_Z_ATTENTION,
    CONS_WDO_ENTRY, CONS_DI_ENTRY, CONS_Z_ATTENTION, CONS_USE_NWE,
    WALL_MIN_PTS, WALL_SL_BUFFER, WALL_TP_BUFFER, WALL_MAX_SL, WALL_MIN_RR,
    COOLDOWN_BARS,
    BUY_SL, BUY_TP, BUY_BE_ACT, BUY_BE_LOCK,
    SELL_SL, SELL_TP, SELL_BE_ACT, SELL_BE_LOCK,
    WIN_CONTRACTS, WIN_PV,
    ENTRY_START_H, ENTRY_START_M, ENTRY_END_H, ENTRY_END_M,
    FORCE_CLOSE_H, FORCE_CLOSE_M,
    RHO_MIN,
    NWE_BAND_MULT,
)


STRATEGIES = ["CONS_BASE", "WDO_NWE", "DI_NWE"]


def calc_wall_tp_sl(direction: str, entry_px: float, walls: list,
                    min_pts: float = WALL_MIN_PTS,
                    sl_buf: float = WALL_SL_BUFFER,
                    tp_buf: float = WALL_TP_BUFFER) -> tuple[float, float, float, float]:
    """
    Compute dynamic Take Profit (at next GEX Wall - tp_buf, >= min_pts)
    and Stop Loss (hidden behind previous GEX Wall + sl_buf, >= min_pts).
    Returns: (tp_price, sl_price, tp_pts, sl_pts)
    """
    wall_prices = []
    if walls:
        for w in walls:
            if isinstance(w, dict) and w.get("price") is not None:
                wall_prices.append(float(w["price"]))
            elif isinstance(w, (int, float)):
                wall_prices.append(float(w))
        wall_prices = sorted(set(wall_prices))

    is_buy = (direction == "BUY" or direction == 1)
    if not wall_prices:
        tp_pts = max(min_pts, 400.0)
        sl_pts = max(min_pts, 200.0)
        tp_px = (entry_px + tp_pts) if is_buy else (entry_px - tp_pts)
        sl_px = (entry_px - sl_pts) if is_buy else (entry_px + sl_pts)
        return round(tp_px, 0), round(sl_px, 0), round(tp_pts, 0), round(sl_pts, 0)

    if is_buy:
        down_walls = [w for w in wall_prices if w <= entry_px]
        if down_walls:
            prev_wall = down_walls[-1]
            sl_pts = max(min_pts, (entry_px - prev_wall) + sl_buf)
        else:
            sl_pts = min_pts
        sl_px = entry_px - sl_pts

        up_walls = [w for w in wall_prices if (w - tp_buf) - entry_px >= min_pts]
        if up_walls:
            tp_px = up_walls[0] - tp_buf
            tp_pts = tp_px - entry_px
        else:
            tp_pts = max(min_pts * 2.0, 400.0)
            tp_px = entry_px + tp_pts
    else:
        up_walls = [w for w in wall_prices if w >= entry_px]
        if up_walls:
            prev_wall = up_walls[0]
            sl_pts = max(min_pts, (prev_wall - entry_px) + sl_buf)
        else:
            sl_pts = min_pts
        sl_px = entry_px + sl_pts

        down_walls = [w for w in reversed(wall_prices) if entry_px - (w + tp_buf) >= min_pts]
        if down_walls:
            tp_px = down_walls[0] + tp_buf
            tp_pts = entry_px - tp_px
        else:
            tp_pts = max(min_pts * 2.0, 400.0)
            tp_px = entry_px - tp_pts

    return round(tp_px, 0), round(sl_px, 0), round(tp_pts, 0), round(sl_pts, 0)



class TradeEngine:
    def __init__(self, db_path: str = "trades.db"):
        self.db_path = db_path
        self._last_close_ts = {s: 0.0 for s in STRATEGIES}
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        conn = self._connect()
        c = conn.cursor()
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
                hmm_state TEXT
            )
        ''')
        # Migration: add strategy and wall tp/sl columns if missing
        for col_sql in [
            "ALTER TABLE matador_ops ADD COLUMN strategy TEXT DEFAULT 'CONS_BASE'",
            "ALTER TABLE matador_ops ADD COLUMN tp_price REAL DEFAULT 0.0",
            "ALTER TABLE matador_ops ADD COLUMN sl_price REAL DEFAULT 0.0",
        ]:
            try:
                c.execute(col_sql)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()

    def _get_open_trades(self):
        """Returns dict of open trades keyed by strategy."""
        conn = self._connect()
        c = conn.cursor()
        c.execute(
            "SELECT id, direction, z_source, strategy, price_win_in, price_wdo_in, "
            "max_pts_favor, be_active, tp_price, sl_price FROM matador_ops WHERE status='OPEN'"
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
                "tp_price": row[8] or 0.0, "sl_price": row[9] or 0.0,
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
                 rho: float, beta_safe: bool, hmm_state: str,
                 hour: int, minute: int,
                 beta_value: float = 0.0,
                 nwe_is_up: bool = True,
                 nwe_upper: float = 0.0,
                 nwe_lower: float = 0.0,
                 bar_close_confirmed: bool = True,
                 walls: list = None) -> dict:
        """
        Main evaluation loop. Called every poll (~2.5s).
        Evaluates all 3 strategies independently and returns combined result.

        bar_close_confirmed: True only when the M5 bar has just closed.
            - Entries are ONLY evaluated on bar close (backtest parity).
            - Exits (SL/TP/BE/MeanReversion) are checked every poll tick.
        """
        open_trades = self._get_open_trades()
        results = {}

        for strat in STRATEGIES:
            trade = open_trades[strat]

            # ── Check exits for open trade (every tick) ──
            # Per-strategy lock: if this strategy already has a position, 
            # only check exits — never open a second trade for the same setup
            if trade is not None:
                results[strat] = self._check_exits(
                    trade, win_price, wdo_price, hour, minute, z_wdo, z_di, strat, walls=walls
                )
                continue

            # ── New entries: ONLY on confirmed bar close ──
            if not bar_close_confirmed:
                results[strat] = self._result("WAIT", strat)
                continue

            # ── Common pre-entry checks ──
            if abs(z_wdo) >= Z_ANOMALY or abs(z_di) >= Z_ANOMALY:
                results[strat] = self._result("ANOMALY", strat)
                continue

            if not self._in_session(hour, minute):
                results[strat] = self._result("WAIT", strat)
                continue

            if not beta_safe:
                results[strat] = self._result("WAIT", strat)
                continue

            # ── Cooldown check (4 M5 bars = 20 min after closing a trade) ──
            if (datetime.now().timestamp() - self._last_close_ts.get(strat, 0.0)) < (COOLDOWN_BARS * 300):
                results[strat] = self._result("WAIT", strat)
                continue

            # ── Strategy-specific entry logic ──
            if strat == "CONS_BASE":
                results[strat] = self._eval_consensus(
                    z_wdo, z_di, win_price, wdo_price, rho, beta_value, hmm_state,
                    nwe_is_up=nwe_is_up, nwe_upper=nwe_upper, nwe_lower=nwe_lower, walls=walls
                )
            elif strat == "WDO_NWE":
                results[strat] = self._eval_wdo_nwe(
                    z_wdo, win_price, wdo_price, rho, beta_value, hmm_state,
                    nwe_is_up, nwe_upper, nwe_lower, walls=walls
                )
            elif strat == "DI_NWE":
                results[strat] = self._eval_di_nwe(
                    z_di, win_price, wdo_price, rho, beta_value, hmm_state,
                    nwe_is_up, nwe_upper, nwe_lower, walls=walls
                )

        # Build combined response
        return self._build_portfolio_result(results)

    # ── Strategy evaluators ─────────────────────────────────────────────────

    def _eval_consensus(self, z_wdo, z_di, win_price, wdo_price, rho, beta, hmm,
                        nwe_is_up=True, nwe_upper=0.0, nwe_lower=0.0, walls=None):
        """Consensus: asymmetric WDO (1.6) + DI (2.2) confirmation (att 1.2) + NWE proximity."""
        sig_buy = (z_wdo <= -CONS_WDO_ENTRY and z_di <= -CONS_Z_ATTENTION) or \
                  (z_di <= -CONS_DI_ENTRY and z_wdo <= -CONS_Z_ATTENTION)
        sig_sell = (z_wdo >= CONS_WDO_ENTRY and z_di >= CONS_Z_ATTENTION) or \
                   (z_di >= CONS_DI_ENTRY and z_wdo >= CONS_Z_ATTENTION)

        if CONS_USE_NWE:
            band_width = nwe_upper - nwe_lower if (nwe_upper > 0 and nwe_lower > 0) else 1.0
            if band_width < 1e-10:
                band_width = 1.0
            if sig_buy:
                if nwe_is_up or (nwe_lower > 0 and win_price > nwe_lower + band_width * 0.15):
                    sig_buy = False
            if sig_sell:
                if (not nwe_is_up) or (nwe_upper > 0 and win_price < nwe_upper - band_width * 0.15):
                    sig_sell = False

        if sig_buy:
            return self._open_trade("BUY", "CONSENSO", z_wdo,
                                    win_price, wdo_price, rho, beta, hmm, "CONS_BASE", walls=walls)
        if sig_sell:
            return self._open_trade("SELL", "CONSENSO", z_wdo,
                                    win_price, wdo_price, rho, beta, hmm, "CONS_BASE", walls=walls)

        return self._result("WAIT", "CONS_BASE")


    def _eval_wdo_nwe(self, z_wdo, win_price, wdo_price, rho, beta, hmm,
                      nwe_is_up, nwe_upper, nwe_lower, walls=None):
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
                                    win_price, wdo_price, rho, beta, hmm, "WDO_NWE", walls=walls)
        if sig_sell:
            return self._open_trade("SELL", "WDO_KALMAN", z_wdo,
                                    win_price, wdo_price, rho, beta, hmm, "WDO_NWE", walls=walls)

        return self._result("WAIT", "WDO_NWE")

    def _eval_di_nwe(self, z_di, win_price, wdo_price, rho, beta, hmm,
                     nwe_is_up, nwe_upper, nwe_lower, walls=None):
        """DI Isolado + NWE adaptive band multiplier filter."""
        sig_buy = z_di <= -DI_Z_ENTRY
        sig_sell = z_di >= DI_Z_ENTRY

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
                                    win_price, wdo_price, rho, beta, hmm, "DI_NWE", walls=walls)
        if sig_sell:
            return self._open_trade("SELL", "DI_JOHANSEN", z_di,
                                    win_price, wdo_price, rho, beta, hmm, "DI_NWE", walls=walls)

        return self._result("WAIT", "DI_NWE")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _result(self, action, strategy):
        return {
            "action": action, "strategy": strategy,
            "open_trade": None, "exit_reason": None, "pnl": None,
        }

    def _open_trade(self, direction, z_source, z_val,
                     win_price, wdo_price, rho, beta, hmm_state, strategy, walls=None):
        tp_px, sl_px, tp_pts, sl_pts = calc_wall_tp_sl(direction, win_price, walls)
        # Validate Wall Risk:Reward and Max SL
        if sl_pts > WALL_MAX_SL or (tp_pts / max(sl_pts, 1.0)) < WALL_MIN_RR:
            return self._result("WAIT", strategy)

        conn = self._connect()
        c = conn.cursor()
        c.execute('''
            INSERT INTO matador_ops
            (timestamp_in, status, direction, z_in, z_source, strategy, rho_in, beta_in,
             qty_win, price_win_in, price_wdo_in, hmm_state, tp_price, sl_price)
            VALUES (?, 'OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (datetime.now().isoformat(), direction, z_val, z_source, strategy,
              rho, beta, WIN_CONTRACTS, win_price, wdo_price, hmm_state, tp_px, sl_px))
        conn.commit()
        trade_id = c.lastrowid
        conn.close()

        action = "BUY_WIN" if direction == "BUY" else "SELL_WIN"
        return {
            "action": action, "strategy": strategy,
            "open_trade": {"id": trade_id, "direction": direction,
                           "z_source": z_source, "price_win_in": win_price,
                           "tp_price": tp_px, "sl_price": sl_px,
                           "tp_pts": tp_pts, "sl_pts": sl_pts,
                           "strategy": strategy},
            "exit_reason": None, "pnl": None,
        }

    def _check_exits(self, trade, win_price, wdo_price, hour, minute, z_wdo, z_di, strategy, walls=None):
        is_buy = trade["direction"] == "BUY"
        entry_px = trade["price_win_in"]
        tp_px = trade.get("tp_price") or 0.0
        sl_px = trade.get("sl_price") or 0.0

        if tp_px > 0 and sl_px > 0:
            tp = abs(tp_px - entry_px)
            sl = abs(sl_px - entry_px)
        else:
            tp_px, sl_px, tp, sl = calc_wall_tp_sl(trade["direction"], entry_px, walls)

        be_act = BUY_BE_ACT if is_buy else SELL_BE_ACT
        be_lock = BUY_BE_LOCK if is_buy else SELL_BE_LOCK

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

        # Exit checks (Wall TP, Wall SL >= 200 pts, Breakeven, and Mean Reversion >= 200 pts)
        reason = None
        if pts_favor >= tp:
            reason = "TARGET"
        elif be_active and pts_favor <= be_lock:
            reason = "BE_STOP"
        elif not be_active and pts_favor <= -sl:
            reason = "STOP_LOSS"
        elif pts_favor >= WALL_MIN_PTS:
            # Z-Spread Mean Reversion exit once >= 200 pts profit is guaranteed
            if strategy == "WDO_NWE" and ((is_buy and z_wdo >= 0.2) or (not is_buy and z_wdo <= -0.2)):
                reason = "TARGET"
            elif strategy == "DI_NWE" and ((is_buy and z_di >= 0.2) or (not is_buy and z_di <= -0.2)):
                reason = "TARGET"
            elif strategy == "CONS_BASE" and ((is_buy and z_wdo >= 0.0 and z_di >= 0.0) or (not is_buy and z_wdo <= 0.0 and z_di <= 0.0)):
                reason = "TARGET"

        if self._is_force_close(hour, minute):
            reason = "FORCE_CLOSE"


        if reason:
            pnl = pts_favor * WIN_CONTRACTS * WIN_PV
            self._close_trade(trade["id"], reason, win_price, wdo_price, pnl)
            self._last_close_ts[strategy] = datetime.now().timestamp()
            return {
                "action": "CLOSE", "strategy": strategy,
                "open_trade": None, "exit_reason": reason,
                "pnl": round(pnl, 2),
            }

        return {
            "action": "HOLDING", "strategy": strategy,
            "open_trade": trade, "exit_reason": None, "pnl": None,
        }

    def _update_field(self, trade_id, field, value):
        if field not in ("max_pts_favor", "be_active"):
            raise ValueError(f"Campo inválido em _update_field: {field}")
        conn = self._connect()
        c = conn.cursor()
        c.execute(f"UPDATE matador_ops SET {field}=? WHERE id=?", (value, trade_id))
        conn.commit()
        conn.close()

    def _close_trade(self, trade_id, reason, win_out, wdo_out, pnl):
        conn = self._connect()
        c = conn.cursor()
        c.execute(
            "UPDATE matador_ops SET status='CLOSED', timestamp_out=?, "
            "exit_reason=?, price_win_out=?, price_wdo_out=?, pnl_brl=? WHERE id=?",
            (datetime.now().isoformat(), reason, win_out, wdo_out, pnl, trade_id)
        )
        conn.commit()
        conn.close()

    def _build_portfolio_result(self, results: dict) -> dict:
        """Combine all 3 strategy results into a unified response."""
        # Legacy compat: pick the most "active" action for the main field
        actions = [r["action"] for r in results.values()]
        main_action = "WAIT"
        for a in ["BUY_WIN", "SELL_WIN", "CLOSE"]:
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
        conn = self._connect()
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
