# -*- coding: utf-8 -*-
"""
Verificador CLI das conexões Cloud SaaS MagicWalls:
1. Supabase PostgREST (6 tabelas: profiles, subscriptions, active_sessions, terms_acceptance, audit_logs, producer_heartbeats)
2. Upstash Redis REST (SET -> GET -> DEL)
3. Cloud API (/health e /api/v1/feed/status)

Lê credenciais exclusivamente de variáveis de ambiente e nunca imprime segredos.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from typing import Any

import httpx

REQUIRED_SUPABASE_TABLES = (
    "profiles",
    "subscriptions",
    "active_sessions",
    "terms_acceptance",
    "audit_logs",
    "producer_heartbeats",
)


def check_supabase(
    supabase_url: str,
    service_role_key: str,
    timeout: float = 8.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if not supabase_url or not service_role_key:
        return {
            "configured": False,
            "ok": False,
            "detail": "SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY não configurados.",
            "tables": {},
        }

    base = f"{supabase_url.rstrip('/')}/rest/v1"
    clean_key = service_role_key.strip()
    headers = {
        "apikey": clean_key,
        "Accept": "application/json",
    }
    # Chaves novas do Supabase (sb_secret_*) são opacas e não devem ir em Authorization: Bearer.
    if clean_key and not clean_key.startswith("sb_"):
        headers["Authorization"] = f"Bearer {clean_key}"
    own_client = client is None
    http = client or httpx.Client(timeout=timeout, headers=headers)
    tables_status: dict[str, dict[str, Any]] = {}
    all_ok = True
    try:
        for table in REQUIRED_SUPABASE_TABLES:
            try:
                r = http.get(f"{base}/{table}", params={"select": "*", "limit": "1"}, headers=headers)
                ok = r.status_code == 200
                tables_status[table] = {"ok": ok, "status_code": r.status_code}
                if not ok:
                    all_ok = False
            except Exception as exc:
                tables_status[table] = {"ok": False, "error": str(exc)}
                all_ok = False
    finally:
        if own_client:
            http.close()

    missing = [t for t, info in tables_status.items() if not info.get("ok")]
    detail = "6/6 tabelas acessíveis." if all_ok else f"Tabelas com falha: {', '.join(missing)}"
    return {
        "configured": True,
        "ok": all_ok,
        "detail": detail,
        "tables": tables_status,
    }


def check_upstash(
    rest_url: str,
    rest_token: str,
    timeout: float = 6.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if not rest_url or not rest_token:
        return {
            "configured": False,
            "ok": False,
            "detail": "UPSTASH_REDIS_REST_URL ou UPSTASH_REDIS_REST_TOKEN não configurados.",
        }

    url = rest_url.rstrip("/")
    headers = {"Authorization": f"Bearer {rest_token}", "Content-Type": "application/json"}
    probe_key = "__mw_verify_probe__"
    probe_val = f"probe-{secrets.token_hex(8)}"
    own_client = client is None
    http = client or httpx.Client(timeout=timeout, headers=headers)
    try:
        r_set = http.post(url, json=["SET", probe_key, probe_val, "EX", 30], headers=headers)
        r_set.raise_for_status()
        r_get = http.post(url, json=["GET", probe_key], headers=headers)
        r_get.raise_for_status()
        got = (r_get.json() or {}).get("result")
        r_del = http.post(url, json=["DEL", probe_key], headers=headers)
        r_del.raise_for_status()
        ok = got == probe_val
        return {
            "configured": True,
            "ok": ok,
            "detail": "SET/GET/DEL roundtrip OK." if ok else f"Valor divergente no GET: {got!r}",
        }
    except Exception as exc:
        return {"configured": True, "ok": False, "detail": f"Erro Upstash: {exc}"}
    finally:
        if own_client:
            http.close()


def check_cloud_api(
    api_url: str,
    timeout: float = 8.0,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if not api_url:
        return {
            "configured": False,
            "ok": False,
            "detail": "MW_CLOUD_API_URL não configurada.",
        }

    base = api_url.rstrip("/")
    own_client = client is None
    http = client or httpx.Client(timeout=timeout)
    try:
        r_health = http.get(f"{base}/health")
        r_health.raise_for_status()
        h_json = r_health.json()
        r_feed = http.get(f"{base}/api/v1/feed/status")
        r_feed.raise_for_status()
        f_json = r_feed.json()
        ok = bool(h_json.get("ok")) and bool(f_json.get("ok"))
        return {
            "configured": True,
            "ok": ok,
            "db_backend": h_json.get("db_backend"),
            "store_backend": h_json.get("store_backend"),
            "feed_status": f_json.get("status"),
            "detail": (
                f"/health OK (db={h_json.get('db_backend')}, store={h_json.get('store_backend')}, "
                f"feed={f_json.get('status')})"
            ),
        }
    except Exception as exc:
        return {"configured": True, "ok": False, "detail": f"Erro Cloud API: {exc}"}
    finally:
        if own_client:
            http.close()


def run_all_checks(
    require_all: bool = False,
    timeout: float = 8.0,
) -> tuple[int, dict[str, dict[str, Any]]]:
    sb = check_supabase(
        os.environ.get("SUPABASE_URL", "").strip(),
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip(),
        timeout=timeout,
    )
    up = check_upstash(
        os.environ.get("UPSTASH_REDIS_REST_URL", "").strip(),
        os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip(),
        timeout=timeout,
    )
    api = check_cloud_api(
        os.environ.get("MW_CLOUD_API_URL", "").strip(),
        timeout=timeout,
    )

    results = {"supabase": sb, "upstash": up, "cloud_api": api}
    failed = False
    for name, res in results.items():
        if res["configured"]:
            if not res["ok"]:
                failed = True
        elif require_all:
            failed = True
    return (1 if failed else 0), results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verifica conexões Cloud SaaS MagicWalls.")
    parser.add_argument(
        "--require-all",
        action="store_true",
        help="Falha caso alguma camada (Supabase, Upstash, Cloud API) não esteja configurada.",
    )
    parser.add_argument("--timeout", type=float, default=8.0, help="Timeout HTTP em segundos (padrão 8.0).")
    args = parser.parse_args(argv)

    code, results = run_all_checks(require_all=args.require_all, timeout=args.timeout)
    print("=== Verificador de Conexões Cloud SaaS MagicWalls ===")
    for name in ("supabase", "upstash", "cloud_api"):
        res = results[name]
        if not res["configured"]:
            tag = "MISSING" if args.require_all else "SKIPPED"
        else:
            tag = "OK" if res["ok"] else "FAIL"
        print(f"[{tag:7s}] {name:10s} -> {res['detail']}")
        if name == "supabase" and res.get("tables"):
            for tbl, info in res["tables"].items():
                t_tag = "OK" if info.get("ok") else "FAIL"
                extra = info.get("status_code") or info.get("error") or ""
                print(f"          - {tbl:20s}: {t_tag} ({extra})")
    return code


if __name__ == "__main__":
    sys.exit(main())
