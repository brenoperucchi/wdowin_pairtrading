# -*- coding: utf-8 -*-
"""
Produtor Push da MagicWalls (PC Local / VPS Windows -> Cloud SaaS API).

Executa 1 única leitura periódica ao server.py local (127.0.0.1:8080),
gera os snapshots sanitizados CORE e PRO reutilizando os sanitizadores de
scripts/painel_publico.py, comprime com gzip, assina via HMAC-SHA256 e
empurra para a nuvem (<MW_CLOUD_API_URL>/internal/v1/push/snapshot).

Inclui:
- Failover automático Primary <-> Hot Standby (--role standby)
- Monitor de Heartbeat SLA 99,9% (alerta Telegram/Webhook se >15s sem push em 08:55-17:30)
"""

from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import hashlib
import json
import os
import socket
import sys
import time
from typing import Any, Optional

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cloud_saas.security import compute_push_signature, notify_admin_telegram
from scripts.painel_publico import _sanitize_etapa1, _sanitize_etapa1_5176

try:
    from core.div_engines_view import detect as _detect_engine_divs
except Exception:
    _detect_engine_divs = None

_WALLS_FLOW_6_IDS = {
    "WIN_DIV_WALL",
    "WDO_DIV_WALL",
    "ESP_DIV_V22_WIN",
    "C1a_BRK_WIN",
    "V1a_DIV_WDO",
    "SYM_DIV_WIN",
    "SYM_DIV_WDO",
}


def _attach_precomputed_divs(obj: Any, include_trades: bool = False) -> Any:
    """Embute as divergências oficiais V3.2 em WIN/WDO.caminho_a.engine_divs_v32.

    Garante exibição imediata no SaaS Cloud e no Card IG mesmo sem roundtrip extra
    no /api/compass/divergencias_motor.
    """
    if not isinstance(obj, dict) or _detect_engine_divs is None:
        return obj
    for sym in ("WIN", "WDO"):
        asset = obj.get(sym)
        if not isinstance(asset, dict):
            continue
        ca = asset.get("caminho_a")
        if not isinstance(ca, dict):
            continue
        raw_series = ca.get("m5_dealer_vs_flow_series") or []
        bars = [
            {
                "time": str(pt.get("time", ""))[:5],
                "open": float(pt.get("open", 0.0) or 0.0),
                "high": float(pt.get("high", 0.0) or 0.0),
                "low": float(pt.get("low", 0.0) or 0.0),
                "close": float(pt.get("close", 0.0) or 0.0),
                "wave": float(pt.get("smart_swing_wave", 0.0) or 0.0),
            }
            for pt in raw_series
            if isinstance(pt, dict) and not pt.get("is_prev_day") and pt.get("time")
        ]
        if len(bars) < 5:
            ca["engine_divs_v32"] = []
            continue
        walls = [
            {"type": w.get("type"), "price": float(w["price"])}
            for w in (asset.get("all_walls") or [])
            if isinstance(w, dict) and w.get("price") is not None
        ]
        trades = []
        if include_trades:
            for s in (ca.get("signals_log") or []):
                if (
                    isinstance(s, dict)
                    and not s.get("is_prev_day")
                    and s.get("time")
                    and str(s.get("strategy_id") or "") in _WALLS_FLOW_6_IDS
                ):
                    trades.append(
                        {
                            "strategy_id": s.get("strategy_id"),
                            "time": str(s.get("time"))[:5],
                            "direction": s.get("direction"),
                        }
                    )
        try:
            ca["engine_divs_v32"] = _detect_engine_divs(sym, bars, walls, "v3.2", trades=trades)
        except Exception:
            ca["engine_divs_v32"] = []
    return obj


def _is_b3_session_now(now_dt: Optional[datetime] = None) -> bool:
    dt = now_dt or datetime.now()
    if dt.weekday() >= 5:
        return False
    hm = dt.hour * 60 + dt.minute
    return (8 * 60 + 55) <= hm <= (17 * 60 + 30)


def _fetch_local_json(client: httpx.Client, url: str, timeout: float = 10.0) -> Optional[bytes]:
    try:
        resp = client.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        return None
    return None


def _decode_json_bytes(raw: Optional[bytes]) -> Optional[Any]:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


class HeartbeatMonitor:
    """Dispara alerta crítico se o feed ficar > stale_sec sem push durante o pregão."""

    def __init__(
        self,
        stale_sec: float = 15.0,
        cooldown_sec: float = 120.0,
        telegram_token: str = "",
        telegram_chat_id: str = "",
        alert_webhook_url: str = "",
        always_alert: bool = False,
    ) -> None:
        self.stale_sec = stale_sec
        self.cooldown_sec = cooldown_sec
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        self.alert_webhook_url = alert_webhook_url
        self.always_alert = always_alert
        self.last_ok_mono = time.monotonic()
        self.last_alert_mono = 0.0
        self.in_alert = False

    def _dispatch(self, text: str) -> None:
        if self.telegram_token and self.telegram_chat_id:
            notify_admin_telegram(self.telegram_token, self.telegram_chat_id, text)
        if self.alert_webhook_url:
            try:
                httpx.post(self.alert_webhook_url, json={"text": text}, timeout=3.0)
            except Exception:
                pass
        print(f"[HEARTBEAT_ALERT] {text}", flush=True)

    def mark_ok(self, producer_id: str) -> None:
        now = time.monotonic()
        if self.in_alert:
            self.in_alert = False
            self._dispatch(f"[MAGICWALLS RECUPERADO] Produtor {producer_id} voltou a enviar snapshots normalmente.")
        self.last_ok_mono = now

    def check(self, producer_id: str, last_error: str = "") -> None:
        now = time.monotonic()
        gap = now - self.last_ok_mono
        if gap <= self.stale_sec:
            return
        if not self.always_alert and not _is_b3_session_now():
            return
        if (now - self.last_alert_mono) < self.cooldown_sec:
            return
        self.in_alert = True
        self.last_alert_mono = now
        detail = f" Motivo: {last_error}" if last_error else ""
        self._dispatch(
            f"[CRÍTICO MAGICWALLS SLA] Produtor {producer_id} sem push há {gap:.0f}s (limite {self.stale_sec:.0f}s).{detail}"
        )


class CloudPublisher:
    """Coleta 1 leitura do backend local, sanitiza CORE/PRO e envia com HMAC para a nuvem."""

    def __init__(
        self,
        cloud_url: str,
        local_url: str,
        hmac_secret: str,
        producer_id: str,
        role: str = "primary",
        primary_failover_sec: float = 12.0,
        max_backfill_days: int = 25,
    ) -> None:
        self.cloud_url = cloud_url.rstrip("/")
        self.local_url = local_url.rstrip("/")
        self.hmac_secret = hmac_secret
        self.producer_id = producer_id
        self.role = role
        self.primary_failover_sec = primary_failover_sec
        self.max_backfill_days = max(1, int(max_backfill_days))
        self._local = httpx.Client(timeout=15.0)
        self._cloud = httpx.Client(timeout=15.0)
        _connect_ip = os.environ.get("MW_CLOUD_CONNECT_IP", "").strip()
        if _connect_ip:
            from urllib.parse import urlparse
            _cloud_host = urlparse(self.cloud_url).hostname

            def _route_to_ip(request, _ip=_connect_ip, _host=_cloud_host):
                if request.url.host == _host:
                    request.headers["Host"] = _host
                    request.extensions["sni_hostname"] = _host
                    request.url = request.url.copy_with(host=_ip)

            self._cloud = httpx.Client(timeout=15.0, event_hooks={"request": [_route_to_ip]})
        self._last_fetch_ts: dict[str, float] = {}
        self._cached_raw: dict[str, bytes] = {}
        self._day_cache_pushed_ts: dict[str, float] = {}
        self._last_sent_hashes: dict[str, str] = {}
        self._last_backfill_mono: float = 0.0
        self._last_standby_hb_ts = 0.0

    def close(self) -> None:
        self._local.close()
        self._cloud.close()

    def _fetch_throttled(self, key: str, path: str, ttl_sec: float, timeout: float = 12.0, force: bool = False) -> Optional[bytes]:
        now = time.monotonic()
        if not force and key in self._cached_raw and (now - self._last_fetch_ts.get(key, 0.0)) < ttl_sec:
            return self._cached_raw[key]
        data = _fetch_local_json(self._local, f"{self.local_url}{path}", timeout=timeout)
        if data is not None:
            self._cached_raw[key] = data
            self._last_fetch_ts[key] = now
            return data
        return self._cached_raw.get(key)

    @staticmethod
    def _has_compass_bars(obj: Any) -> bool:
        if not isinstance(obj, dict):
            return False
        for sym in ("WIN", "WDO"):
            bars = ((obj.get(sym) or {}).get("caminho_a") or {}).get("m5_dealer_vs_flow_series") or []
            if len(bars) > 0:
                return True
        return False

    def _prepare_day_pair(self, day_raw: bytes) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        pro_day = _decode_json_bytes(_sanitize_etapa1_5176(day_raw))
        if not self._has_compass_bars(pro_day):
            return None, None
        core_day = _decode_json_bytes(_sanitize_etapa1(day_raw))
        core_day = _attach_precomputed_divs(core_day, include_trades=False)
        pro_day = _attach_precomputed_divs(pro_day, include_trades=True)
        return core_day, pro_day

    def build_snapshots(self, force_all: bool = False, include_days: bool = True) -> dict[str, dict[str, Any]]:
        etapa1_lite_raw = self._fetch_throttled("etapa1_lite", "/api/compass/etapa1?lite=1", 2.0, timeout=15.0, force=force_all)
        etapa1_full_raw = self._fetch_throttled("etapa1_full", "/api/compass/etapa1", 60.0, timeout=25.0, force=force_all)
        m1_raw = self._fetch_throttled("m1_series", "/api/compass/m1_series", 20.0, timeout=12.0, force=force_all)
        regime_raw = self._fetch_throttled("regime", "/api/v2/regime", 5.0, timeout=8.0, force=force_all)
        perf_raw = self._fetch_throttled("performance", "/api/performance", 5.0, timeout=8.0, force=force_all)
        di_raw = self._fetch_throttled("di_regime", "/api/di-regime", 5.0, timeout=8.0, force=force_all)
        gex_raw = self._fetch_throttled("gex_walls", "/api/gex-walls", 15.0, timeout=8.0, force=force_all)
        hist_raw = self._fetch_throttled("history", "/api/history?days=30", 300.0, timeout=20.0, force=force_all)
        morning_brief_raw = self._fetch_throttled(
            "morning_brief",
            "/api/morning-brief",
            30.0,
            timeout=8.0,
            force=force_all,
        )

        core_lite = _attach_precomputed_divs(_decode_json_bytes(_sanitize_etapa1(etapa1_lite_raw)), include_trades=False) if etapa1_lite_raw else None
        core_full = _attach_precomputed_divs(_decode_json_bytes(_sanitize_etapa1(etapa1_full_raw)), include_trades=False) if etapa1_full_raw else None
        pro_lite = _attach_precomputed_divs(_decode_json_bytes(_sanitize_etapa1_5176(etapa1_lite_raw)), include_trades=True) if etapa1_lite_raw else None
        pro_full = _attach_precomputed_divs(_decode_json_bytes(_sanitize_etapa1_5176(etapa1_full_raw)), include_trades=True) if etapa1_full_raw else None
        m1_obj = _decode_json_bytes(m1_raw)

        core_map: dict[str, Any] = {
            "etapa1_lite": core_lite,
            "etapa1_full": core_full,
            "m1_series": m1_obj,
        }
        pro_map: dict[str, Any] = {
            "etapa1_lite": pro_lite,
            "etapa1_full": pro_full,
            "m1_series": m1_obj,
            "regime": _decode_json_bytes(regime_raw),
            "performance": _decode_json_bytes(perf_raw),
            "di_regime": _decode_json_bytes(di_raw),
            "gex_walls": _decode_json_bytes(gex_raw),
            "history": _decode_json_bytes(hist_raw),
        }

        if include_days:
            avail_dates = (pro_lite or core_lite or {}).get("available_dates") or []
            now_mono = time.monotonic()
            pushed_this_cycle = 0
            per_cycle_cap = 2 if not force_all else min(3, self.max_backfill_days)
            for idx, raw_d in enumerate(avail_dates[: max(30, self.max_backfill_days + 10)]):
                if idx >= self.max_backfill_days and len(self._day_cache_pushed_ts) >= self.max_backfill_days:
                    break
                if pushed_this_cycle >= per_cycle_cap:
                    break
                d = str(raw_d or "").strip()
                if len(d) != 10:
                    continue
                ttl_refresh = 300.0 if idx < 2 else 1800.0
                due = force_all or (d not in self._day_cache_pushed_ts) or ((now_mono - self._day_cache_pushed_ts[d]) >= ttl_refresh)
                if not due:
                    continue
                day_raw = self._fetch_throttled(
                    f"day_{d}",
                    f"/api/compass/etapa1?date_str={d}&lite=1",
                    ttl_refresh,
                    timeout=15.0,
                    force=force_all,
                )
                self._day_cache_pushed_ts[d] = now_mono
                if not day_raw:
                    continue
                core_day, pro_day = self._prepare_day_pair(day_raw)
                if core_day is None or pro_day is None:
                    continue
                core_map[f"etapa1_day_{d}"] = core_day
                pro_map[f"etapa1_day_{d}"] = pro_day
                pushed_this_cycle += 1

        return {
            "core": core_map,
            "pro": pro_map,
            "admin": {
                "morning_brief": _decode_json_bytes(morning_brief_raw),
            },
        }

    def _primary_is_healthy_in_cloud(self) -> bool:
        try:
            resp = self._cloud.get(f"{self.cloud_url}/api/v1/feed/status", timeout=4.0)
            if resp.status_code != 200:
                return False
            st = resp.json()
            age = st.get("age_sec")
            return (
                st.get("active_role") == "primary"
                and isinstance(age, (int, float))
                and age < self.primary_failover_sec
            )
        except Exception:
            return False

    def _post_snapshots_payload(
        self,
        snapshots: Optional[dict[str, dict[str, Any]]] = None,
        heartbeat_only: bool = False,
    ) -> tuple[bool, dict[str, Any]]:
        if heartbeat_only:
            payload: dict[str, Any] = {
                "producer_id": self.producer_id,
                "producer_role": self.role,
                "heartbeat_only": True,
                "pushed_at": time.time(),
            }
        else:
            payload = {
                "producer_id": self.producer_id,
                "producer_role": self.role,
                "pushed_at": time.time(),
                "snapshots": snapshots or {},
            }

        raw_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        gz_bytes = gzip.compress(raw_json, compresslevel=5)
        ts_str = str(int(time.time()))
        sig = compute_push_signature(self.hmac_secret, ts_str, self.producer_id, self.role, gz_bytes)

        headers = {
            "Content-Type": "application/json",
            "Content-Encoding": "gzip",
            "X-MW-Timestamp": ts_str,
            "X-MW-Producer-Id": self.producer_id,
            "X-MW-Producer-Role": self.role,
            "X-MW-Signature": sig,
        }
        resp = self._cloud.post(f"{self.cloud_url}/internal/v1/push/snapshot", content=gz_bytes, headers=headers)
        if resp.status_code != 200:
            return False, {"status_code": resp.status_code, "body": resp.text[:300]}
        return True, resp.json()

    def push_backfill_days(self, max_days: Optional[int] = None, batch_size: int = 3) -> dict[str, Any]:
        target_days = max(1, int(max_days if max_days is not None else self.max_backfill_days))
        lite_raw = self._fetch_throttled("etapa1_lite", "/api/compass/etapa1?lite=1", 2.0, timeout=15.0, force=True)
        lite_obj = _decode_json_bytes(lite_raw) or {}
        avail_dates = lite_obj.get("available_dates") or []
        collected: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        now_mono = time.monotonic()

        for raw_d in avail_dates[: max(45, target_days + 15)]:
            if len(collected) >= target_days:
                break
            d = str(raw_d or "").strip()
            if len(d) != 10:
                continue
            day_raw = self._fetch_throttled(
                f"day_{d}",
                f"/api/compass/etapa1?date_str={d}&lite=1",
                300.0,
                timeout=20.0,
                force=True,
            )
            self._day_cache_pushed_ts[d] = now_mono
            if not day_raw:
                continue
            core_day, pro_day = self._prepare_day_pair(day_raw)
            if core_day is None or pro_day is None:
                continue
            collected.append((d, core_day, pro_day))

        pushed_days: list[str] = []
        failed_batches: list[dict[str, Any]] = []
        step = max(1, int(batch_size))
        for i in range(0, len(collected), step):
            chunk = collected[i : i + step]
            snap_chunk = {
                "core": {f"etapa1_day_{d}": c_obj for d, c_obj, _ in chunk},
                "pro": {f"etapa1_day_{d}": p_obj for d, _, p_obj in chunk},
            }
            ok, res = self._post_snapshots_payload(snap_chunk, heartbeat_only=False)
            if ok:
                pushed_days.extend([d for d, _, _ in chunk])
            else:
                failed_batches.append({"days": [d for d, _, _ in chunk], "error": res})

        self._last_backfill_mono = time.monotonic()
        return {
            "ok": len(failed_batches) == 0,
            "requested_days": target_days,
            "populated_days": len(collected),
            "pushed_days": pushed_days,
            "failed_batches": failed_batches,
        }

    def push_once(self, force_all: bool = False) -> tuple[bool, dict[str, Any]]:
        heartbeat_only = False
        if self.role == "standby" and self._primary_is_healthy_in_cloud():
            now = time.monotonic()
            if (now - self._last_standby_hb_ts) < 10.0:
                return True, {"ok": True, "mode": "standby_sleeping"}
            self._last_standby_hb_ts = now
            heartbeat_only = True

        if heartbeat_only:
            return self._post_snapshots_payload(heartbeat_only=True)

        snapshots = self.build_snapshots(force_all=force_all, include_days=not force_all)
        if not force_all:
            changed_snapshots: dict[str, dict[str, Any]] = {}
            pending_hashes: dict[str, str] = {}
            for tier in ("core", "pro", "admin"):
                tier_map = snapshots.get(tier) or {}
                changed_tier: dict[str, Any] = {}
                for ep_name, ep_val in tier_map.items():
                    if ep_val is None:
                        continue
                    h_key = f"{tier}:{ep_name}"
                    digest = hashlib.sha256(
                        json.dumps(ep_val, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                    if self._last_sent_hashes.get(h_key) != digest:
                        changed_tier[ep_name] = ep_val
                        pending_hashes[h_key] = digest
                if changed_tier:
                    changed_snapshots[tier] = changed_tier
            if not changed_snapshots:
                ok, res = self._post_snapshots_payload(heartbeat_only=True)
            else:
                ok, res = self._post_snapshots_payload(changed_snapshots, heartbeat_only=False)
                if ok:
                    self._last_sent_hashes.update(pending_hashes)
        else:
            ok, res = self._post_snapshots_payload(snapshots, heartbeat_only=False)
            if ok:
                for tier in ("core", "pro", "admin"):
                    for ep_name, ep_val in (snapshots.get(tier) or {}).items():
                        if ep_val is not None:
                            self._last_sent_hashes[f"{tier}:{ep_name}"] = hashlib.sha256(
                                json.dumps(ep_val, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                            ).hexdigest()

        if (
            ok
            and isinstance(res, dict)
            and res.get("needs_backfill")
            and not force_all
            and (time.monotonic() - self._last_backfill_mono) >= 120.0
        ):
            self._last_backfill_mono = time.monotonic()
            self._last_sent_hashes.clear()
            bf_res = self.push_backfill_days(max_days=self.max_backfill_days, batch_size=3)
            print(f"[AUTO-BACKFILL] {bf_res}", flush=True)

        return ok, res


def _load_default_env(env_file: Optional[str] = None) -> None:
    """Carrega variáveis de cloud_saas/.env caso ainda não estejam definidas no ambiente."""
    path = env_file or os.path.join(ROOT, "cloud_saas", ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                key = k.strip()
                if key:
                    os.environ.setdefault(key, v.strip())
    except OSError:
        pass


def main() -> int:
    _load_default_env()
    parser = argparse.ArgumentParser(description="MagicWalls Cloud Push Publisher")
    parser.add_argument("--cloud-url", default=os.environ.get("MW_CLOUD_API_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--local-url", default=os.environ.get("MW_LOCAL_BACKEND_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--hmac-secret", default=os.environ.get("MW_PUSH_HMAC_SECRET", ""))
    parser.add_argument("--producer-id", default=os.environ.get("MW_PRODUCER_ID", socket.gethostname()))
    parser.add_argument("--role", choices=["primary", "standby"], default=os.environ.get("MW_PRODUCER_ROLE", "primary"))
    parser.add_argument("--interval", type=float, default=2.5)
    parser.add_argument("--stale-alert-sec", type=float, default=15.0)
    parser.add_argument("--backfill-days", type=int, default=25, help="Quantidade maxima de pregoes historicos enviados ao cache SaaS.")
    parser.add_argument("--once", action="store_true", help="Executa apenas 1 push completo e encerra.")
    parser.add_argument("--always-alert", action="store_true", help="Dispara alertas mesmo fora do horário do pregão.")
    args = parser.parse_args()

    if not args.hmac_secret:
        raise SystemExit("Erro: defina --hmac-secret ou a variável MW_PUSH_HMAC_SECRET.")

    publisher = CloudPublisher(
        cloud_url=args.cloud_url,
        local_url=args.local_url,
        hmac_secret=args.hmac_secret,
        producer_id=args.producer_id,
        role=args.role,
        max_backfill_days=args.backfill_days,
    )
    monitor = HeartbeatMonitor(
        stale_sec=args.stale_alert_sec,
        telegram_token=os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID", "").strip(),
        alert_webhook_url=os.environ.get("MW_ALERT_WEBHOOK_URL", "").strip(),
        always_alert=args.always_alert,
    )
    if not (monitor.telegram_token and monitor.telegram_chat_id) and not monitor.alert_webhook_url:
        print(
            "[CLOUD_PUBLISHER] AVISO: TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nao configurados em cloud_saas/.env — alertas de SLA serao registrados apenas em log.",
            flush=True,
        )

    try:
        if args.once:
            bf_res = publisher.push_backfill_days(max_days=args.backfill_days, batch_size=3)
            print(f"[BACKFILL] {bf_res}", flush=True)
            ok, res = publisher.push_once(force_all=True)
            print(f"[ONCE] ok={ok} res={res}", flush=True)
            return 0 if (ok and bf_res.get("ok")) else 1

        print(
            f"[CLOUD_PUBLISHER] {args.producer_id} ({args.role}) empurrando {args.local_url} -> {args.cloud_url} a cada {args.interval}s",
            flush=True,
        )
        while True:
            t0 = time.monotonic()
            last_err = ""
            try:
                ok, res = publisher.push_once(force_all=False)
                if ok:
                    monitor.mark_ok(args.producer_id)
                else:
                    last_err = str(res)
            except Exception as exc:
                last_err = str(exc)

            monitor.check(args.producer_id, last_error=last_err)
            elapsed = time.monotonic() - t0
            sleep_s = max(0.2, args.interval - elapsed)
            time.sleep(sleep_s)
    finally:
        publisher.close()


if __name__ == "__main__":
    raise SystemExit(main())
