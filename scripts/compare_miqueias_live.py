"""Compare WDOWIN live JSON with Miqueias's reference JSON.

The script does not need the React dashboard. It fetches both FastAPI servers,
writes raw JSON snapshots, derives a business-level diff, and emits a small
JSONL audit that approximates the operational funnel without instrumenting
Miqueias's engine.
"""
from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ENDPOINTS = {
    "v2": "/api/v2/regime",
    "di": "/api/di-regime",
    "health": "/health",
}
FLOAT_TOL = 1e-6


@dataclass
class FetchResult:
    ok: bool
    url: str
    status_code: int | None = None
    data: dict[str, Any] | None = None
    error: str | None = None
    elapsed_ms: float = 0.0


@dataclass
class CompareRun:
    schema: str = "wdowin.miqueias-live-compare.v1"
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    ours_base: str = ""
    ref_base: str = ""
    output_dir: str = ""
    fetch: dict[str, dict[str, Any]] = field(default_factory=dict)
    business: dict[str, dict[str, Any]] = field(default_factory=dict)
    decision: dict[str, Any] = field(default_factory=dict)
    differences: list[dict[str, Any]] = field(default_factory=list)
    files: dict[str, str] = field(default_factory=dict)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture and compare WDOWIN vs Miqueias live API JSON."
    )
    parser.add_argument("--ours", default="http://127.0.0.1:8080")
    parser.add_argument("--ref", default="http://127.0.0.1:8081")
    parser.add_argument("--out", default="audits/live_compare")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument(
        "--tag",
        default="",
        help="Optional suffix for the output directory name",
    )
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Return exit code 1 when business differences are found",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep sampling until interrupted, writing one snapshot directory per run.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=300.0,
        help="Seconds between loop samples when --align-m5 is not used.",
    )
    parser.add_argument(
        "--align-m5",
        action="store_true",
        help="In --loop mode, sample shortly after each 5-minute bar boundary.",
    )
    parser.add_argument(
        "--m5-delay-seconds",
        type=float,
        default=8.0,
        help="Delay after each 5-minute boundary before sampling with --align-m5.",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=0,
        help="Maximum loop samples to run; 0 means forever.",
    )
    return parser.parse_args(argv)


def _clean_base(base: str) -> str:
    return base.rstrip("/")


def _url(base: str, path: str) -> str:
    return f"{_clean_base(base)}{path}"


def fetch_json(url: str, *, timeout: float) -> FetchResult:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            elapsed = (time.perf_counter() - started) * 1000
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                return FetchResult(
                    ok=False,
                    url=url,
                    status_code=resp.status,
                    error=f"INVALID_JSON: {exc}",
                    elapsed_ms=elapsed,
                )
            return FetchResult(
                ok=200 <= resp.status < 300,
                url=url,
                status_code=resp.status,
                data=data,
                elapsed_ms=elapsed,
            )
    except urllib.error.HTTPError as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return FetchResult(
            ok=False,
            url=url,
            status_code=exc.code,
            error=f"HTTP_ERROR: {exc}",
            elapsed_ms=elapsed,
        )
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return FetchResult(
            ok=False,
            url=url,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_ms=elapsed,
        )


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _get(data: dict[str, Any] | None, *path: str) -> Any:
    cur: Any = data or {}
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _strategy_actions(v2: dict[str, Any] | None) -> dict[str, str | None]:
    strategies = _get(v2, "trade_engine", "strategies") or {}
    out: dict[str, str | None] = {}
    for key in ("CONS_BASE", "WDO_NWE", "DI_NWE"):
        val = strategies.get(key) if isinstance(strategies, dict) else None
        out[key] = val.get("action") if isinstance(val, dict) else None
    return out


def business_snapshot(v2: dict[str, Any] | None, di: dict[str, Any] | None) -> dict[str, Any]:
    risk_gate = _get(v2, "risk_gate") or {}
    regime_health = _get(v2, "regime_health") or {}
    coint_eg = _get(v2, "coint_eg") or {}
    rg_info = risk_gate.get("informational") if isinstance(risk_gate, dict) else {}

    return {
        "error": _get(v2, "error"),
        "version": _get(v2, "meta", "version"),
        "symbol_a": _get(v2, "meta", "symbol_a"),
        "symbol_b": _get(v2, "meta", "symbol_b"),
        "last_update": _get(v2, "last_update"),
        "current_z_wdo": _num(_get(v2, "current_z")),
        "current_z_di": _num(_get(di, "current_z")),
        "current_rho": _num(_get(v2, "current_rho")),
        "di_current_rho": _num(_get(di, "current_rho")),
        "beta_ols": _num(_get(v2, "beta_ols")),
        "beta_kalman": _num(_get(v2, "beta_kalman")),
        "beta_delta_pct": _num(_get(v2, "beta_delta_pct")),
        "di_beta_delta_pct": _num(_get(di, "beta_delta_pct")),
        "beta_unstable": bool(_get(v2, "beta_unstable")),
        "di_beta_unstable": bool(_get(di, "beta_unstable")),
        "safe_to_trade": _get(regime_health, "safe_to_trade"),
        "di_safe_to_trade": _get(di, "regime_health", "safe_to_trade"),
        "risk_gate_allowed": risk_gate.get("allowed") if isinstance(risk_gate, dict) else None,
        "risk_gate_reasons": risk_gate.get("reasons") if isinstance(risk_gate, dict) else None,
        "eg_pvalue": _num(
            coint_eg.get("pvalue")
            if isinstance(coint_eg, dict) and coint_eg.get("pvalue") is not None
            else (rg_info or {}).get("eg_pvalue")
        ),
        "di_eg_pvalue": _num(_get(di, "coint_eg", "pvalue")),
        "johansen_open": _get(v2, "johansen_gate", "open"),
        "trade_engine_action": _get(v2, "trade_engine", "action"),
        "strategy_actions": _strategy_actions(v2),
    }


def _compare_value(path: str, ours: Any, ref: Any) -> dict[str, Any] | None:
    if isinstance(ours, float) or isinstance(ref, float):
        if ours is None or ref is None:
            equal = ours is ref
        else:
            equal = abs(float(ours) - float(ref)) <= FLOAT_TOL
    else:
        equal = ours == ref
    if equal:
        return None
    return {"path": path, "ours": ours, "ref": ref}


def compare_business(ours: dict[str, Any], ref: dict[str, Any]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    keys = sorted(set(ours) | set(ref))
    for key in keys:
        if key == "last_update":
            continue
        if key in {"risk_gate_allowed", "risk_gate_reasons"} and (
            ours.get(key) is None or ref.get(key) is None
        ):
            continue
        if key == "strategy_actions":
            actions = sorted(set(ours.get(key) or {}) | set(ref.get(key) or {}))
            for strat in actions:
                diff = _compare_value(
                    f"strategy_actions.{strat}",
                    (ours.get(key) or {}).get(strat),
                    (ref.get(key) or {}).get(strat),
                )
                if diff:
                    diffs.append(diff)
            continue
        diff = _compare_value(key, ours.get(key), ref.get(key))
        if diff:
            diffs.append(diff)
    return diffs


def compare_fetch_health(fetch: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for system in ("ours", "ref"):
        for endpoint, result in sorted((fetch.get(system) or {}).items()):
            if result.get("ok"):
                continue
            diffs.append({
                "path": f"fetch.{system}.{endpoint}",
                "ours": result.get("error") if system == "ours" else None,
                "ref": result.get("error") if system == "ref" else None,
                "status_code": result.get("status_code"),
                "url": result.get("url"),
            })
    return diffs


def decision_summary(ours: dict[str, Any], ref: dict[str, Any]) -> dict[str, Any]:
    strategies = sorted(
        set(ours.get("strategy_actions") or {})
        | set(ref.get("strategy_actions") or {})
    )
    strategy_rows = []
    signal_mismatches = []
    for strategy in strategies:
        ours_action = (ours.get("strategy_actions") or {}).get(strategy)
        ref_action = (ref.get("strategy_actions") or {}).get(strategy)
        matches = ours_action == ref_action
        row = {
            "strategy": strategy,
            "ours_action": ours_action,
            "ref_action": ref_action,
            "matches": matches,
        }
        strategy_rows.append(row)
        if not matches:
            signal_mismatches.append(row)

    engine_matches = ours.get("trade_engine_action") == ref.get("trade_engine_action")
    return {
        "engine": {
            "ours_action": ours.get("trade_engine_action"),
            "ref_action": ref.get("trade_engine_action"),
            "matches": engine_matches,
        },
        "strategies": strategy_rows,
        "signal_mismatches": signal_mismatches,
        "has_signal_mismatch": bool(signal_mismatches) or not engine_matches,
        "indicator_diff_count": 0,
        "fetch_error_count": 0,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )


def _audit_event(
    *,
    system: str,
    phase: str,
    event: str,
    status: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "system": system,
        "phase": phase,
        "event": event,
        "status": status,
        "message": message,
        "payload": payload or {},
    }


def build_audit_events(run: CompareRun) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for system in ("ours", "ref"):
        fetch = run.fetch.get(system, {})
        business = run.business.get(system, {})
        for name, result in fetch.items():
            events.append(_audit_event(
                system=system,
                phase="DATA",
                event=f"FETCH_{name.upper()}",
                status="OK" if result.get("ok") else "FAILED",
                message=result.get("url") or name,
                payload={
                    "status_code": result.get("status_code"),
                    "error": result.get("error"),
                    "elapsed_ms": result.get("elapsed_ms"),
                },
            ))

        if fetch.get("v2", {}).get("ok"):
            events.append(_audit_event(
                system=system,
                phase="INDICATORS",
                event="REGIME_SNAPSHOT",
                status="OK",
                message="Business fields extracted from /api/v2/regime + /api/di-regime",
                payload=business,
            ))
            allowed = business.get("risk_gate_allowed")
            if allowed is None:
                allowed = bool(business.get("safe_to_trade"))
            events.append(_audit_event(
                system=system,
                phase="ELIGIBILITY",
                event="GATE_STATE",
                status="OK" if allowed else "BLOCKED",
                message="Reference gate is inferred when no explicit risk_gate exists",
                payload={
                    "safe_to_trade": business.get("safe_to_trade"),
                    "risk_gate_allowed": business.get("risk_gate_allowed"),
                    "risk_gate_reasons": business.get("risk_gate_reasons"),
                    "eg_pvalue": business.get("eg_pvalue"),
                    "beta_unstable": business.get("beta_unstable"),
                },
            ))
            for strategy, action in (business.get("strategy_actions") or {}).items():
                events.append(_audit_event(
                    system=system,
                    phase="SIGNAL",
                    event=action or "UNKNOWN",
                    status="OK" if action and action != "WAIT" else "INFO",
                    message=strategy,
                    payload={"strategy": strategy, "action": action},
                ))

    for diff in run.differences:
        events.append(_audit_event(
            system="compare",
            phase="COMPARE",
            event="MISMATCH",
            status="FAILED",
            message=diff["path"],
            payload=diff,
        ))

    return events


def run_compare(
    *,
    ours_base: str,
    ref_base: str,
    out_dir: Path,
    timeout: float,
) -> CompareRun:
    run = CompareRun(
        ours_base=_clean_base(ours_base),
        ref_base=_clean_base(ref_base),
        output_dir=str(out_dir),
    )

    raw: dict[str, dict[str, FetchResult]] = {"ours": {}, "ref": {}}
    for system, base in (("ours", ours_base), ("ref", ref_base)):
        for name, path in ENDPOINTS.items():
            raw[system][name] = fetch_json(_url(base, path), timeout=timeout)

    for system in ("ours", "ref"):
        run.fetch[system] = {
            name: asdict(result)
            for name, result in raw[system].items()
        }
        v2 = raw[system]["v2"].data if raw[system]["v2"].ok else None
        di = raw[system]["di"].data if raw[system]["di"].ok else None
        run.business[system] = business_snapshot(v2, di)

    run.differences = (
        compare_fetch_health(run.fetch)
        + compare_business(run.business["ours"], run.business["ref"])
    )
    run.decision = decision_summary(run.business["ours"], run.business["ref"])
    run.decision["indicator_diff_count"] = sum(
        1 for diff in run.differences
        if not str(diff.get("path", "")).startswith("strategy_actions.")
        and not str(diff.get("path", "")).startswith("fetch.")
    )
    run.decision["fetch_error_count"] = sum(
        1 for diff in run.differences
        if str(diff.get("path", "")).startswith("fetch.")
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    for system in ("ours", "ref"):
        for name, result in raw[system].items():
            payload = result.data if result.data is not None else asdict(result)
            path = out_dir / f"{system}_{name}.json"
            _write_json(path, payload)
            run.files[f"{system}_{name}"] = str(path)

    audit_path = out_dir / "audit.jsonl"
    events = build_audit_events(run)
    audit_path.write_text(
        "".join(json.dumps(event, sort_keys=True, default=str) + "\n" for event in events),
        encoding="utf-8",
    )
    run.files["audit_jsonl"] = str(audit_path)

    summary_path = out_dir / "summary.json"
    _write_json(summary_path, asdict(run))
    run.files["summary"] = str(summary_path)
    return run


def _output_dir(base: str, tag: str) -> Path:
    suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
    if tag:
        safe_tag = "".join(c if c.isalnum() or c in {"-", "_"} else "_" for c in tag)
        suffix = f"{suffix}-{safe_tag}"
    return Path(base) / suffix


def _print_run_summary(run: CompareRun) -> None:
    print("=" * 72)
    print("WDOWIN x Miqueias live comparison")
    print(f"output_dir: {run.output_dir}")
    print(f"summary:    {run.files['summary']}")
    print(f"audit:      {run.files['audit_jsonl']}")
    print(f"diffs:      {len(run.differences)}")
    for diff in run.differences[:20]:
        print(f"- {diff['path']}: ours={diff['ours']!r} ref={diff['ref']!r}")
    if len(run.differences) > 20:
        print(f"... {len(run.differences) - 20} more")
    print("=" * 72, flush=True)


def _run_once(args: argparse.Namespace, *, tag: str) -> CompareRun:
    run = run_compare(
        ours_base=args.ours,
        ref_base=args.ref,
        out_dir=_output_dir(args.out, tag),
        timeout=args.timeout,
    )
    _print_run_summary(run)
    return run


def _seconds_until_next_m5(now: datetime | None = None, *, delay_seconds: float = 8.0) -> float:
    now = now or datetime.now()
    minute_floor = now.replace(second=0, microsecond=0)
    minutes_to_add = (5 - (minute_floor.minute % 5)) % 5
    target = minute_floor + timedelta(minutes=minutes_to_add, seconds=delay_seconds)
    if target <= now:
        target += timedelta(minutes=5)
    return max(0.0, (target - now).total_seconds())


def _append_loop_index(base: str, run: CompareRun, *, run_number: int, tag: str) -> None:
    base_path = Path(base)
    base_path.mkdir(parents=True, exist_ok=True)
    row = {
        "schema": "wdowin.miqueias-live-compare.index.v1",
        "timestamp": run.timestamp,
        "run_number": run_number,
        "tag": tag,
        "output_dir": run.output_dir,
        "diff_count": len(run.differences),
        "differences": run.differences,
        "decision": run.decision,
        "ours": {
            "trade_engine_action": run.business.get("ours", {}).get("trade_engine_action"),
            "strategy_actions": run.business.get("ours", {}).get("strategy_actions"),
            "current_z_wdo": run.business.get("ours", {}).get("current_z_wdo"),
            "current_z_di": run.business.get("ours", {}).get("current_z_di"),
            "risk_gate_reasons": run.business.get("ours", {}).get("risk_gate_reasons"),
        },
        "ref": {
            "trade_engine_action": run.business.get("ref", {}).get("trade_engine_action"),
            "strategy_actions": run.business.get("ref", {}).get("strategy_actions"),
            "current_z_wdo": run.business.get("ref", {}).get("current_z_wdo"),
            "current_z_di": run.business.get("ref", {}).get("current_z_di"),
            "risk_gate_reasons": run.business.get("ref", {}).get("risk_gate_reasons"),
        },
    }
    with (base_path / "index.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _loop(args: argparse.Namespace) -> int:
    run_number = 0
    print(
        "Starting WDOWIN x Miqueias compare loop "
        f"(ours={args.ours}, ref={args.ref}, out={args.out})",
        flush=True,
    )
    try:
        while True:
            if args.align_m5:
                wait = _seconds_until_next_m5(delay_seconds=args.m5_delay_seconds)
                print(f"Waiting {wait:.1f}s for next M5 sample...", flush=True)
                time.sleep(wait)

            run_number += 1
            run_tag = args.tag or "loop"
            run = _run_once(args, tag=f"{run_tag}-run{run_number:04d}")
            _append_loop_index(args.out, run, run_number=run_number, tag=run_tag)

            if args.fail_on_diff and run.differences:
                return 1
            if args.max_runs > 0 and run_number >= args.max_runs:
                return 0
            if not args.align_m5:
                time.sleep(max(0.0, args.interval_seconds))
    except KeyboardInterrupt:
        print("Compare loop stopped by operator.", flush=True)
        return 130


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.loop:
        return _loop(args)
    run = _run_once(args, tag=args.tag)
    return 1 if args.fail_on_diff and run.differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
