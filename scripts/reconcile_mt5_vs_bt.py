# -*- coding: utf-8 -*-
"""
Reconciliacao Diaria MT5 Live vs Backtest (Top 10 Jumba EAs).

Le (em modo somente-leitura) os CSVs gerados pelo Jumba_Portfolio_Live_Monitor
e pelos EAs em %APPDATA%/MetaQuotes/Terminal/Common/Files/:
  - jumba_portfolio_live_monitor_<login>.csv
  - jumba_live_deals_<login>.csv
  - jumba_live_trades_audit_<login>.csv
  - jumba_daily_stop_state_<login>.csv (+ jumba_daily_stop_events_<login>.csv)
  - jumba_state_<login>_*_*.csv e jumba_wdo_state_<login>_*_*.csv

Calcula expectativa pro-rata do BT (BT_NetBRL * n_pregoes_live / 212.0),
desvios de PnL/WR/PF/MaxDD/LossStreak, concentracao diaria de resultado,
auditoria de limites de stop (esperado Global 950 / WIN 400 / WDO 0) e estado
dos 10 robos ativos, gerando relatorios .md e .json em data/reports/reconciliacao_mt5/.
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_COMMON_DIR = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal\Common\Files")
DEFAULT_OUT_DIR = os.path.join("data", "reports", "reconciliacao_mt5")
DEFAULT_LOGIN = "2004051"
ALL_LOGINS = ("2004051", "62033102")
BT_DAYS_DEFAULT = 212.0

EXPECTED_STOP_GLOBAL = 950.0
EXPECTED_STOP_WIN = 400.0
EXPECTED_STOP_WDO = 0.0

TOP10_ROBOTS: Tuple[Tuple[str, int, str], ...] = (
    ("EST-04", 88004, "WIN"),
    ("EST-07", 88007, "WIN"),
    ("EST-09", 88009, "WIN"),
    ("EST-10", 88010, "WIN"),
    ("EST-13", 88013, "WIN"),
    ("EST-14", 88014, "WIN"),
    ("EST-15", 88015, "WIN"),
    ("WDO-01", 89001, "WDO"),
    ("WDO-05", 89005, "WDO"),
    ("WDO-07", 89007, "WDO"),
)
TOP10_MAGICS = {magic for _, magic, _ in TOP10_ROBOTS}
TOP10_CODE_BY_MAGIC = {magic: code for code, magic, _ in TOP10_ROBOTS}


@dataclass
class AlertItem:
    severity: str
    code: str
    target: str
    message: str


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(str(val).strip().replace(",", "."))
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError):
        return default


def _normalize_date(raw_dt: str) -> str:
    """Extrai YYYY-MM-DD de strings 'YYYY.MM.DD HH:MM:SS' ou 'YYYY-MM-DD ...'."""
    token = raw_dt.strip().split()[0] if raw_dt else ""
    return token.replace(".", "-")


def load_monitor_csv(path: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Le jumba_portfolio_live_monitor_<login>.csv."""
    if not os.path.isfile(path):
        return [], None

    mtime_iso = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for r in reader:
            code = (r.get("Code") or "").strip()
            if not code:
                continue
            rows.append(
                {
                    "code": code,
                    "strategy": (r.get("Strategy") or "").strip(),
                    "magic": _safe_int(r.get("Magic")),
                    "open_dir": _safe_int(r.get("OpenDir")),
                    "open_lots": _safe_float(r.get("OpenLots")),
                    "floating_brl": _safe_float(r.get("FloatingBRL")),
                    "pending_orders": _safe_int(r.get("PendingOrders")),
                    "live_trades": _safe_int(r.get("LiveTrades")),
                    "live_wr_pct": _safe_float(r.get("LiveWR_Pct")),
                    "live_pf": _safe_float(r.get("LivePF")),
                    "live_day_brl": _safe_float(r.get("LiveDayBRL")),
                    "live_net_brl": _safe_float(r.get("LiveNetBRL")),
                    "live_curr_dd_brl": _safe_float(r.get("LiveCurrDD_BRL")),
                    "live_max_dd_brl": _safe_float(r.get("LiveMaxDD_BRL")),
                    "bt_max_dd_brl": _safe_float(r.get("BT_MaxDD_BRL")),
                    "dd_used_pct": _safe_float(r.get("DD_Used_Pct")),
                    "live_curr_loss_streak": _safe_int(r.get("LiveCurrLossStreak")),
                    "live_max_loss_streak": _safe_int(r.get("LiveMaxLossStreak")),
                    "bt_max_loss_streak": _safe_int(r.get("BT_MaxLossStreak")),
                    "bt_trades": _safe_int(r.get("BT_Trades")),
                    "bt_wr_pct": _safe_float(r.get("BT_WR_Pct")),
                    "bt_pf": _safe_float(r.get("BT_PF")),
                    "bt_net_brl": _safe_float(r.get("BT_NetBRL")),
                }
            )
    return rows, mtime_iso


def _summarize_daily_pnl(daily_pnl: Dict[str, float]) -> Dict[str, Any]:
    """Calcula metricas de pregoes, melhor/pior dia e concentracao."""
    if not daily_pnl:
        return {
            "sessions": 0,
            "date_min": None,
            "date_max": None,
            "total_net_brl": 0.0,
            "positive_days": 0,
            "negative_days": 0,
            "flat_days": 0,
            "best_day": None,
            "worst_day": None,
            "net_ex_best_day_brl": 0.0,
            "best_day_share_of_net_pct": None,
            "max_abs_day_share_of_abs_volume_pct": 0.0,
            "daily_series": [],
        }

    ordered_days = sorted(daily_pnl.keys())
    total_net = round(sum(daily_pnl.values()), 2)
    best_date = max(ordered_days, key=lambda d: daily_pnl[d])
    worst_date = min(ordered_days, key=lambda d: daily_pnl[d])
    best_val = round(daily_pnl[best_date], 2)
    worst_val = round(daily_pnl[worst_date], 2)
    net_ex_best = round(total_net - best_val, 2)
    sum_abs_days = sum(abs(v) for v in daily_pnl.values())
    max_abs_day = max(abs(v) for v in daily_pnl.values())

    best_share_net: Optional[float] = None
    if total_net > 0.01:
        best_share_net = round(100.0 * best_val / total_net, 1)

    max_abs_share = round(100.0 * max_abs_day / sum_abs_days, 1) if sum_abs_days > 0.01 else 0.0

    return {
        "sessions": len(ordered_days),
        "date_min": ordered_days[0],
        "date_max": ordered_days[-1],
        "total_net_brl": total_net,
        "positive_days": sum(1 for d in ordered_days if daily_pnl[d] > 0.01),
        "negative_days": sum(1 for d in ordered_days if daily_pnl[d] < -0.01),
        "flat_days": sum(1 for d in ordered_days if abs(daily_pnl[d]) <= 0.01),
        "best_day": {"date": best_date, "pnl_brl": best_val},
        "worst_day": {"date": worst_date, "pnl_brl": worst_val},
        "net_ex_best_day_brl": net_ex_best,
        "best_day_share_of_net_pct": best_share_net,
        "max_abs_day_share_of_abs_volume_pct": max_abs_share,
        "daily_series": [{"date": d, "pnl_brl": round(daily_pnl[d], 2)} for d in ordered_days],
    }


def load_deals_csv(path: str) -> Dict[str, Any]:
    """Le jumba_live_deals_<login>.csv e separa Top 10 vs todos os deals."""
    if not os.path.isfile(path):
        return {"exists": False}

    daily_all: Dict[str, float] = {}
    daily_top10: Dict[str, float] = {}
    by_magic_all: Dict[int, Dict[str, Any]] = {}
    total_rows = 0
    out_deals_all = 0
    out_deals_top10 = 0
    non_top10_out_deals = 0

    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for r in reader:
            total_rows += 1
            entry = (r.get("entry") or "").strip()
            if entry not in ("1", "2", "3"):  # DEAL_ENTRY_OUT / INOUT / OUT_BY
                continue
            date_str = _normalize_date(r.get("time") or "")
            if not date_str:
                continue
            magic = _safe_int(r.get("magic"))
            pnl = (
                _safe_float(r.get("profit"))
                + _safe_float(r.get("swap"))
                + _safe_float(r.get("commission"))
                + _safe_float(r.get("fee"))
            )

            out_deals_all += 1
            daily_all[date_str] = daily_all.get(date_str, 0.0) + pnl

            m_entry = by_magic_all.setdefault(magic, {"trades": 0, "net_brl": 0.0, "wins": 0, "losses": 0})
            m_entry["trades"] += 1
            m_entry["net_brl"] = round(m_entry["net_brl"] + pnl, 2)
            if pnl > 0.001:
                m_entry["wins"] += 1
            elif pnl < -0.001:
                m_entry["losses"] += 1

            if magic in TOP10_MAGICS:
                out_deals_top10 += 1
                daily_top10[date_str] = daily_top10.get(date_str, 0.0) + pnl
            else:
                non_top10_out_deals += 1

    return {
        "exists": True,
        "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
        "total_deal_rows": total_rows,
        "out_deals_all": out_deals_all,
        "out_deals_top10": out_deals_top10,
        "non_top10_out_deals": non_top10_out_deals,
        "top10_summary": _summarize_daily_pnl(daily_top10),
        "all_summary": _summarize_daily_pnl(daily_all),
        "by_magic": {str(k): v for k, v in sorted(by_magic_all.items())},
    }


def load_audit_csv(path: str) -> Dict[str, Any]:
    """Le jumba_live_trades_audit_<login>.csv (sem cabecalho, 10 colunas ';')."""
    if not os.path.isfile(path):
        return {"exists": False}

    daily_all: Dict[str, float] = {}
    daily_top10: Dict[str, float] = {}
    by_magic: Dict[int, Dict[str, Any]] = {}
    reasons: Dict[str, int] = {}
    total_trades = 0
    top10_trades = 0

    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            cols = line.split(";")
            if len(cols) < 9:
                continue
            # Pula eventual cabecalho se existir
            if not cols[2].strip().lstrip("-").isdigit():
                continue

            date_str = _normalize_date(cols[0])
            magic = _safe_int(cols[2])
            pnl = _safe_float(cols[8])
            reason = cols[9].strip() if len(cols) >= 10 else ""

            total_trades += 1
            daily_all[date_str] = daily_all.get(date_str, 0.0) + pnl
            if reason:
                reasons[reason] = reasons.get(reason, 0) + 1

            m_entry = by_magic.setdefault(magic, {"trades": 0, "net_brl": 0.0})
            m_entry["trades"] += 1
            m_entry["net_brl"] = round(m_entry["net_brl"] + pnl, 2)

            if magic in TOP10_MAGICS:
                top10_trades += 1
                daily_top10[date_str] = daily_top10.get(date_str, 0.0) + pnl

    return {
        "exists": True,
        "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
        "total_trades": total_trades,
        "top10_trades": top10_trades,
        "top10_summary": _summarize_daily_pnl(daily_top10),
        "all_summary": _summarize_daily_pnl(daily_all),
        "by_magic": {str(k): v for k, v in sorted(by_magic.items())},
        "exit_reasons": dict(sorted(reasons.items())),
    }


def load_daily_stop_state(path: str) -> Dict[str, Any]:
    """Le jumba_daily_stop_state_<login>.csv e audita limites 950 / 400 / 0."""
    if not os.path.isfile(path):
        return {"exists": False}

    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        rows = list(reader)

    if not rows:
        return {"exists": True, "empty": True}

    r = rows[-1]
    limit_global = _safe_float(r.get("limit_global"))
    limit_win = _safe_float(r.get("limit_win"))
    limit_wdo = _safe_float(r.get("limit_wdo"))
    enabled = _safe_int(r.get("enabled"))

    limits_ok = (
        enabled == 1
        and abs(limit_global - EXPECTED_STOP_GLOBAL) < 0.01
        and abs(limit_win - EXPECTED_STOP_WIN) < 0.01
        and abs(limit_wdo - EXPECTED_STOP_WDO) < 0.01
    )

    return {
        "exists": True,
        "empty": False,
        "updated_at": (r.get("updated_at") or "").strip(),
        "day_key": (r.get("day_key") or "").strip(),
        "enabled": enabled,
        "auction_pause": _safe_int(r.get("auction_pause")),
        "stop_global_hit": _safe_int(r.get("stop_global_hit")),
        "stop_win_hit": _safe_int(r.get("stop_win_hit")),
        "stop_wdo_hit": _safe_int(r.get("stop_wdo_hit")),
        "limit_global": limit_global,
        "limit_win": limit_win,
        "limit_wdo": limit_wdo,
        "expected_limits": {
            "global": EXPECTED_STOP_GLOBAL,
            "win": EXPECTED_STOP_WIN,
            "wdo": EXPECTED_STOP_WDO,
        },
        "limits_match_expected": limits_ok,
        "total_global": _safe_float(r.get("total_global")),
        "total_win": _safe_float(r.get("total_win")),
        "total_wdo": _safe_float(r.get("total_wdo")),
        "mae_global": _safe_float(r.get("mae_global")),
        "mae_win": _safe_float(r.get("mae_win")),
        "mae_wdo": _safe_float(r.get("mae_wdo")),
    }


def load_daily_stop_events(path: str) -> List[Dict[str, Any]]:
    """Le jumba_daily_stop_events_<login>.csv se existir."""
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return [dict(r) for r in csv.DictReader(f, delimiter=";")]


def audit_state_files(common_dir: str, login: str) -> Dict[str, Any]:
    """Audita jumba_state_<login>_*_*.csv e jumba_wdo_state_<login>_*_*.csv."""
    patterns = [
        os.path.join(common_dir, f"jumba_state_{login}_*_*.csv"),
        os.path.join(common_dir, f"jumba_wdo_state_{login}_*_*.csv"),
    ]
    found_by_magic: Dict[int, List[Dict[str, Any]]] = {}

    for pat in patterns:
        for p in sorted(glob.glob(pat)):
            fname = os.path.basename(p)
            stem = os.path.splitext(fname)[0]
            parts = stem.split("_")
            magic = _safe_int(parts[-1], -1)
            symbol = parts[-2] if len(parts) >= 2 else ""
            mtime_ts = os.path.getmtime(p)
            mtime_dt = datetime.fromtimestamp(mtime_ts)
            state_date = ""
            try:
                with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
                    state_date = f.readline().strip()
            except OSError:
                pass
            found_by_magic.setdefault(magic, []).append(
                {
                    "filename": fname,
                    "symbol": symbol,
                    "state_date": state_date,
                    "mtime": mtime_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "mtime_ts": mtime_ts,
                    "size_bytes": os.path.getsize(p),
                }
            )

    top10_latest_ts = 0.0
    for m in TOP10_MAGICS:
        for item in found_by_magic.get(m, []):
            if item["mtime_ts"] > top10_latest_ts:
                top10_latest_ts = item["mtime_ts"]

    top10_status: List[Dict[str, Any]] = []
    for code, magic, asset in TOP10_ROBOTS:
        entries = sorted(found_by_magic.get(magic, []), key=lambda x: x["mtime_ts"], reverse=True)
        if entries:
            latest = entries[0]
            age_days_vs_latest = round((top10_latest_ts - latest["mtime_ts"]) / 86400.0, 2) if top10_latest_ts else 0.0
            is_recent = age_days_vs_latest <= 2.0
            top10_status.append(
                {
                    "code": code,
                    "magic": magic,
                    "asset": asset,
                    "has_state": True,
                    "is_recent": is_recent,
                    "latest_file": latest["filename"],
                    "symbol": latest["symbol"],
                    "state_date": latest["state_date"],
                    "mtime": latest["mtime"],
                    "lag_days_vs_newest": age_days_vs_latest,
                }
            )
        else:
            top10_status.append(
                {
                    "code": code,
                    "magic": magic,
                    "asset": asset,
                    "has_state": False,
                    "is_recent": False,
                    "latest_file": None,
                    "symbol": None,
                    "state_date": None,
                    "mtime": None,
                    "lag_days_vs_newest": None,
                }
            )

    legacy_magics = sorted(m for m in found_by_magic if m not in TOP10_MAGICS)
    return {
        "top10_latest_mtime": (
            datetime.fromtimestamp(top10_latest_ts).strftime("%Y-%m-%d %H:%M:%S") if top10_latest_ts else None
        ),
        "top10_present_count": sum(1 for item in top10_status if item["has_state"]),
        "top10_recent_count": sum(1 for item in top10_status if item["is_recent"]),
        "top10_states": top10_status,
        "legacy_state_magics": legacy_magics,
    }


def _build_alerts(
    login: str,
    rows: List[Dict[str, Any]],
    deals_info: Dict[str, Any],
    audit_info: Dict[str, Any],
    stop_info: Dict[str, Any],
    state_info: Dict[str, Any],
) -> List[AlertItem]:
    alerts: List[AlertItem] = []

    # 1. Stop diario
    if not stop_info.get("exists"):
        alerts.append(
            AlertItem(
                severity="CRITICAL",
                code="STOP_STATE_MISSING",
                target=f"conta:{login}",
                message=f"Arquivo jumba_daily_stop_state_{login}.csv nao encontrado.",
            )
        )
    elif stop_info.get("empty"):
        alerts.append(
            AlertItem(
                severity="CRITICAL",
                code="STOP_STATE_EMPTY",
                target=f"conta:{login}",
                message=f"Arquivo jumba_daily_stop_state_{login}.csv esta vazio.",
            )
        )
    else:
        if stop_info.get("enabled") != 1:
            alerts.append(
                AlertItem(
                    severity="CRITICAL",
                    code="STOP_DISABLED",
                    target=f"conta:{login}",
                    message="Gerencia de Stop Diario esta DESATIVADA (enabled != 1).",
                )
            )
        if not stop_info.get("limits_match_expected"):
            alerts.append(
                AlertItem(
                    severity="HIGH",
                    code="STOP_LIMIT_MISMATCH",
                    target=f"conta:{login}",
                    message=(
                        f"Limites de Stop divergentes do padrao G {EXPECTED_STOP_GLOBAL:.0f} / "
                        f"W {EXPECTED_STOP_WIN:.0f} / D {EXPECTED_STOP_WDO:.0f}: "
                        f"atual G {stop_info['limit_global']:.0f} / W {stop_info['limit_win']:.0f} / "
                        f"D {stop_info['limit_wdo']:.0f}."
                    ),
                )
            )

    # 2. Metricas por robo, subtotal e total (DD >= 70%, LossStreak >= BT, 0 trades)
    deals_by_magic = deals_info.get("by_magic", {}) if deals_info.get("exists") else {}
    for r in rows:
        code = r["code"]
        dd_pct = r["dd_used_pct"]
        if dd_pct >= 70.0:
            sev = "CRITICAL" if dd_pct >= 85.0 else "HIGH"
            alerts.append(
                AlertItem(
                    severity=sev,
                    code="DD_USED_HIGH",
                    target=code,
                    message=(
                        f"{code} consumiu {dd_pct:.1f}% do MaxDD do BT "
                        f"(Live MaxDD R$ {r['live_max_dd_brl']:.0f} vs BT R$ {r['bt_max_dd_brl']:.0f})."
                    ),
                )
            )

        bt_streak = r["bt_max_loss_streak"]
        if bt_streak > 0 and (r["live_max_loss_streak"] >= bt_streak or r["live_curr_loss_streak"] >= bt_streak):
            sev = "CRITICAL" if r["live_max_loss_streak"] > bt_streak else "HIGH"
            alerts.append(
                AlertItem(
                    severity=sev,
                    code="LOSS_STREAK_BREACH",
                    target=code,
                    message=(
                        f"{code} atingiu/igualou Loss Streak do BT: "
                        f"Live Atual={r['live_curr_loss_streak']} Max={r['live_max_loss_streak']} vs BT={bt_streak}."
                    ),
                )
            )

        if r["magic"] in TOP10_MAGICS and r["live_trades"] == 0:
            alerts.append(
                AlertItem(
                    severity="INFO",
                    code="ROBOT_NO_TRADES",
                    target=code,
                    message=(
                        f"{code} (magic {r['magic']}) tem 0 trades fechados no monitor "
                        "(verificar se recem-ativado como EST-09/10 em 19/11 ou sem gatilho)."
                    ),
                )
            )
        elif r["magic"] in TOP10_MAGICS and deals_by_magic:
            d_cnt = deals_by_magic.get(str(r["magic"]), {}).get("trades", 0)
            if d_cnt != r["live_trades"]:
                alerts.append(
                    AlertItem(
                        severity="INFO",
                        code="MONITOR_VS_DEALS_COUNT",
                        target=code,
                        message=f"{code}: monitor={r['live_trades']} trades vs deals OUT={d_cnt}.",
                    )
                )

    # 3. State files Top 10
    for st in state_info.get("top10_states", []):
        if not st["has_state"]:
            alerts.append(
                AlertItem(
                    severity="HIGH",
                    code="STATE_FILE_MISSING",
                    target=st["code"],
                    message=f"{st['code']} (magic {st['magic']}) sem arquivo de estado em Common\\Files.",
                )
            )
        elif not st["is_recent"]:
            alerts.append(
                AlertItem(
                    severity="HIGH",
                    code="STATE_FILE_STALE",
                    target=st["code"],
                    message=(
                        f"{st['code']} (magic {st['magic']}) com arquivo de estado defasado "
                        f"({st['mtime']}, atraso {st['lag_days_vs_newest']}d vs mais recente)."
                    ),
                )
            )

    # 4. Concentracao diaria de PnL
    top10_sum = deals_info.get("top10_summary") if deals_info.get("exists") else audit_info.get("top10_summary")
    if top10_sum and top10_sum.get("sessions", 0) > 1:
        best = top10_sum["best_day"]
        total_net = top10_sum["total_net_brl"]
        net_ex_best = top10_sum["net_ex_best_day_brl"]
        share_net = top10_sum["best_day_share_of_net_pct"]
        max_abs_share = top10_sum["max_abs_day_share_of_abs_volume_pct"]
        conc_abs_threshold = 25.0 if top10_sum["sessions"] >= 5 else 40.0
        if (share_net is not None and share_net >= 40.0) or (total_net >= 0 and net_ex_best < 0) or max_abs_share >= conc_abs_threshold:
            alerts.append(
                AlertItem(
                    severity="WARN",
                    code="PNL_CONCENTRATION_HIGH",
                    target=f"conta:{login}",
                    message=(
                        f"Alta concentracao em 1 pregao: melhor dia {best['date']} fez R$ {best['pnl_brl']:+.2f} "
                        f"(PnL liquido acumulado R$ {total_net:+.2f}; sem o melhor dia seria R$ {net_ex_best:+.2f}; "
                        f"maior dia representa {max_abs_share:.1f}% do volume |diario|)."
                    ),
                )
            )

    return alerts


def reconcile_login(common_dir: str, login: str, bt_days: float = BT_DAYS_DEFAULT) -> Dict[str, Any]:
    """Executa reconciliacao completa para um login MT5."""
    monitor_path = os.path.join(common_dir, f"jumba_portfolio_live_monitor_{login}.csv")
    deals_path = os.path.join(common_dir, f"jumba_live_deals_{login}.csv")
    audit_path = os.path.join(common_dir, f"jumba_live_trades_audit_{login}.csv")
    stop_path = os.path.join(common_dir, f"jumba_daily_stop_state_{login}.csv")
    events_path = os.path.join(common_dir, f"jumba_daily_stop_events_{login}.csv")

    monitor_rows, monitor_mtime = load_monitor_csv(monitor_path)
    deals_info = load_deals_csv(deals_path)
    audit_info = load_audit_csv(audit_path)
    stop_info = load_daily_stop_state(stop_path)
    stop_events = load_daily_stop_events(events_path)
    state_info = audit_state_files(common_dir, login)

    # Determina pregoes operados (prioridade: deals Top10 -> deals All -> audit Top10)
    n_pregoes_live = 0
    date_min = None
    date_max = None
    sessions_source = "none"
    if deals_info.get("exists") and deals_info["top10_summary"]["sessions"] > 0:
        s = deals_info["top10_summary"]
        n_pregoes_live = s["sessions"]
        date_min = s["date_min"]
        date_max = s["date_max"]
        sessions_source = "deals_top10"
    elif deals_info.get("exists") and deals_info["all_summary"]["sessions"] > 0:
        s = deals_info["all_summary"]
        n_pregoes_live = s["sessions"]
        date_min = s["date_min"]
        date_max = s["date_max"]
        sessions_source = "deals_all"
    elif audit_info.get("exists") and audit_info["top10_summary"]["sessions"] > 0:
        s = audit_info["top10_summary"]
        n_pregoes_live = s["sessions"]
        date_min = s["date_min"]
        date_max = s["date_max"]
        sessions_source = "audit_top10"

    enriched_rows: List[Dict[str, Any]] = []
    for r in monitor_rows:
        bt_prorata = round(r["bt_net_brl"] * n_pregoes_live / bt_days, 2) if n_pregoes_live > 0 else 0.0
        desvio_brl = round(r["live_net_brl"] - bt_prorata, 2)
        desvio_pct = round(100.0 * desvio_brl / abs(bt_prorata), 1) if abs(bt_prorata) > 0.01 else None
        wr_diff = round(r["live_wr_pct"] - r["bt_wr_pct"], 1) if r["live_trades"] > 0 else None
        pf_diff = round(r["live_pf"] - r["bt_pf"], 2) if r["live_trades"] > 0 else None
        streak_pct = (
            round(100.0 * r["live_max_loss_streak"] / r["bt_max_loss_streak"], 1)
            if r["bt_max_loss_streak"] > 0
            else 0.0
        )

        enriched_rows.append(
            {
                **r,
                "bt_prorata_brl": bt_prorata,
                "desvio_brl": desvio_brl,
                "desvio_pct": desvio_pct,
                "wr_diff_pp": wr_diff,
                "pf_diff": pf_diff,
                "streak_used_pct": streak_pct,
            }
        )

    alerts = _build_alerts(login, enriched_rows, deals_info, audit_info, stop_info, state_info)
    total_row = next((r for r in enriched_rows if r["code"] == "TOTAL"), None)

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "login": login,
        "common_dir": common_dir,
        "bt_days_base": bt_days,
        "monitor_exists": bool(monitor_rows),
        "monitor_mtime": monitor_mtime,
        "sessions": {
            "source": sessions_source,
            "n_pregoes_live": n_pregoes_live,
            "date_min": date_min,
            "date_max": date_max,
        },
        "total_summary": total_row,
        "rows": enriched_rows,
        "deals": deals_info,
        "audit": audit_info,
        "daily_stop": stop_info,
        "daily_stop_events": stop_events,
        "state_files": state_info,
        "alerts": [asdict(a) for a in alerts],
    }


def render_markdown(rep: Dict[str, Any]) -> str:
    """Formata relatorio completo em Markdown."""
    login = rep["login"]
    sess = rep["sessions"]
    tot = rep["total_summary"] or {}
    stop = rep["daily_stop"]
    deals = rep["deals"]
    audit = rep["audit"]
    state = rep["state_files"]

    lines: List[str] = [
        f"# Reconciliacao MT5 Live vs Backtest — Conta `{login}`",
        "",
        f"- **Gerado em:** `{rep['generated_at']}`",
        f"- **Fonte CSV (`Common\\Files`):** `{rep['common_dir']}`",
        f"- **Monitor CSV atualizado em:** `{rep['monitor_mtime'] or 'AUSENTE'}`",
        f"- **Pregoes operados (Top 10):** **{sess['n_pregoes_live']}** (`{sess['date_min']}` -> `{sess['date_max']}`, fonte `{sess['source']}`, base BT `{rep['bt_days_base']:.0f}` pregoes)",
        "",
    ]

    if tot:
        desvio_pct_str = f"{tot['desvio_pct']:+.1f}%" if tot["desvio_pct"] is not None else "n/a"
        lines.extend(
            [
                "## Resumo Executivo da Carteira (Top 10)",
                "",
                "| Metrica | Live | Esperado BT (Pro-Rata / Ref) | Desvio / Uso |",
                "| :--- | :---: | :---: | :---: |",
                f"| **Trades Fechados** | {tot['live_trades']} | {tot['bt_trades']} (212d) | — |",
                f"| **Resultado Liquido** | **R$ {tot['live_net_brl']:+.2f}** | R$ {tot['bt_prorata_brl']:+.2f} (`BT 212d: R$ {tot['bt_net_brl']:,.2f}`) | **R$ {tot['desvio_brl']:+.2f}** ({desvio_pct_str}) |",
                f"| **Win Rate** | {tot['live_wr_pct']:.1f}% | {tot['bt_wr_pct']:.1f}% | {tot['wr_diff_pp']:+.1f} pp |" if tot["wr_diff_pp"] is not None else f"| **Win Rate** | {tot['live_wr_pct']:.1f}% | {tot['bt_wr_pct']:.1f}% | — |",
                f"| **Profit Factor** | {tot['live_pf']:.2f} | {tot['bt_pf']:.2f} | {tot['pf_diff']:+.2f} |" if tot["pf_diff"] is not None else f"| **Profit Factor** | {tot['live_pf']:.2f} | {tot['bt_pf']:.2f} | — |",
                f"| **MaxDD** | R$ {tot['live_max_dd_brl']:.2f} (atual R$ {tot['live_curr_dd_brl']:.2f}) | R$ {tot['bt_max_dd_brl']:.2f} | **{tot['dd_used_pct']:.1f}%** |",
                f"| **Loss Streak** | atual {tot['live_curr_loss_streak']} / max {tot['live_max_loss_streak']} | max BT {tot['bt_max_loss_streak']} | {tot['streak_used_pct']:.1f}% |",
                "",
            ]
        )

    lines.append("## Alertas")
    lines.append("")
    if rep["alerts"]:
        for a in rep["alerts"]:
            lines.append(f"- **[{a['severity']}] `{a['code']}` ({a['target']}):** {a['message']}")
    else:
        lines.append("- Nenhum alerta critico ou de atencao detectado.")
    lines.append("")

    lines.extend(
        [
            "## Comparativo por Robo e Subtotais (Live vs BT Pro-Rata)",
            "",
            "| Codigo | Magic | Trades (L/BT) | Live Net (R$) | BT Pro-Rata (R$) | Desvio (R$) | WR (L/BT) | PF (L/BT) | MaxDD (L/BT) | DD Uso% | Streak (Atu/Max/BT) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for r in rep["rows"]:
        magic_s = str(r["magic"]) if r["magic"] > 0 else "—"
        wr_s = f"{r['live_wr_pct']:.1f}%/{r['bt_wr_pct']:.1f}%" if r["live_trades"] > 0 else f"--/{r['bt_wr_pct']:.1f}%"
        pf_s = f"{r['live_pf']:.2f}/{r['bt_pf']:.2f}" if r["live_trades"] > 0 else f"--/{r['bt_pf']:.2f}"
        lines.append(
            f"| **{r['code']}** | {magic_s} | {r['live_trades']}/{r['bt_trades']} | "
            f"{r['live_net_brl']:+.2f} | {r['bt_prorata_brl']:+.2f} | {r['desvio_brl']:+.2f} | "
            f"{wr_s} | {pf_s} | {r['live_max_dd_brl']:.0f}/{r['bt_max_dd_brl']:.0f} | "
            f"{r['dd_used_pct']:.1f}% | {r['live_curr_loss_streak']}/{r['live_max_loss_streak']}/{r['bt_max_loss_streak']} |"
        )
    lines.append("")

    # Stop Diario
    lines.append("## Auditoria de Stop Diario (`jumba_daily_stop_state`)")
    lines.append("")
    if stop.get("exists") and not stop.get("empty"):
        status_stop = "CONFORME" if stop["limits_match_expected"] else "DIVERGENTE"
        lines.extend(
            [
                f"- **Status:** `{status_stop}` | `enabled={stop['enabled']}` | `updated_at={stop['updated_at']}` | `day_key={stop['day_key']}`",
                f"- **Limites Configurados:** Global `R$ {stop['limit_global']:.2f}` | WIN `R$ {stop['limit_win']:.2f}` | WDO `R$ {stop['limit_wdo']:.2f}` (Esperado: `G 950 / W 400 / D 0`)",
                f"- **Travas Hoje:** Global `{stop['stop_global_hit']}` | WIN `{stop['stop_win_hit']}` | WDO `{stop['stop_wdo_hit']}`",
            ]
        )
    else:
        lines.append("- Arquivo de estado de stop diario ausente ou vazio.")
    if rep["daily_stop_events"]:
        lines.append(f"- **Eventos de Stop registrados ({len(rep['daily_stop_events'])}):**")
        for ev in rep["daily_stop_events"]:
            lines.append(
                f"  - `{ev.get('time')}` | escopo `{ev.get('scope')}` | limite `R$ {ev.get('limit_brl')}` | "
                f"pnl `R$ {ev.get('pnl_brl')}` | mae `R$ {ev.get('mae_brl')}`"
            )
    lines.append("")

    # PnL Diario & Concentracao
    lines.append("## PnL Diario por Pregao & Concentracao (`deals` Top 10 vs `audit`)")
    lines.append("")
    if deals.get("exists"):
        d_top = deals["top10_summary"]
        d_all = deals["all_summary"]
        lines.append(
            f"- **Deals CSV (`jumba_live_deals_{login}.csv`):** {deals['out_deals_top10']} OUT deals Top 10 "
            f"(soma **R$ {d_top['total_net_brl']:+.2f}**) + {deals['non_top10_out_deals']} OUT deals fora do Top 10 "
            f"(total bruto todos magics: **R$ {d_all['total_net_brl']:+.2f}**)."
        )
        if d_top.get("best_day"):
            share_s = f"{d_top['best_day_share_of_net_pct']:.1f}% do liquido" if d_top["best_day_share_of_net_pct"] is not None else "liquido negativo"
            lines.append(
                f"- **Concentracao Top 10:** Melhor dia `{d_top['best_day']['date']}` = **R$ {d_top['best_day']['pnl_brl']:+.2f}** ({share_s}) | "
                f"Pior dia `{d_top['worst_day']['date']}` = **R$ {d_top['worst_day']['pnl_brl']:+.2f}** | "
                f"Resultado sem o melhor dia = **R$ {d_top['net_ex_best_day_brl']:+.2f}**"
            )
    if audit.get("exists"):
        a_top = audit["top10_summary"]
        a_all = audit["all_summary"]
        lines.append(
            f"- **Audit CSV (`jumba_live_trades_audit_{login}.csv`):** {audit['total_trades']} registros "
            f"(Top 10: {audit['top10_trades']}, soma Top 10 R$ {a_top['total_net_brl']:+.2f}, soma total R$ {a_all['total_net_brl']:+.2f}; "
            f"saidas: `{audit['exit_reasons']}`)."
        )

    if deals.get("exists") and deals["all_summary"]["daily_series"]:
        top10_map = {x["date"]: x["pnl_brl"] for x in deals["top10_summary"]["daily_series"]}
        all_map = {x["date"]: x["pnl_brl"] for x in deals["all_summary"]["daily_series"]}
        audit_map = (
            {x["date"]: x["pnl_brl"] for x in audit["top10_summary"]["daily_series"]}
            if audit.get("exists")
            else {}
        )
        lines.extend(
            [
                "",
                "| Data | Deals Top 10 (R$) | Deals Todos (R$) | Audit Top 10 (R$) |",
                "| :--- | :---: | :---: | :---: |",
            ]
        )
        for day in sorted(set(top10_map) | set(all_map) | set(audit_map)):
            lines.append(
                f"| {day} | {top10_map.get(day, 0.0):+.2f} | {all_map.get(day, 0.0):+.2f} | {audit_map.get(day, 0.0):+.2f} |"
            )
    lines.append("")

    # State Files
    lines.extend(
        [
            "## Auditoria dos State Files (Top 10)",
            "",
            f"- **Presentes:** {state['top10_present_count']}/10 | **Atualizados (<=2d do mais recente `{state['top10_latest_mtime']}`):** {state['top10_recent_count']}/10",
            f"- **State files legados (fora do Top 10):** `{state['legacy_state_magics']}`",
            "",
            "| Robo | Magic | Ativo | Contrato | Data Interna | Ultima Modificacao | Status |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for st in state["top10_states"]:
        status_s = "OK" if (st["has_state"] and st["is_recent"]) else ("AUSENTE" if not st["has_state"] else "DEFASADO")
        lines.append(
            f"| {st['code']} | {st['magic']} | {st['asset']} | {st['symbol'] or '—'} | "
            f"{st['state_date'] or '—'} | {st['mtime'] or '—'} | {status_s} |"
        )
    lines.append("")

    return "\n".join(lines)


def print_terminal_summary(rep: Dict[str, Any]) -> None:
    """Imprime resumo objetivo no terminal."""
    login = rep["login"]
    sess = rep["sessions"]
    tot = rep["total_summary"]
    stop = rep["daily_stop"]
    state = rep["state_files"]

    print("=" * 78)
    print(f"[RECONCILE MT5 vs BT] Conta {login} | Pregoes={sess['n_pregoes_live']} ({sess['date_min']} -> {sess['date_max']})")
    if tot:
        desvio_pct_s = f"{tot['desvio_pct']:+.1f}%" if tot["desvio_pct"] is not None else "n/a"
        print(
            f"  TOTAL Top 10: Trades={tot['live_trades']} | Live=R$ {tot['live_net_brl']:+.2f} | "
            f"BT Pro-Rata ({sess['n_pregoes_live']}/212d)=R$ {tot['bt_prorata_brl']:+.2f} | "
            f"Desvio=R$ {tot['desvio_brl']:+.2f} ({desvio_pct_s})"
        )
        print(
            f"  Metricas    : WR={tot['live_wr_pct']:.1f}% (BT {tot['bt_wr_pct']:.1f}%) | "
            f"PF={tot['live_pf']:.2f} (BT {tot['bt_pf']:.2f}) | "
            f"MaxDD=R$ {tot['live_max_dd_brl']:.0f}/{tot['bt_max_dd_brl']:.0f} ({tot['dd_used_pct']:.1f}%) | "
            f"Streak={tot['live_curr_loss_streak']}/{tot['live_max_loss_streak']} (BT {tot['bt_max_loss_streak']})"
        )
    else:
        print("  [AVISO] Linha TOTAL ausente no monitor CSV.")

    if stop.get("exists") and not stop.get("empty"):
        ok_txt = "OK" if stop["limits_match_expected"] else "DIVERGENTE"
        print(
            f"  Stop Diario : [{ok_txt}] enabled={stop['enabled']} | "
            f"G={stop['limit_global']:.0f} / W={stop['limit_win']:.0f} / D={stop['limit_wdo']:.0f} "
            f"(esperado 950/400/0)"
        )
    else:
        print("  Stop Diario : [AUSENTE]")

    print(
        f"  State Files : {state['top10_present_count']}/10 presentes | "
        f"{state['top10_recent_count']}/10 recentes (ref {state['top10_latest_mtime']})"
    )

    if rep["alerts"]:
        print(f"  Alertas ({len(rep['alerts'])}):")
        for a in rep["alerts"]:
            print(f"    - [{a['severity']}] {a['code']} ({a['target']}): {a['message']}")
    else:
        print("  Alertas (0): nenhum.")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcilia resultados Live MT5 vs Backtest (Jumba Top 10).")
    parser.add_argument("--common-dir", default=DEFAULT_COMMON_DIR, help="Diretorio Common\\Files do MetaQuotes MT5.")
    parser.add_argument("--login", default=DEFAULT_LOGIN, help=f"Numero da conta MT5 (padrao: {DEFAULT_LOGIN}).")
    parser.add_argument("--all", action="store_true", help="Executa para as contas 2004051 e 62033102.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help=f"Diretorio de saida (padrao: {DEFAULT_OUT_DIR}).")
    parser.add_argument("--bt-days", type=float, default=BT_DAYS_DEFAULT, help="Total de pregoes do BT base (padrao: 212).")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = parse_args(argv)
    logins = list(ALL_LOGINS) if args.all else [str(args.login).strip()]
    common_dir = os.path.expandvars(args.common_dir)
    os.makedirs(args.out_dir, exist_ok=True)
    today_tag = datetime.now().strftime("%Y-%m-%d")

    for login in logins:
        rep = reconcile_login(common_dir=common_dir, login=login, bt_days=args.bt_days)
        md_path = os.path.join(args.out_dir, f"reconcile_{login}_{today_tag}.md")
        json_path = os.path.join(args.out_dir, f"reconcile_{login}_{today_tag}.json")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(render_markdown(rep))
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)

        print_terminal_summary(rep)
        print(f"  Relatorios  : {md_path} | {json_path}")

    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
