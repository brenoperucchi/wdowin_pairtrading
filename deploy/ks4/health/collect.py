#!/usr/bin/env python3
"""Coletor de saude do Magic Walls no ks4 (somente leitura).

Roda a cada 30 s (timer de usuario do app) e grava:
  - health.json        (visao publica: estados, idades e frases curtas)
  - health-admin.json  (mesmos componentes + detalhes; para a tailnet)
na pasta de dados da API (/home/app/magicwalls-cloud/data, vista como /data no
container magicwalls-cloud). A API serve esses arquivos; este script nao abre
porta, nao reinicia nada e nao grava segredo.

Estados: ok | degraded | down | closed (fora do pregao) | unknown.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")
OUT = os.environ.get("MW_HEALTH_OUT", "/home/app/magicwalls-cloud/data")
STATE = os.environ.get("MW_HEALTH_STATE", "/home/app/health/state.json")
RTD = "/home/app/rtd-csv"
LOGS = ("/home/app/profit-wine/prefix/drive_c/users/mt5/AppData/Roaming/"
        "Nelogica/Scalper/Logs")
GEXDIR = "/home/app/mt5-wine-lab/prefix-a/drive_c/magicwalls/gex/data"
ASSETS = ("WINZ26", "WDOZ26")
OPEN_H, OPEN_M, CLOSE_H, CLOSE_M = 9, 5, 18, 25   # janela do pregao (BRT)
SEV = {"ok": 0, "closed": 0, "unknown": 1, "degraded": 2, "down": 3}

NOW = datetime.now(timezone.utc)
NOW_BRT = NOW.astimezone(BRT)
ENV = dict(os.environ, XDG_RUNTIME_DIR="/run/user/%d" % os.getuid())


def market_open():
    if NOW_BRT.weekday() >= 5:
        return False
    m = NOW_BRT.hour * 60 + NOW_BRT.minute
    return OPEN_H * 60 + OPEN_M <= m <= CLOSE_H * 60 + CLOSE_M


def run(cmd, timeout=8):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                          env=ENV)


def http_json(url, timeout=4):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode())


def parse_brt(s, fmt):
    return datetime.strptime(s, fmt).replace(tzinfo=BRT)


def age_from(dt):
    return max(0, int((NOW - dt.astimezone(timezone.utc)).total_seconds()))


def comp(status, summary, age=None, hint="", detail=None):
    c = {"status": status, "summary": summary}
    if age is not None:
        c["age_sec"] = age
    if hint and status not in ("ok", "closed"):
        c["hint"] = hint
    return c, (detail or {})


def safe(fn):
    try:
        return fn()
    except Exception as e:  # nunca derruba o coletor
        return comp("unknown", "nao foi possivel checar",
                    hint="coletor falhou nesta checagem",
                    detail={"erro": "%s: %s" % (type(e).__name__, e)})


# ---------------------------------------------------------------- componentes
def containers():
    names = ("profit-wine", "mt5-a", "magicwalls-cloud")
    out = run(["podman", "ps", "--format", "{{.Names}}"]).stdout.split()
    down = [n for n in names if n not in out]
    if down:
        return comp("down", "container fora do ar: " + ", ".join(down),
                    hint="systemctl --user start <container>",
                    detail={"fora": down})
    return comp("ok", "containers no ar", detail={"no_ar": list(names)})


def profit_app():
    today = NOW_BRT.strftime("%Y_%m_%d")
    f = os.path.join(LOGS, "LogDesktop_%s.log" % today)
    if not os.path.exists(f):
        cands = sorted(glob.glob(os.path.join(LOGS, "LogDesktop_*.log")))
        f = cands[-1] if cands else None
    if not f:
        return comp("down", "Scalper sem log", hint="abrir o Scalper pelo /vnc")
    size = os.path.getsize(f)
    with open(f, "rb") as fh:
        fh.seek(max(0, size - 300000))
        tail = fh.read().decode("latin-1")
    last = None
    for m in re.finditer(
            r"SendImAlive : (\d\d/\d\d/\d{4} \d\d:\d\d:\d\d)\.\d+ "
            r"CanSendMessage=(\w+).*?SocketConnected=(\w+)", tail):
        last = m
    if not last:
        return comp("down", "Scalper sem batimento no log",
                    hint="ver o Scalper no /vnc (login, aviso, travamento)")
    ts = parse_brt(last.group(1), "%d/%m/%Y %H:%M:%S")
    age = age_from(ts)
    ok = last.group(2) == "True" and last.group(3) == "True"
    if age > 120:
        return comp("down", "Scalper sem batimento ha %d s" % age, age,
                    "Scalper travado ou fechado; ver o /vnc",
                    {"ultimo_batimento_brt": ts.isoformat()})
    if not ok:
        return comp("degraded", "Scalper sem conexao com o feed", age,
                    "reconectar no Scalper (/vnc)")
    return comp("ok", "Scalper logado e conectado", age)


def read_status():
    with open(os.path.join(RTD, "status.json")) as fh:
        return json.load(fh)


def rtd_reader():
    st = read_status()
    a = st["assets"][ASSETS[0]]
    hor, date = a.get("hor", ""), a.get("date", "")
    detail = {"batches": st.get("batches"), "hor": hor, "date": date}
    try:
        ts = parse_brt(date + " " + hor, "%d/%m/%Y %H:%M:%S")
    except Exception:
        return comp("unknown", "RTD sem horario valido", detail=detail)
    age = age_from(ts)
    if not market_open():
        return comp("closed", "fora do pregao (ultimo dado %s)" % hor, age,
                    detail=detail)
    if date != NOW_BRT.strftime("%d/%m/%Y"):
        return comp("down", "RTD com dados de outro dia", age,
                    "reiniciar o container profit-wine", detail=detail)
    if age <= 90:
        return comp("ok", "RTD lendo (ultimo dado %s)" % hor, age,
                    detail=detail)
    if age <= 300:
        return comp("degraded", "RTD atrasado %d s" % age, age,
                    "ver rtdmw no container profit-wine", detail=detail)
    return comp("down", "RTD parado ha %d s" % age, age,
                "ver rtdmw-loop no container profit-wine", detail=detail)


def minutes_of(path):
    mins = []
    with open(path) as fh:
        for ln in fh:
            p = ln.split(";")
            if p[0] == "RESET" or ":" not in p[0]:
                continue
            h, m = p[0].split(":")
            mins.append(int(h) * 60 + int(m))
    return mins


def csv_minute():
    d = NOW_BRT.strftime("%d_%m_%Y")
    detail, worst, parts = {}, "ok", []
    open_ = market_open()
    nowm = NOW_BRT.hour * 60 + NOW_BRT.minute
    for a in ASSETS:
        f = os.path.join(RTD, "%s_min_%s.csv" % (a, d))
        if not os.path.exists(f):
            if open_ and nowm > OPEN_H * 60 + OPEN_M + 5:
                worst = "down"
            detail[a] = {"arquivo": False}
            parts.append("%s sem arquivo" % a)
            continue
        mins = minutes_of(f)
        lo = OPEN_H * 60 + OPEN_M
        hi = min(nowm, CLOSE_H * 60 + CLOSE_M)
        have = set(mins)
        missing = [m for m in range(max(lo, min(mins) if mins else lo), hi)
                   if m not in have] if mins else []
        recent = [m for m in missing if m >= nowm - 30]
        last = max(mins) if mins else None
        lag = (nowm - last) if last is not None else None
        detail[a] = {"linhas": len(mins), "ultima": "%02d:%02d" % divmod(last, 60)
                     if last is not None else None,
                     "lacunas_dia": len(missing), "lacunas_30min": len(recent)}
        parts.append("%s %d linhas" % (a, len(mins)))
        if open_:
            if lag is None or lag > 5:
                worst = "down"
            elif (lag > 2 or recent) and SEV[worst] < SEV["degraded"]:
                worst = "degraded"
    if not open_:
        return comp("closed", "fora do pregao; " + "; ".join(parts),
                    detail=detail)
    summ = "CSV por minuto: " + "; ".join(parts)
    return comp(worst, summ, hint="ver rtdmw; lacunas se recuperam so no dia seguinte",
                detail=detail)


def tt_coverage():
    st = read_status()
    tt = st.get("tt") or {}
    detail, covs = {}, []
    for k, v in tt.items():
        detail[k] = {"ativo": v.get("asset"), "cobertura": v.get("coverage"),
                     "negocios": v.get("trades")}
        if v.get("coverage") is not None:
            covs.append(v["coverage"])
    if not market_open():
        return comp("closed", "fora do pregao", detail=detail)
    if not covs:
        return comp("degraded", "T&T sem cobertura medida ainda",
                    hint="aguardar alguns minutos de pregao", detail=detail)
    lo = min(covs)
    if lo >= 0.90:
        return comp("ok", "T&T com cobertura %.0f%%+" % (lo * 100),
                    detail=detail)
    if lo >= 0.70:
        return comp("degraded", "T&T com cobertura %.0f%%" % (lo * 100),
                    hint="ver rtdmw (linhas do T&T)", detail=detail)
    return comp("down", "T&T com cobertura %.0f%%" % (lo * 100),
                hint="ver rtdmw (linhas do T&T)", detail=detail)


def mt5():
    r = run(["podman", "exec", "mt5-a", "python3", "-c",
             "import urllib.request as u;print(u.urlopen("
             "'http://127.0.0.1:8080/health',timeout=5).read().decode())"],
            timeout=12)
    if r.returncode != 0:
        return comp("down", "server.py nao responde",
                    hint="systemctl --user status magicwalls-server",
                    detail={"erro": r.stderr[-200:]})
    h = json.loads(r.stdout)
    detail = {"mt5_connected": h.get("mt5_connected"),
              "profit_connected": h.get("profit_connected")}
    if not h.get("mt5_connected"):
        return comp("down", "MT5 sem conexao com a corretora",
                    hint="entrar na conta pelo /vnc", detail=detail)
    return comp("ok", "MT5 conectado", detail=detail)


def publisher():
    r = run(["systemctl", "--user", "is-active", "magicwalls-publisher",
             "magicwalls-server"])
    states = r.stdout.split()
    detail = {"units": states}
    if states != ["active", "active"]:
        return comp("down", "publisher/server inativos",
                    hint="systemctl --user status magicwalls-publisher",
                    detail=detail)
    h = http_json("http://127.0.0.1:6201/health")
    age = h.get("feed_age_sec")
    detail["feed_age_sec"] = age
    if age is None:
        return comp("degraded", "API sem idade do feed", detail=detail)
    age = int(age)
    if age <= 60:
        return comp("ok", "feed chegando na API", age, detail=detail)
    if not market_open():
        return comp("closed", "fora do pregao; feed com %d s" % age, age,
                    detail=detail)
    if age <= 300:
        return comp("degraded", "feed atrasado %d s" % age, age,
                    "ver magicwalls-publisher", detail=detail)
    return comp("down", "feed parado ha %d s" % age, age,
                "ver magicwalls-publisher e o MT5", detail=detail)


def cloud_api():
    h = http_json("http://127.0.0.1:6201/health")
    if h.get("ok"):
        return comp("ok", "API no ar", detail={"db": h.get("db_backend")})
    return comp("down", "API respondeu sem ok", hint="ver magicwalls-cloud")


def gex():
    r = run(["systemctl", "--user", "show", "magicwalls-gex.service",
             "-p", "Result"])
    result = r.stdout.strip().split("=", 1)[-1]
    files = glob.glob(os.path.join(GEXDIR, "*.json"))
    newest = max((os.path.getmtime(f) for f in files), default=None)
    detail = {"result": result}
    if newest is None:
        return comp("down", "GEX sem arquivos", hint="ver magicwalls-gex")
    age = int(time.time() - newest)
    detail["idade_h"] = round(age / 3600, 1)
    if result not in ("success", ""):
        return comp("degraded", "ultima rodada do GEX falhou", age,
                    "journalctl --user -u magicwalls-gex", detail)
    if age <= 30 * 3600:
        return comp("ok", "GEX atualizado ha %.1f h" % (age / 3600), age,
                    detail=detail)
    if age <= 80 * 3600:
        return comp("degraded", "GEX com %.0f h" % (age / 3600), age,
                    "ver magicwalls-gex", detail)
    return comp("down", "GEX com %.0f h" % (age / 3600), age,
                "ver magicwalls-gex", detail)



def corretoras():
    """Painel de corretoras do motor: dado real (T&T/.trd) ou estimado (fallback sem Profit)."""
    r = run(["podman", "exec", "mt5-a", "python3", "-c",
             "import urllib.request as u,json;d=json.load(u.urlopen("
             "'http://127.0.0.1:8080/api/flow',timeout=20));"
             "print(json.dumps({'source':d.get('source'),'date':d.get('date')}))"],
            timeout=30)
    if r.returncode != 0:
        return comp("unknown", "nao foi possivel ler o /api/flow",
                    hint="ver magicwalls-server", detail={"erro": r.stderr[-200:]})
    d = json.loads(r.stdout)
    src = d.get("source") or "?"
    detail = {"fonte": src, "data": d.get("date")}
    if not market_open():
        return comp("closed", "fora do pregao (fonte %s)" % src, detail=detail)
    if src in ("PROFIT_RTD_TT", "PROFIT_TRD_NATIVE"):
        return comp("ok", "corretoras com dado real do Profit", detail=detail)
    return comp("degraded", "corretoras estimadas (sem T&T do Profit)",
                hint="ver rtdmw e o sync do tt_*.csv", detail=detail)


def setups():
    """Setups ao vivo: erros recentes do setups_live no log do server.py."""
    log = "/home/app/mt5-wine-lab/prefix-a/drive_c/magicwalls/server.log"
    if not os.path.exists(log):
        return comp("unknown", "sem log do server.py")
    with open(log, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 400000))
        tail = fh.read().decode("utf-8", "ignore").splitlines()
    errs = [l for l in tail[-3000:] if "[setups_live]" in l]
    detail = {"erros_recentes": len(errs), "ultimo": (errs[-1][:160] if errs else None)}
    if errs:
        return comp("degraded", "setups ao vivo com %d erro(s) recente(s)" % len(errs),
                    hint="ver server.log (setups_live)", detail=detail)
    return comp("ok", "setups ao vivo sem erro", detail=detail)


def host():
    du = shutil.disk_usage("/")
    pct = du.used * 100 // du.total
    mem = {}
    with open("/proc/meminfo") as fh:
        for ln in fh:
            k, v = ln.split(":")
            mem[k] = int(v.split()[0])
    avail_pct = mem["MemAvailable"] * 100 // mem["MemTotal"]
    nginx = run(["systemctl", "is-active", "nginx"]).stdout.strip()
    cert_days = None
    try:
        end = subprocess.run(
            "echo | openssl s_client -connect 127.0.0.1:443 -servername "
            "magicwalls.imentore.com 2>/dev/null | openssl x509 -noout -enddate",
            shell=True, capture_output=True, text=True, timeout=8).stdout
        m = re.search(r"notAfter=(.*)", end)
        if m:
            exp = datetime.strptime(m.group(1).strip(), "%b %d %H:%M:%S %Y %Z")
            cert_days = (exp - NOW.replace(tzinfo=None)).days
    except Exception:
        pass
    detail = {"disco_pct": pct, "mem_disponivel_pct": avail_pct,
              "nginx": nginx, "certificado_dias": cert_days}
    bad = []
    st = "ok"
    if nginx != "active":
        st, bad = "down", bad + ["nginx " + nginx]
    if pct >= 95 or avail_pct <= 5:
        st, bad = "down", bad + ["disco/memoria criticos"]
    elif (pct >= 85 or avail_pct <= 10) and SEV[st] < 2:
        st, bad = "degraded", bad + ["disco/memoria apertados"]
    if cert_days is not None and cert_days < 14 and SEV[st] < 2:
        st, bad = "degraded", bad + ["certificado vence em %d d" % cert_days]
    if st == "ok":
        return comp("ok", "servidor saudavel (disco %d%%, memoria livre %d%%)"
                    % (pct, avail_pct), detail=detail)
    return comp(st, "; ".join(bad), hint="ver o servidor ks4", detail=detail)


# ------------------------------------------------------------------- montagem
def main():
    checks = [
        ("containers", containers), ("profit_app", profit_app),
        ("profit_rtd", rtd_reader), ("profit_csv_minuto", csv_minute),
        ("profit_tt", tt_coverage), ("corretoras", corretoras),
        ("setups", setups), ("mt5", mt5),
        ("publisher", publisher), ("api", cloud_api),
        ("gex", gex), ("servidor", host),
    ]
    try:
        with open(STATE) as fh:
            state = json.load(fh)
    except Exception:
        state = {}
    pub, adm, worst = {}, {}, "ok"
    iso = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    for name, fn in checks:
        c, detail = safe(fn)
        prev = state.get(name, {})
        since = prev.get("since", iso) if prev.get("status") == c["status"] else iso
        state[name] = {"status": c["status"], "since": since}
        c["since"] = since
        pub[name] = c
        adm[name] = dict(c, detail=detail)
        if SEV[c["status"]] > SEV[worst]:
            worst = c["status"]
    bad = [n for n, c in pub.items() if c["status"] in ("degraded", "down")]
    unk = [n for n, c in pub.items() if c["status"] == "unknown"]
    if not market_open():
        mk = "fora do pregao"
    else:
        mk = "pregao aberto"
    if bad:
        summary = "%s: %s com problema (%s)" % (
            worst, len(bad), ", ".join(bad))
    elif unk:
        summary = "ok, mas sem checar: " + ", ".join(unk)
    else:
        summary = "tudo funcionando (%s)" % mk
    doc = {
        "schema": 1,
        "generated_at": iso,
        "generated_at_brt": NOW_BRT.strftime("%Y-%m-%d %H:%M:%S"),
        "market_open": market_open(),
        "status": worst if worst != "closed" else "ok",
        "summary": summary,
        "components": pub,
    }
    adoc = dict(doc, components=adm)
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    for path, d in (("health.json", doc), ("health-admin.json", adoc)):
        tmp = os.path.join(OUT, path + ".tmp")
        with open(tmp, "w") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        os.chmod(tmp, 0o644)
        os.replace(tmp, os.path.join(OUT, path))
    with open(STATE + ".tmp", "w") as fh:
        json.dump(state, fh)
    os.replace(STATE + ".tmp", STATE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
