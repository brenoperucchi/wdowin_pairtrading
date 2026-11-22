# -*- coding: utf-8 -*-
"""
Intermediário SOMENTE-LEITURA para o link público do painel 5176 (túnel cloudflared).

- Serve a versão pública do painel (regime-dashboard/dist-publico, gerada com `npx vite build --mode publico`).
- Repassa ao server.py (127.0.0.1:8080) APENAS as consultas que o painel faz para mostrar dados:
    GET  /api/v2/regime · /api/performance · /api/di-regime · /api/history · /api/gex-walls · /api/flow
         /api/compass/etapa1 · /api/compass/m1_series
    POST /api/compass/divergencias_motor (só cálculo de divergência sobre as barras enviadas; corpo ≤ 2 MB)
- Todo o resto é 404: /api/restart, /api/flow/inject-history, /api/flow/update, /api/live-calendar (conta MT5),
  /docs, /openapi.json, e qualquer outro caminho.
- Respostas GET em cache por alguns segundos (vários visitantes não multiplicam a carga no server.py).
- Escuta só em 127.0.0.1 — o acesso externo vem pelo túnel.

Uso: python scripts/painel_publico.py [porta=5199]
     cloudflared tunnel --url http://127.0.0.1:5199
"""
import gzip
import json
import mimetypes
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKEND = "http://127.0.0.1:8080"
GET_OK_5178 = {"/api/compass/etapa1", "/api/compass/m1_series"}
GET_OK_5176 = GET_OK_5178 | {
    "/api/v2/regime",
    "/api/performance",
    "/api/di-regime",
    "/api/history",
    "/api/gex-walls",
}
POST_OK = {"/api/compass/divergencias_motor"}
MAX_BODY = 2 * 1024 * 1024
TTL = {"/api/compass/m1_series": 20.0, "/api/history": 30.0}   # demais: 3 s (etapa1 full no modo 5176: 15 s)
_cache, _locks, _glock = {}, {}, threading.Lock()
MODE = "5178"
DIST = os.path.join(ROOT, "regime-dashboard", "dist-publico")
GET_OK = set(GET_OK_5178)


def _sanitize_etapa1_5176(raw_bytes: bytes) -> bytes:
    """Modo 5176 (ROBOS MAGIC WALLS): mantém gráficos, carteira 5176 e sinais; remove apenas avisos locais RTD."""
    try:
        obj = json.loads(raw_bytes)
    except Exception:
        return raw_bytes
    if not isinstance(obj, dict):
        return raw_bytes
    obj.pop("profit_rtd_warnings", None)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sanitize_etapa1(raw_bytes: bytes) -> bytes:
    """Remove dados internos (estratégias, corretoras, sinais/trades, logs RTD) antes de expor ao público."""
    try:
        obj = json.loads(raw_bytes)
    except Exception:
        return raw_bytes
    if not isinstance(obj, dict):
        return raw_bytes
    for k in ("portfolio_4_sistematicas", "profit_rtd_warnings", "caminho_b"):
        obj.pop(k, None)
    for sym in ("WIN", "WDO"):
        asset = obj.get(sym)
        if not isinstance(asset, dict):
            continue
        for k in ("brokers", "top_buyers", "top_sellers", "caminho_b"):
            asset.pop(k, None)
        ca = asset.get("caminho_a")
        if isinstance(ca, dict):
            ca.pop("signals_scorecard", None)
            raw_sigs = ca.get("signals_log")
            if isinstance(raw_sigs, list):
                ca["signals_log"] = [
                    {
                        "strategy_id": s.get("strategy_id"),
                        "time": s.get("time"),
                        "direction": s.get("direction"),
                        "is_prev_day": bool(s.get("is_prev_day", False)),
                    }
                    for s in raw_sigs
                    if isinstance(s, dict) and s.get("time")
                ]
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _safe_query(path: str, query: str) -> str:
    qs = parse_qs(query or "", keep_blank_values=False)
    clean = {}
    if "date_str" in qs and qs["date_str"]:
        val = qs["date_str"][0].strip()[:10]
        if len(val) == 10 and all(c.isdigit() or c == "-" for c in val):
            clean["date_str"] = val
    if path == "/api/compass/etapa1":
        if MODE == "5178" or (qs.get("lite", [""])[0] in ("1", "true")):
            clean["lite"] = "1"
    if path == "/api/history" and "days" in qs and qs["days"]:
        try:
            d_val = max(1, min(365, int(qs["days"][0])))
            clean["days"] = str(d_val)
        except ValueError:
            pass
    return urlencode(clean)


def _fetch(url, data=None, timeout=90):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"} if data else {},
                                 method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.headers.get("Content-Type", "application/json"), r.read()


def cached_get(path, query):
    safe_q = _safe_query(path, query)
    key = path + ("?" + safe_q if safe_q else "")
    ttl = TTL.get(path, 3.0)
    if MODE == "5176" and path == "/api/compass/etapa1" and "lite=1" not in safe_q:
        ttl = 15.0
    with _glock:
        lock = _locks.setdefault(key, threading.Lock())
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    with lock:                                   # um único pedido ao backend por chave
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        status, ctype, body = _fetch(BACKEND + key)
        if path == "/api/compass/etapa1" and status == 200:
            body = _sanitize_etapa1_5176(body) if MODE == "5176" else _sanitize_etapa1(body)
        res = (status, ctype, body)
        with _glock:
            _cache[key] = (time.time(), res)
            if len(_cache) > 500:                # limpa entradas antigas
                for k in sorted(_cache, key=lambda k: _cache[k][0])[:250]:
                    _cache.pop(k, None)
        return res


class H(BaseHTTPRequestHandler):
    server_version = "painel5176"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, ctype, body, cache="no-store"):
        accept_enc = self.headers.get("Accept-Encoding", "")
        use_gzip = "gzip" in accept_enc and len(body) > 512
        if use_gzip:
            body = gzip.compress(body, compresslevel=5)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _404(self):
        self._send(404, "text/plain; charset=utf-8", b"nao encontrado")

    def do_HEAD(self):
        self.do_GET()

    def _normalize_path(self, raw_path: str):
        if raw_path == "/magicwall":
            return "/magicwall", True
        if raw_path.startswith("/magicwall/"):
            trimmed = raw_path[len("/magicwall"):] or "/"
            return trimmed, False
        return raw_path, False

    def do_GET(self):
        u = urlsplit(self.path)
        path, needs_trailing_slash = self._normalize_path(u.path)
        if needs_trailing_slash:
            target = "/magicwall/" + (("?" + u.query) if u.query else "")
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/health":
            return self._send(200, "application/json", b'{"ok":true,"service":"painel_publico"}')
        if path.startswith("/api/"):
            if path not in GET_OK:
                return self._404()
            try:
                code, ctype, body = cached_get(path, u.query)
                return self._send(code, ctype, body)
            except urllib.error.HTTPError as e:
                return self._send(e.code, "application/json", json.dumps({"ok": False}).encode())
            except Exception:
                return self._send(502, "application/json", json.dumps({"ok": False, "error": "backend indisponivel"}).encode())
        # arquivos estáticos da versão pública (sem listagem, sem sair da pasta)
        rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
        full = os.path.realpath(os.path.join(DIST, rel))
        if not full.startswith(os.path.realpath(DIST) + os.sep) or not os.path.isfile(full):
            return self._404()
        with open(full, "rb") as f:
            body = f.read()
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, ctype, body, "public, max-age=31536000, immutable" if rel.startswith("assets/") else "no-cache")

    def do_POST(self):
        raw_path = urlsplit(self.path).path
        path, _ = self._normalize_path(raw_path)
        if path not in POST_OK:
            return self._404()
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._send(413, "application/json", b'{"ok": false}')
        data = self.rfile.read(n)
        try:
            json.loads(data)
            code, ctype, body = _fetch(BACKEND + path, data=data)
            return self._send(code, ctype, body)
        except Exception:
            return self._send(502, "application/json", json.dumps({"ok": False}).encode())

    def do_PUT(self):
        self._404()

    do_DELETE = do_PATCH = do_OPTIONS = do_PUT


def main():
    global MODE, DIST, GET_OK
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5199
    if "--mode" in sys.argv:
        m_idx = sys.argv.index("--mode")
        MODE = sys.argv[m_idx + 1] if m_idx + 1 < len(sys.argv) else "5178"
    elif port == 5198:
        MODE = "5176"
    if MODE == "5176":
        DIST = os.path.join(ROOT, "regime-dashboard", "dist-publico-5176")
        GET_OK = set(GET_OK_5176)
        H.server_version = "painel5176_robos"
    else:
        DIST = os.path.join(ROOT, "regime-dashboard", "dist-publico")
        GET_OK = set(GET_OK_5178)
    if not os.path.isfile(os.path.join(DIST, "index.html")):
        raise SystemExit(f"versao publica nao encontrada em {DIST}")
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    print(f"painel publico ({MODE}) em http://127.0.0.1:{port} (somente leitura -> {BACKEND})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
