"""Synthetic live-execution smoke for WDOWIN.

This script forces one approved synthetic signal through the same execution
path used by production:

    risk_gate -> TradeEngine.evaluate -> _open_trade -> send_market_order

Safety contract:
  - default is --dry-run: no MT5 import, no terminal, no order_send
  - --live calls real MT5
  - --live requires --ack-live-risk

The expected off-session success case is receiving
TRADE_RETCODE_MARKET_CLOSED from MT5, proving that Python, terminal
initialization, symbol selection, order payload construction, and
mt5.order_send all executed.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

# Allow `python scripts/wdowin_live_execution_smoke.py ...` from repo root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import core.trade_engine as trade_engine_module  # noqa: E402
from core.config import (  # noqa: E402
    LIVE_DEVIATION,
    LIVE_MAGIC_BASE,
    LIVE_SYMBOL_WIN,
    MT5_PATH,
    MT5_PORTABLE,
    WIN_CONTRACTS,
)
from core.execution_timeline import load_timeline  # noqa: E402
from core.risk_gate import risk_gate  # noqa: E402
from core.trade_engine import TradeEngine  # noqa: E402


SCHEMA = "wdowin.live-execution-smoke.v1"
DEFAULT_REPORT_DIR = "reports/execution_smoke"
DEFAULT_AUDIT_DIR = "reports/execution_smoke"

RETCODE_NAMES = {
    10008: "TRADE_RETCODE_PLACED",
    10009: "TRADE_RETCODE_DONE",
    10013: "TRADE_RETCODE_INVALID",
    10014: "TRADE_RETCODE_INVALID_VOLUME",
    10018: "TRADE_RETCODE_MARKET_CLOSED",
}


@dataclass
class SmokeReport:
    schema: str = SCHEMA
    mode: str = "dry-run"
    classification: str = "unexpected_error"
    symbol: str | None = None
    side: str | None = None
    volume: float | None = None
    order_payload: dict = field(default_factory=dict)
    retcode: int | None = None
    retcode_name: str | None = None
    mt5_last_error: list | None = None
    raw_response: dict = field(default_factory=dict)
    terminal_path: str | None = None
    terminal_info: dict | None = None
    windows_python: str | None = None
    python_executable: str = sys.executable
    platform: str = platform.platform()
    symbol_info: dict | None = None
    symbol_tick: dict | None = None
    risk_gate: dict | None = None
    trade_result: dict | None = None
    report_file: str | None = None
    audit_path: str | None = None
    timeline_query: str | None = None
    timeline_events: list = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _safe_json_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(v) for v in value]
    return str(value)


def _obj_to_dict(obj) -> dict | None:
    if obj is None:
        return None
    if hasattr(obj, "_asdict"):
        return _safe_json_value(obj._asdict())
    if isinstance(obj, dict):
        return _safe_json_value(obj)
    return _safe_json_value(vars(obj)) if hasattr(obj, "__dict__") else {"value": str(obj)}


def _retcode_name(retcode: int | None) -> str | None:
    if retcode is None:
        return None
    return RETCODE_NAMES.get(int(retcode), f"RET_CODE_{retcode}")


def classify_result(
    *,
    mode: str,
    init_ok: bool,
    symbol_ok: bool,
    volume_ok: bool,
    retcode: int | None,
) -> str:
    if mode == "dry-run":
        return "dry_run_simulated"
    if not init_ok:
        return "connection_or_terminal_error"
    if not symbol_ok:
        return "invalid_symbol_or_contract"
    if not volume_ok or retcode == 10014:
        return "invalid_volume"
    if retcode == 10018:
        return "expected_market_closed"
    if retcode in {10008, 10009}:
        return "order_placed_or_filled"
    return "unexpected_error"


def _volume_ok(volume: float, symbol_info: dict | None) -> bool:
    if not symbol_info:
        return False
    try:
        vmin = float(symbol_info.get("volume_min") or 0.0)
        vmax = float(symbol_info.get("volume_max") or volume)
        step = float(symbol_info.get("volume_step") or 0.0)
        if volume < vmin or volume > vmax:
            return False
        if step <= 0:
            return True
        units = round((volume - vmin) / step)
        return abs((vmin + units * step) - volume) < 1e-9
    except Exception:
        return False


def _write_report(report: SmokeReport, report_dir: str) -> str:
    Path(report_dir).mkdir(parents=True, exist_ok=True)
    path = Path(report_dir) / f"wdowin_live_execution_smoke_{datetime.now():%Y%m%d-%H%M%S}.json"
    report.report_file = str(path)
    path.write_text(json.dumps(asdict(report), indent=2, sort_keys=True, default=str), encoding="utf-8")
    return str(path)


def _timeline_rows(db_path: str) -> list[dict]:
    rows = list(reversed(load_timeline(db_path, limit=50)))
    return [
        {
            "id": r.get("id"),
            "phase": r.get("phase"),
            "event": r.get("event"),
            "status": r.get("status"),
            "strategy": r.get("strategy"),
            "symbol": r.get("symbol"),
            "payload_json": r.get("payload_json"),
        }
        for r in rows
    ]


def _latest_timeline_payload(rows: list[dict], phase: str, event: str) -> dict:
    for row in rows:
        if row.get("phase") == phase and row.get("event") == event:
            raw = row.get("payload_json")
            return json.loads(raw) if raw else {}
    return {}


def _mt5_payload_from_project_request(project_request: dict, side: str, price: float = 0.0) -> dict:
    """Mirror core.mt5_client.send_market_order's MT5 request in report-friendly names."""
    if not project_request:
        return {}
    return {
        "symbol": project_request.get("symbol"),
        "action": "TRADE_ACTION_DEAL",
        "type": "ORDER_TYPE_BUY" if side == "BUY" else "ORDER_TYPE_SELL",
        "volume": float(project_request.get("volume") or 0.0),
        "price": float(price or 0.0),
        "deviation": int(project_request.get("deviation") or 0),
        "magic": project_request.get("magic"),
        "comment": project_request.get("comment"),
        "type_time": "ORDER_TIME_GTC",
        "type_filling": "ORDER_FILLING_RETURN",
        "project_order_request": project_request,
    }


def _approved_gate(side: str) -> tuple[dict, dict]:
    z = -2.1 if side == "BUY" else 2.1
    z_di = -1.5 if side == "BUY" else 1.5
    gate = risk_gate(
        z_wdo=z,
        z_di=z_di,
        rho_level=0,
        beta_delta_pct=0.0,
        eg_pvalue=0.01,
        hour=11,
        minute=0,
        bar_close_confirmed=True,
        trades_today_count=0,
        daily_pnl_brl=0.0,
        minutes_since_last_loss=None,
        mt5_connected=True,
        joh_open=True,
        hmm_state="SMOKE",
    )
    return gate, {"z_wdo": z, "z_di": z_di}


def _run_engine_smoke(
    *,
    db_path: str,
    symbol: str,
    side: str,
    volume: float,
    deviation: int,
    live: bool,
    dry_order_result: dict | None = None,
) -> dict:
    old = {
        "LIVE_ORDERS": trade_engine_module.LIVE_ORDERS,
        "LIVE_SYMBOL_WIN": trade_engine_module.LIVE_SYMBOL_WIN,
        "WIN_CONTRACTS": trade_engine_module.WIN_CONTRACTS,
        "LIVE_DEVIATION": trade_engine_module.LIVE_DEVIATION,
        "send_market_order": trade_engine_module.send_market_order,
    }
    try:
        trade_engine_module.LIVE_ORDERS = bool(live)
        trade_engine_module.LIVE_SYMBOL_WIN = symbol
        trade_engine_module.WIN_CONTRACTS = float(volume)
        trade_engine_module.LIVE_DEVIATION = int(deviation)
        if dry_order_result is not None:
            trade_engine_module.send_market_order = (
                lambda *_args, **_kwargs: dict(dry_order_result)
            )

        engine = TradeEngine(db_path)
        gate, z = _approved_gate(side)
        if not gate["allowed"]:
            return {"gate": gate, "result": {"action": "GATE_BLOCKED"}}

        # NWE values intentionally block the WDO_NWE/DI_NWE slots while leaving
        # CONS_BASE open, so the smoke emits exactly one order attempt.
        nwe_is_up = side == "BUY"
        result = engine.evaluate(
            z_wdo=z["z_wdo"],
            z_di=z["z_di"],
            win_price=130000.0,
            wdo_price=5500.0,
            rho=-0.85,
            gate=gate,
            hmm_state="SMOKE",
            hour=11,
            minute=0,
            beta_value=-22.5,
            nwe_is_up=nwe_is_up,
            nwe_upper=130800.0,
            nwe_lower=129200.0,
            closed_bar_ts=int(datetime.now().timestamp()),
            entry_win_price=130000.0,
            entry_wdo_price=5500.0,
            now_dt=datetime.now(),
        )
        return {"gate": gate, "result": result}
    finally:
        for key, value in old.items():
            setattr(trade_engine_module, key, value)


def _connect_and_probe_mt5(args, report: SmokeReport) -> tuple[bool, bool, bool]:
    try:
        import MetaTrader5 as mt5  # noqa: PLC0415
        import core.mt5_client as mt5_client  # noqa: PLC0415
    except Exception as exc:
        report.notes.append(f"MetaTrader5 import failed: {exc}")
        return False, False, False

    if args.mt5_path:
        mt5_client.MT5_PATH = args.mt5_path
    mt5_client.MT5_PORTABLE = bool(args.portable)

    if args.mt5_path and not os.path.exists(args.mt5_path):
        report.notes.append(f"terminal path missing: {args.mt5_path}")
        return False, False, False

    init_ok = mt5_client.connect_mt5()
    report.mt5_last_error = list(mt5.last_error()) if hasattr(mt5, "last_error") else None
    terminal_info = mt5.terminal_info() if init_ok else None
    report.terminal_info = _obj_to_dict(terminal_info)
    if not init_ok:
        return False, False, False

    mt5.symbol_select(args.symbol, True)
    info = mt5.symbol_info(args.symbol)
    tick = mt5.symbol_info_tick(args.symbol)
    report.symbol_info = _obj_to_dict(info)
    report.symbol_tick = _obj_to_dict(tick)
    report.mt5_last_error = list(mt5.last_error())

    symbol_ok = info is not None
    volume_ok = _volume_ok(args.volume, report.symbol_info)
    return True, symbol_ok, volume_ok


def _parse_order_result_from_timeline(rows: list[dict]) -> dict:
    payload = _latest_timeline_payload(rows, "EXECUTION", "EXECUTION_REJECTED")
    if payload:
        return payload
    payload = _latest_timeline_payload(rows, "EXECUTION", "EXECUTION_FILLED")
    return payload


def _wsl_to_windows_path(path: str) -> str:
    if path.startswith("/mnt/") and len(path) > 6:
        drive = path[5].upper()
        rest = path[7:].replace("/", "\\")
        return f"{drive}:\\{rest}"
    return path


def _maybe_reexec_windows(args: argparse.Namespace) -> int | None:
    if not args.live or args._windows_child or os.name == "nt":
        return None
    if not args.windows_python:
        return None

    cmd_exe = "/mnt/c/Windows/System32/cmd.exe"
    if not os.path.exists(cmd_exe):
        return None

    cwd_win = _wsl_to_windows_path(str(_REPO_ROOT))
    py_win = _wsl_to_windows_path(args.windows_python)
    original_args = [a for a in sys.argv[1:] if a != "--_windows-child"]
    child_args = original_args + ["--_windows-child"]
    py_cmd = subprocess.list2cmdline([py_win, "scripts\\wdowin_live_execution_smoke.py", *child_args])
    return subprocess.call([cmd_exe, "/C", f'cd /d "{cwd_win}" && {py_cmd}'])


def run_smoke(args: argparse.Namespace) -> tuple[int, SmokeReport]:
    mode = "live" if args.live else "dry-run"
    report = SmokeReport(
        mode=mode,
        symbol=args.symbol,
        side=args.side,
        volume=args.volume,
        terminal_path=args.mt5_path or MT5_PATH,
        windows_python=args.windows_python,
    )

    if args.live and not args.ack_live_risk:
        report.classification = "safety_abort"
        report.notes.append("--live requires --ack-live-risk")
        _write_report(report, args.report_dir)
        return 2, report

    if args.order_type != "market":
        report.classification = "unexpected_error"
        report.notes.append("WDOWIN live path currently supports market orders only")
        _write_report(report, args.report_dir)
        return 2, report

    Path(args.audit_dir).mkdir(parents=True, exist_ok=True)
    audit_path = Path(args.audit_dir) / f"wdowin_smoke_audit_{datetime.now():%Y%m%d-%H%M%S}.db"
    report.audit_path = str(audit_path)
    report.timeline_query = (
        f"sqlite3 {audit_path} "
        "\"SELECT phase,event,status,symbol,payload_json FROM execution_timeline ORDER BY id;\""
    )

    init_ok = True
    symbol_ok = True
    volume_ok = True
    dry_order_result = None

    if args.live:
        init_ok, symbol_ok, volume_ok = _connect_and_probe_mt5(args, report)
        if not (init_ok and symbol_ok and volume_ok):
            report.classification = classify_result(
                mode=mode,
                init_ok=init_ok,
                symbol_ok=symbol_ok,
                volume_ok=volume_ok,
                retcode=None,
            )
            _write_report(report, args.report_dir)
            return 1, report
    else:
        dry_order_result = {
            "ok": False,
            "ticket": None,
            "retcode": 10018,
            "message": "DRY_RUN_MARKET_CLOSED",
            "price": None,
        }
        report.mt5_last_error = [0, "DRY_RUN"]
        report.notes.append("dry-run: MT5 was not imported or called")

    engine_out = _run_engine_smoke(
        db_path=str(audit_path),
        symbol=args.symbol,
        side=args.side,
        volume=args.volume,
        deviation=args.deviation,
        live=True,  # live engine branch; dry-run swaps send_market_order with a fake.
        dry_order_result=dry_order_result,
    )
    report.risk_gate = _safe_json_value(engine_out["gate"])
    report.trade_result = _safe_json_value(engine_out["result"])
    report.timeline_events = _timeline_rows(str(audit_path))
    project_order_request = _latest_timeline_payload(report.timeline_events, "ORDER", "ORDER_REQUEST")
    report.order_payload = _mt5_payload_from_project_request(
        project_order_request,
        args.side,
        args.price,
    )
    order_result = _parse_order_result_from_timeline(report.timeline_events)
    report.raw_response = order_result
    report.retcode = order_result.get("retcode")
    report.retcode_name = _retcode_name(report.retcode)

    if args.live:
        try:
            import MetaTrader5 as mt5  # noqa: PLC0415
            report.mt5_last_error = list(mt5.last_error())
        except Exception:
            pass

    report.classification = classify_result(
        mode=mode,
        init_ok=init_ok,
        symbol_ok=symbol_ok,
        volume_ok=volume_ok,
        retcode=report.retcode,
    )
    _write_report(report, args.report_dir)

    # MARKET_CLOSED is a successful smoke outside session; actual placed/filled
    # also proves the path, but returns 3 so operators cannot miss it.
    if report.classification in {"expected_market_closed", "dry_run_simulated"}:
        return 0, report
    if report.classification == "order_placed_or_filled":
        return 3, report
    return 1, report


def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WDOWIN live execution smoke.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Simulate order_send (default)")
    mode.add_argument("--live", action="store_true", help="Call real MT5 order_send")
    parser.add_argument("--ack-live-risk", action="store_true", help="Required with --live")
    parser.add_argument("--symbol", default=LIVE_SYMBOL_WIN, help="Trade symbol, e.g. WINM26")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--volume", type=float, default=float(WIN_CONTRACTS))
    parser.add_argument("--order-type", choices=["market"], default="market")
    parser.add_argument("--price", type=float, default=0.0, help="Reserved; market path ignores price")
    parser.add_argument("--deviation", type=int, default=int(LIVE_DEVIATION))
    parser.add_argument("--magic", type=int, default=int(LIVE_MAGIC_BASE), help="Report-only; engine uses strategy magic")
    parser.add_argument("--comment", default="wdowin-smoke", help="Report-only; engine comment remains strategy/z_source")
    parser.add_argument("--mt5-path", default=MT5_PATH)
    parser.add_argument("--portable", action="store_true", default=MT5_PORTABLE)
    parser.add_argument("--windows-python", help="Windows Python path for WSL re-exec in --live mode")
    parser.add_argument("--report-dir", default=DEFAULT_REPORT_DIR)
    parser.add_argument("--audit-dir", default=DEFAULT_AUDIT_DIR)
    parser.add_argument("--_windows-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.live:
        args.dry_run = False
    return args


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    reexec_code = _maybe_reexec_windows(args)
    if reexec_code is not None:
        return int(reexec_code)

    code, report = run_smoke(args)
    print(json.dumps(asdict(report), indent=2, sort_keys=True, default=str))
    return code


if __name__ == "__main__":
    sys.exit(main())
