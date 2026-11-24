# -*- coding: utf-8 -*-
"""
CLI Administrativo do Funil de Trials (15 Dias) MagicWalls.

Lê MW_CLOUD_API_URL e MW_ADMIN_API_KEY automaticamente de cloud_saas/.env
(ou variáveis de ambiente) e nunca imprime segredos.

Exemplos de uso:
  python scripts/gerenciar_trials.py status
  python scripts/gerenciar_trials.py export --out leads_trials.csv
  python scripts/gerenciar_trials.py extend --id 12 --days 7
  python scripts/gerenciar_trials.py invites
  python scripts/gerenciar_trials.py invite-create --code IG15 --days 15 --max-uses 25 --label "Bio Instagram"
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from typing import Any, Optional

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _load_env(env_file: Optional[str] = None) -> None:
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


def _request_api(
    method: str,
    cloud_url: str,
    path: str,
    admin_key: str = "",
    json_body: Optional[dict[str, Any]] = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any]]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if admin_key:
        headers["X-Admin-Key"] = admin_key
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    url = f"{cloud_url.rstrip('/')}{path}"
    resp = httpx.request(method, url, headers=headers, json=json_body, timeout=timeout)
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text[:400]}
    return resp.status_code, body


def _fmt_dt(raw: Optional[str]) -> str:
    if not raw:
        return "-"
    return str(raw).replace("T", " ")[:16]


def _cmd_status(cloud_url: str, admin_key: str) -> int:
    code_pub, pub = _request_api("GET", cloud_url, "/api/v1/public/trial-config")
    code_adm, rep = _request_api("GET", cloud_url, "/api/v1/admin/trials", admin_key=admin_key)
    if code_adm != 200 or not rep.get("ok"):
        print(f"ERRO HTTP {code_adm} ao consultar /api/v1/admin/trials: {rep}")
        return 1

    summary = rep.get("summary") or {}
    trials = rep.get("trials") or []
    waitlist = rep.get("waitlist") or []
    invites = rep.get("invites") or []

    print("=== Funil de Trials MagicWalls ===")
    print(f"API Cloud : {cloud_url}")
    if code_pub == 200 and pub.get("ok"):
        slots = pub.get("slots_remaining")
        slots_txt = "ilimitado" if slots is None else f"{slots} restantes (teto {pub.get('max_active')})"
        print(
            f"Config    : modo={pub.get('mode')} | dias={pub.get('trial_days')} | "
            f"aceitando={'SIM' if pub.get('accepting_trials') else 'NAO'} | vagas={slots_txt}"
        )

    print(
        f"Resumo    : total={summary.get('total_trials', 0)} | "
        f"ativos={summary.get('active_trials', 0)} | "
        f"expirando_3d={summary.get('expiring_3d', 0)} | "
        f"expirados={summary.get('expired_trials', 0)} | "
        f"convertidos={summary.get('converted_trials', 0)} | "
        f"sem_login={summary.get('never_logged_in', 0)}"
    )
    print(
        f"Leads     : waitlist={summary.get('waitlist_count', 0)} | "
        f"intencao_pagamento={summary.get('conversion_intents_count', 0)} | "
        f"convites={len(invites)}"
    )

    if trials:
        print("\n--- Trials (mais recentes primeiro) ---")
        print(f"{'ID':>4}  {'Nome':22}  {'E-mail':26}  {'WhatsApp':15}  {'Status':9}  {'Rest':>4}  {'Ultimo Login':16}  {'Origem':12}")
        print("-" * 120)
        for t in trials:
            dleft = "-" if t.get("days_left") is None else f"{t.get('days_left')}d"
            print(
                f"{str(t.get('id', '')):>4}  "
                f"{str(t.get('full_name') or '')[:22]:22}  "
                f"{str(t.get('email') or '')[:26]:26}  "
                f"{str(t.get('phone') or '-')[:15]:15}  "
                f"{str(t.get('status') or '')[:9]:9}  "
                f"{dleft:>4}  "
                f"{_fmt_dt(t.get('last_login_at')):16}  "
                f"{str(t.get('acquisition_source') or '-')[:12]:12}"
            )
    else:
        print("\nNenhum trial registrado até o momento.")

    if waitlist:
        print(f"\n--- Lista de Espera / Intenção ({len(waitlist)}) ---")
        for w in waitlist[:25]:
            print(
                f"  - {str(w.get('full_name') or '-')[:24]:24} | "
                f"{str(w.get('email') or '')[:28]:28} | "
                f"{str(w.get('phone') or '-')[:15]:15} | "
                f"origem={w.get('source') or '-'}"
            )
    return 0


def _cmd_export(cloud_url: str, admin_key: str, out_path: str, delimiter: str) -> int:
    code_adm, rep = _request_api("GET", cloud_url, "/api/v1/admin/trials", admin_key=admin_key)
    if code_adm != 200 or not rep.get("ok"):
        print(f"ERRO HTTP {code_adm} ao consultar /api/v1/admin/trials: {rep}")
        return 1

    trials = rep.get("trials") or []
    waitlist = rep.get("waitlist") or []

    abs_out = os.path.abspath(out_path)
    parent = os.path.dirname(abs_out)
    if parent:
        os.makedirs(parent, exist_ok=True)

    rows_written = 0
    with open(abs_out, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=delimiter)
        writer.writerow(
            [
                "tipo",
                "id",
                "nome",
                "email",
                "whatsapp",
                "plano",
                "status",
                "dias_restantes",
                "expira_em",
                "ultimo_login",
                "origem",
                "criado_em",
            ]
        )
        for t in trials:
            writer.writerow(
                [
                    "trial",
                    t.get("id", ""),
                    t.get("full_name", ""),
                    t.get("email", ""),
                    t.get("phone", ""),
                    t.get("plan", ""),
                    t.get("status", ""),
                    "" if t.get("days_left") is None else t.get("days_left"),
                    t.get("expires_at") or "",
                    t.get("last_login_at") or "",
                    t.get("acquisition_source") or "",
                    t.get("created_at") or "",
                ]
            )
            rows_written += 1
        for w in waitlist:
            writer.writerow(
                [
                    "waitlist",
                    w.get("id", ""),
                    w.get("full_name", ""),
                    w.get("email", ""),
                    w.get("phone", ""),
                    "",
                    "lead",
                    "",
                    "",
                    "",
                    w.get("source") or "",
                    w.get("created_at") or "",
                ]
            )
            rows_written += 1

    print(f"[OK] Exportados {rows_written} registros ({len(trials)} trials + {len(waitlist)} waitlist) para {abs_out}")
    return 0


def _cmd_extend(cloud_url: str, admin_key: str, user_id: int, days: int) -> int:
    code, body = _request_api(
        "POST",
        cloud_url,
        f"/api/v1/admin/users/{int(user_id)}/extend",
        admin_key=admin_key,
        json_body={"days": int(days)},
    )
    if code != 200 or not body.get("ok"):
        print(f"ERRO HTTP {code} ao estender usuário {user_id}: {body}")
        return 1
    u = body.get("user") or {}
    print(
        f"[OK] Trial/assinatura do usuário #{u.get('id')} ({u.get('email')}) estendido em +{days} dias. "
        f"Nova expiração: {u.get('expires_at')} ({u.get('trial_days_left')}d restantes)."
    )
    return 0


def _cmd_invites(cloud_url: str, admin_key: str) -> int:
    code, body = _request_api("GET", cloud_url, "/api/v1/admin/invites", admin_key=admin_key)
    if code != 200 or not body.get("ok"):
        print(f"ERRO HTTP {code} ao listar convites: {body}")
        return 1
    invites = body.get("invites") or []
    if not invites:
        print("Nenhum código de convite cadastrado.")
        return 0
    print(f"{'Codigo':16}  {'Label':24}  {'Dias':>4}  {'Usos':>10}  {'Ativo':5}  {'Expira':16}")
    print("-" * 85)
    for inv in invites:
        max_u = inv.get("max_uses")
        usos = f"{inv.get('used_count', 0)}/{max_u if max_u is not None else 'inf'}"
        print(
            f"{str(inv.get('code') or '')[:16]:16}  "
            f"{str(inv.get('label') or '-')[:24]:24}  "
            f"{int(inv.get('trial_days') or 15):>4}  "
            f"{usos:>10}  "
            f"{'SIM' if inv.get('is_active') else 'NAO':5}  "
            f"{_fmt_dt(inv.get('expires_at')):16}"
        )
    return 0


def _cmd_invite_create(
    cloud_url: str,
    admin_key: str,
    code_str: str,
    label: str,
    days: int,
    max_uses: Optional[int],
    expires_at: Optional[str],
    is_active: bool,
) -> int:
    code, body = _request_api(
        "POST",
        cloud_url,
        "/api/v1/admin/invites",
        admin_key=admin_key,
        json_body={
            "code": code_str,
            "label": label,
            "trial_days": int(days),
            "max_uses": max_uses,
            "expires_at": expires_at,
            "is_active": is_active,
        },
    )
    if code != 200 or not body.get("ok"):
        print(f"ERRO HTTP {code} ao salvar convite: {body}")
        return 1
    inv = body.get("invite") or {}
    print(
        f"[OK] Convite salvo: code={inv.get('code')} | dias={inv.get('trial_days')} | "
        f"max_uses={inv.get('max_uses')} | ativo={inv.get('is_active')}"
    )
    print(f"     Link direto: https://app.magicwalls.com.br/?trial=1&invite={inv.get('code')}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Gestão administrativa de Trials (15 dias) MagicWalls.")
    parser.add_argument(
        "--cloud-url",
        default=os.environ.get("MW_CLOUD_API_URL", "https://api.magicwalls.com.br"),
        help="URL base da Cloud API MagicWalls",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Exibe métricas do funil e lista de trials/waitlist (padrão)")

    p_exp = sub.add_parser("export", help="Exporta leads de trials e waitlist para CSV")
    p_exp.add_argument("--out", default="leads_trials.csv", help="Arquivo CSV de saída")
    p_exp.add_argument("--delimiter", default=",", help="Separador CSV (padrão ',')")

    p_ext = sub.add_parser("extend", help="Estende a validade de um usuário em +N dias")
    p_ext.add_argument("--id", type=int, required=True, help="ID numérico do usuário")
    p_ext.add_argument("--days", type=int, default=15, help="Dias extras a adicionar")

    sub.add_parser("invites", help="Lista códigos de convite cadastrados")

    p_ic = sub.add_parser("invite-create", help="Cria ou atualiza um código de convite")
    p_ic.add_argument("--code", required=True, help="Código do convite (ex.: IG15)")
    p_ic.add_argument("--label", default="", help="Descrição/campanha do convite")
    p_ic.add_argument("--days", type=int, default=15, help="Dias de trial para este convite")
    p_ic.add_argument("--max-uses", type=int, default=None, help="Limite máximo de usos")
    p_ic.add_argument("--expires-at", default=None, help="Data/hora ISO UTC de expiração do convite")
    p_ic.add_argument("--inactive", action="store_true", help="Salva o convite como inativo")

    args = parser.parse_args(argv)
    admin_key = os.environ.get("MW_ADMIN_API_KEY", "").strip()
    cloud_url = str(args.cloud_url or "").strip().rstrip("/")
    if not admin_key:
        print("ERRO: MW_ADMIN_API_KEY não encontrado em cloud_saas/.env nem no ambiente.")
        return 1

    cmd = args.command or "status"
    try:
        if cmd == "status":
            return _cmd_status(cloud_url, admin_key)
        if cmd == "export":
            return _cmd_export(cloud_url, admin_key, args.out, args.delimiter)
        if cmd == "extend":
            return _cmd_extend(cloud_url, admin_key, args.id, args.days)
        if cmd == "invites":
            return _cmd_invites(cloud_url, admin_key)
        if cmd == "invite-create":
            return _cmd_invite_create(
                cloud_url,
                admin_key,
                args.code,
                args.label,
                args.days,
                args.max_uses,
                args.expires_at,
                not args.inactive,
            )
    except Exception as exc:
        print(f"ERRO ao comunicar com {cloud_url}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
