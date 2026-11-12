# -*- coding: utf-8 -*-
"""
Servidor local da ferramenta de rotulagem (Fase 0 do PLANO_MESTRE) - Python stdlib, 127.0.0.1:5180.
Le apenas research/div_master/labeler/data/*.json; grava apenas research/div_master/labels/labels.csv (append).
Desfazer = nova linha UNDO apontando para a acao anulada (o CSV nunca e reescrito).
Uso: C:\\Python313\\python.exe research/div_master/labeler/server.py   (parar: fechar o processo / Stop-Process -Id <PID>)
"""
import csv, json, os, threading, uuid
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HOST, PORT = "127.0.0.1", 5180
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
STATIC = os.path.join(BASE, "static")
LABELS_DIR = os.path.join(os.path.dirname(BASE), "labels")
LABELS = os.path.join(LABELS_DIR, "labels.csv")
V2_DET = os.path.join(os.path.dirname(BASE), "engine_v2_1", "detections.json")
COLS = ["ts", "action_id", "action", "date", "asset", "cand_id", "origin", "verdict", "tipo", "dir",
        "f1_time", "f2_time", "sig_time", "f2_price", "wall_type", "wall_price", "wall_dist", "undo_of"]
TIPOS = {"REJEICAO", "ABSORCAO", "ROMPIMENTO", "OUTRO"}
LOCK = threading.Lock()


def load_index():
    return json.load(open(os.path.join(DATA, "index.json"), encoding="utf-8"))


def load_day(date):
    idx = {d["date"] for d in load_index()["days"]}
    if date not in idx:
        return None
    return json.load(open(os.path.join(DATA, f"{date}.json"), encoding="utf-8"))


def load_v2(date):
    if not os.path.exists(V2_DET):
        return []
    data = json.load(open(V2_DET, encoding="utf-8"))
    return data.get(date, [])


def read_rows():
    if not os.path.exists(LABELS):
        return []
    with open(LABELS, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def append_row(row):
    os.makedirs(LABELS_DIR, exist_ok=True)
    new = not os.path.exists(LABELS)
    with open(LABELS, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLS})


def effective(date, rows=None):
    """Estado atual do pregao: ultima decisao valida por candidato + marcacoes manuais, descontando UNDO."""
    rows = [r for r in (rows if rows is not None else read_rows()) if r["date"] == date]
    undone = {r["undo_of"] for r in rows if r["action"] == "UNDO"}
    live = [r for r in rows if r["action"] in ("LABEL", "ADD") and r["action_id"] not in undone]
    labels, manual = {}, []
    for r in live:
        if r["action"] == "LABEL":
            labels[r["cand_id"]] = r
        else:
            manual.append(r)
    return labels, manual, live


def bar_info(day, i):
    b = day["bars"][i]
    return b


class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(os.path.join(STATIC, "index.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/index":
            idx = load_index()
            rows = read_rows()
            for d in idx["days"]:
                labels, manual, _ = effective(d["date"], rows)
                d["n_done"] = len(labels)
                d["n_manual"] = len(manual)
            return self._send(200, idx)
        if u.path == "/api/day":
            date = (q.get("date") or [""])[0]
            day = load_day(date)
            if day is None:
                return self._send(404, {"error": "pregao desconhecido"})
            labels, manual, _ = effective(date)
            day["state"] = {k: {"verdict": v["verdict"], "tipo": v["tipo"], "dir": int(v["dir"] or 0)} for k, v in labels.items()}
            day["manual"] = [{"action_id": r["action_id"], "dir": int(r["dir"]), "tipo": r["tipo"],
                              "f1_time": r["f1_time"], "f2_time": r["f2_time"]} for r in manual]
            day["v21"] = load_v2(date)
            return self._send(200, day)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            n = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:
            return self._send(400, {"error": "json invalido"})
        date = str(body.get("date", ""))
        day = load_day(date)
        if day is None:
            return self._send(404, {"error": "pregao desconhecido"})
        ts = datetime.now().isoformat(timespec="seconds")
        aid = uuid.uuid4().hex[:12]
        with LOCK:
            if u.path == "/api/label":
                cand = next((c for c in day["candidates"] if c["id"] == body.get("cand_id")), None)
                verdict = body.get("verdict")
                tipo = body.get("tipo") or ""
                d = int(body.get("dir", 0))
                if cand is None or verdict not in ("VALIDA", "FALSA") or d not in (1, -1) or \
                        (verdict == "VALIDA" and tipo not in TIPOS) or (tipo and tipo not in TIPOS):
                    return self._send(400, {"error": "dados invalidos"})
                append_row({"ts": ts, "action_id": aid, "action": "LABEL", "date": date, "asset": day["asset"],
                            "cand_id": cand["id"], "origin": "pre", "verdict": verdict, "tipo": tipo, "dir": d,
                            "f1_time": cand.get("f1_time") or "", "f2_time": cand["f2_time"], "sig_time": cand["sig_time"],
                            "f2_price": cand["f2_price"], "wall_type": cand.get("wall_type") or "",
                            "wall_price": cand.get("wall_price") or "", "wall_dist": cand.get("wall_dist") or ""})
                return self._send(200, {"ok": True, "action_id": aid})
            if u.path == "/api/add":
                try:
                    i1, i2, d = int(body["f1_idx"]), int(body["f2_idx"]), int(body["dir"])
                except Exception:
                    return self._send(400, {"error": "dados invalidos"})
                tipo = body.get("tipo") or ""
                nb = len(day["bars"])
                if not (0 <= i1 < nb and 0 <= i2 < nb) or i1 >= i2 or d not in (1, -1) or tipo not in TIPOS:
                    return self._send(400, {"error": "dados invalidos (F1 antes de F2, direcao e tipo)"})
                b2 = day["bars"][i2]
                px2 = b2["low"] if d == 1 else b2["high"]
                walls = day.get("walls") or []
                near = min(walls, key=lambda w: abs(w["price"] - px2)) if walls else None
                append_row({"ts": ts, "action_id": aid, "action": "ADD", "date": date, "asset": day["asset"],
                            "cand_id": f"manual_{aid}", "origin": "manual", "verdict": "VALIDA", "tipo": tipo, "dir": d,
                            "f1_time": day["bars"][i1]["time"], "f2_time": b2["time"], "sig_time": "",
                            "f2_price": px2, "wall_type": near["type"] if near else "",
                            "wall_price": near["price"] if near else "",
                            "wall_dist": round(px2 - near["price"], 1) if near else ""})
                return self._send(200, {"ok": True, "action_id": aid})
            if u.path == "/api/undo":
                _, _, live = effective(date)
                if not live:
                    return self._send(200, {"ok": False, "msg": "nada para desfazer"})
                last = live[-1]
                append_row({"ts": ts, "action_id": aid, "action": "UNDO", "date": date, "asset": day["asset"],
                            "cand_id": last["cand_id"], "undo_of": last["action_id"]})
                return self._send(200, {"ok": True, "undone": last["cand_id"]})
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    srv = ThreadingHTTPServer((HOST, PORT), H)
    print(f"labeler em http://{HOST}:{PORT}  (pid {os.getpid()})", flush=True)
    srv.serve_forever()