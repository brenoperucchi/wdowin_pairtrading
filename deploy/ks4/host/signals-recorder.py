#!/usr/bin/env python3
"""Registro append-only dos sinais que o motor mostra AO VIVO (somente leitura).

Objetivo: provar, no fim do dia, o que foi emitido durante o pregao e comparar com o recalculo do dia
(a API de datas passadas e recalculada). Nao altera nada no motor.

Roda uma vez por minuto (timer de usuario). Pergunta ao server.py do mt5-a por /api/compass/etapa1?lite=1
(sem data = ao vivo) e grava em ~/signals-live/AAAA-MM-DD.jsonl:
  - linha "snap"  quando o signals_log de um ativo MUDA (o log inteiro, com hash), e
  - linha "hb"    a cada 5 minutos (so contagem, fonte e ultimo preco), para provar que o coletor estava rodando.
Nunca reescreve nem apaga linhas. So grava dentro do pregao (BRT 09:00 a 18:40, dias uteis), salvo --force.

Variaveis: MW_SIGNALS_OUT (pasta de saida, padrao ~/signals-live), MW_SIGNALS_CONTAINER (padrao mt5-a).
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")
OUT = os.environ.get("MW_SIGNALS_OUT", os.path.expanduser("~/signals-live"))
CONTAINER = os.environ.get("MW_SIGNALS_CONTAINER", "mt5-a")
ASSETS = ("WIN", "WDO")
FETCH = (
    "import urllib.request;print(urllib.request.urlopen("
    "'http://127.0.0.1:8080/api/compass/etapa1?lite=1',timeout=45).read().decode())"
)


def market_open(now):
    if now.weekday() >= 5:
        return False
    m = now.hour * 60 + now.minute
    return 9 * 60 <= m <= 18 * 60 + 40


def fetch():
    env = dict(os.environ, XDG_RUNTIME_DIR="/run/user/%d" % os.getuid())
    r = subprocess.run(["podman", "exec", CONTAINER, "python3", "-c", FETCH],
                       capture_output=True, text=True, timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError("podman exec falhou: " + r.stderr[-200:])
    return json.loads(r.stdout)


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def last_hashes(path):
    """Ultimo hash gravado por ativo, para nao repetir linhas iguais."""
    seen = {}
    if not os.path.exists(path):
        return seen
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("k") == "snap":
                seen[d["asset"]] = d["hash"]
    return seen


def append(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8"))
    finally:
        os.close(fd)


def main():
    force = "--force" in sys.argv
    now = datetime.now(timezone.utc).astimezone(BRT)
    if not force and not market_open(now):
        return 0
    path = os.path.join(OUT, now.strftime("%Y-%m-%d") + ".jsonl")
    base = {"ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "ts_brt": now.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        j = fetch()
    except Exception as e:  # registra a falha e sai sem erro (nao derruba o timer)
        append(path, [dict(base, k="erro", msg=str(e)[:200])])
        return 0
    seen = last_hashes(path)
    rows = []
    for a in ASSETS:
        d = j.get(a) or {}
        ca = d.get("caminho_a") or {}
        log = ca.get("signals_log")
        if log is None:
            continue
        info = {"asset": a, "source": d.get("source"), "is_historical": j.get("is_historical"),
                "session_date": d.get("session_date"), "last_price": d.get("last_price"), "n": len(log)}
        h = digest(log)
        if seen.get(a) != h:
            rows.append(dict(base, k="snap", hash=h, signals=log,
                             scorecard=ca.get("signals_scorecard"), **info))
        elif now.minute % 5 == 0:
            rows.append(dict(base, k="hb", hash=h, **info))
    if rows:
        append(path, rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
