# -*- coding: utf-8 -*-
"""
Assistente simples de linha de comando / duplo clique para criar ou atualizar
assinantes e administradores no Cloud SaaS MagicWalls via API Admin.

Lê MW_CLOUD_API_URL e MW_ADMIN_API_KEY automaticamente de cloud_saas/.env.
Nunca imprime a chave administrativa nem a senha informada.
"""

from __future__ import annotations

import argparse
from getpass import getpass
import os
import sys

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VALID_PLANS = ("admin", "pro", "core", "quant", "trial")


def _load_env(env_file: str | None = None) -> None:
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


def _prompt_non_empty(label: str) -> str:
    while True:
        val = input(label).strip()
        if val:
            return val
        print("Campo obrigatório. Tente novamente.")


def main(argv: list[str] | None = None) -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Criar ou atualizar usuário SaaS MagicWalls.")
    parser.add_argument("--email", help="E-mail de acesso do usuário")
    parser.add_argument("--password", help="Senha inicial do usuário")
    parser.add_argument("--name", default="", help="Nome completo do usuário")
    parser.add_argument("--plan", choices=VALID_PLANS, help="Plano: admin, pro, core, quant ou trial")
    parser.add_argument("--days", type=int, default=None, help="Dias de validade da assinatura (padrão 30)")
    parser.add_argument("--mt5-login", type=int, default=None, help="Número da conta MT5 (opcional, para plano quant)")
    parser.add_argument("--cloud-url", default=os.environ.get("MW_CLOUD_API_URL", "https://api.magicwalls.com.br"))
    args = parser.parse_args(argv)

    admin_key = os.environ.get("MW_ADMIN_API_KEY", "").strip()
    cloud_url = args.cloud_url.strip().rstrip("/")
    if not admin_key:
        print("ERRO: MW_ADMIN_API_KEY não encontrado em cloud_saas/.env nem no ambiente.")
        return 1

    print("=== Cadastro de Usuário SaaS MagicWalls ===")
    print(f"API Cloud alvo: {cloud_url}")

    email = (args.email or _prompt_non_empty("E-mail do assinante/admin: ")).strip().lower()
    password = args.password if args.password is not None else getpass("Senha (não aparece ao digitar): ").strip()
    if not password:
        print("ERRO: A senha não pode ficar vazia.")
        return 1

    full_name = args.name
    if not args.email:
        full_name = input("Nome completo (opcional, Enter para pular): ").strip()

    plan = args.plan
    if not plan:
        raw_plan = input(f"Plano [{' / '.join(VALID_PLANS)}] (padrão pro): ").strip().lower() or "pro"
        if raw_plan not in VALID_PLANS:
            print(f"Plano inválido '{raw_plan}'. Usando 'pro'.")
            raw_plan = "pro"
        plan = raw_plan

    days = args.days
    if days is None:
        if args.email:
            days = 365 if plan == "admin" else 30
        else:
            default_days = 365 if plan == "admin" else 30
            raw_days = input(f"Dias de acesso (padrão {default_days}): ").strip()
            try:
                days = int(raw_days) if raw_days else default_days
            except ValueError:
                days = default_days

    mt5_login = args.mt5_login
    if mt5_login is None and plan == "quant" and not args.email:
        raw_mt5 = input("Número da conta MT5 (Enter para deixar em branco): ").strip()
        if raw_mt5.isdigit():
            mt5_login = int(raw_mt5)

    payload = {
        "email": email,
        "password": password,
        "full_name": full_name,
        "plan": plan,
        "status": "active",
        "days": days,
        "mt5_account_login": mt5_login,
    }

    try:
        resp = httpx.post(
            f"{cloud_url}/api/v1/admin/users",
            json=payload,
            headers={"X-Admin-Key": admin_key, "Content-Type": "application/json"},
            timeout=15.0,
        )
    except Exception as exc:
        print(f"ERRO de conexão com {cloud_url}: {exc}")
        return 1

    if resp.status_code != 200:
        print(f"ERRO HTTP {resp.status_code}: {resp.text[:300]}")
        return 1

    data = resp.json()
    u = data.get("user") or {}
    print("\n[OK] Usuário salvo na nuvem com sucesso!")
    print(f"  ID     : {u.get('id')}")
    print(f"  E-mail : {u.get('email')}")
    print(f"  Plano  : {str(u.get('plan', '')).upper()}")
    print(f"  Status : {u.get('status')}")
    print(f"  Expira : {u.get('expires_at')}")
    if data.get("mt5_license_token"):
        print("  MT5    : Licença QUANT gerada no servidor (consulte o painel Admin para visualizar).")
    print("\nAgora acesse https://app.magicwalls.com.br (ou https://magicwalls-app.pages.dev) com esse e-mail e senha.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
