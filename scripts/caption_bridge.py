#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ponte local de legendas com IA (variante B) para a tela de Marketing.

A tela envia o CORPO da legenda (sem os avisos fixos). A ponte pede ao llm-gateway (Strata, na 5090) DUAS frases:
um gancho de abertura e um fechamento. O código monta a variante B = gancho + legenda original INTACTA + fechamento,
e valida as frases. A chave do gateway fica só aqui: nunca vai para o navegador. Os avisos fixos e as hashtags são
anexados pela tela depois.

Regras que a ponte garante (a IA não decide nada disso):
  - a legenda original (números, horários, direções) nunca passa pela IA: ela só escreve as duas frases;
  - as frases não trazem número que não exista na original;
  - sem promessa de ganho, sem recomendação, sem hashtag;
  - uma chamada por vez (o Strata é compartilhado) e no máximo 2 tentativas por pedido.

Uso:  caption_bridge.py [--port 8095]
Chave: ~/.config/magicwalls-marketing/gateway-key.json (modo 600). Nada é registrado em log além de metadados.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import threading
import unicodedata
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple

PROJECT = "magicwalls-marketing"
GATEWAY_URL = os.environ.get("MW_GATEWAY_URL", "http://127.0.0.1:8080")
KEY_FILE = pathlib.Path(os.environ.get("MW_GATEWAY_KEY_FILE", pathlib.Path.home() / ".config/magicwalls-marketing/gateway-key.json"))
ALLOWED_ORIGINS = {
    o.strip() for o in os.environ.get("MW_BRIDGE_ORIGINS", "http://127.0.0.1:8098,https://app.magicwalls.com.br").split(",") if o.strip()
}
MAX_BODY_IN = 2200
MAX_B = 1800
MAX_HOOK = 110
MAX_CLOSING = 140
ATTEMPTS = 2

DEFAULT_TONE = "equilibrado"

# Instrução de estilo por nível. Só o estilo muda: as travas (números, termos proibidos, hashtags) valem para todos.
TONES = {
    "sobrio": (
        "tom sóbrio e direto, só informativo: relate fatos que estão na legenda, sem emoji, sem pergunta, sem "
        "exclamação e sem avaliar o desempenho ('conforme o plano', 'resultado sólido' e similares estão proibidos)"
    ),
    "equilibrado": (
        "tom equilibrado, com personalidade: abra com um contraste ou uma observação curta sobre o dia e feche com uma "
        "frase leve e específica sobre o que o card mostra; evite frases genéricas sobre risco ou resultado "
        "('a gestão do risco define o resultado' é exemplo do que NÃO escrever); no máximo 1 emoji"
    ),
    "chamativo": (
        "tom chamativo, para despertar curiosidade e levar a pessoa a olhar o painel: abra com contraste, pergunta ou "
        "número em destaque; feche convidando a ver como cada sinal apareceu; no máximo 1 emoji. Chamativo NÃO é "
        "promessa: nunca sugira ganho, resultado de conta ou que seguir os sinais dá retorno"
    ),
}

SYSTEM_TEMPLATE = (
    "Você escreve frases de efeito para o Instagram da Magic Walls, um estudo quantitativo educacional sobre "
    "mini-índice (WIN) e mini-dólar (WDO) da B3. A partir da legenda recebida, escreva duas frases em português "
    "do Brasil, em {tone}:\n"
    "- gancho: frase de abertura que prende a atenção, de uma linha, com no máximo 110 caracteres;\n"
    "- fechamento: frase curta de encerramento, de uma linha, com no máximo 140 caracteres.\n"
    "Regras obrigatórias:\n"
    "1. Use números, horários e pontos SOMENTE se estiverem escritos na legenda recebida, copiados exatamente, "
    "inclusive o sinal (se a legenda diz -250, escreva -250 e não 250). Na dúvida, não use número.\n"
    "2. Nunca prometa ganho, não use 'garantido', 'lucro certo' nem peça para comprar ou vender. Não recomende nada.\n"
    "3. Não escreva hashtags, avisos legais nem a frase 'conteúdo educacional': isso é adicionado depois.\n"
    "4. No máximo 1 emoji em cada frase. Cada frase em uma única linha.\n"
    "5. Responda somente o JSON pedido."
)


def system_prompt(tone: str) -> str:
    return SYSTEM_TEMPLATE.format(tone=TONES[tone])


SCHEMA = {
    "type": "object",
    "properties": {
        "gancho": {"type": "string", "maxLength": MAX_HOOK},
        "fechamento": {"type": "string", "maxLength": MAX_CLOSING},
    },
    "required": ["gancho", "fechamento"],
    "additionalProperties": False,
}

# Termos que nunca podem aparecer na variante B (comparados sem acento e em minúsculas).
BANNED = (
    "garantid", "lucro certo", "ganho certo", "sem risco", "risco zero", "dinheiro facil", "enriquec", "milion",
    "recomend", "compre ", "venda agora", "aproveite", "nao perca", "imperdivel", "certeza de", "100%",
    # garantias disfarçadas e conversa de lucro: o card mostra pontos, não resultado de conta
    "protege o capital", "protege seu capital", "preserva o capital", "protecao do capital", "lucr",
    "define o resultado", "garante",
)

HASHTAG_RE = re.compile(r"#[^\W\d_]")  # '#WIN' é hashtag; '#1' (número do sinal) não é

NUM_RE = re.compile(r"(?<![\w])[+\-−]?\d[\d.,]*(?::\d{2})?")


class BridgeError(Exception):
    def __init__(self, status: int, code: str, detail: str):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def facts(text: str) -> set:
    """Números e horários do texto, normalizados (sinal unicode vira '-', pontuação final sai)."""
    out = set()
    for raw in NUM_RE.findall(text or ""):
        token = raw.replace("−", "-").rstrip(".,")
        if re.search(r"\d", token):
            out.add(token.lstrip("+"))
    return out


def validate_variant(original: str, candidate: str) -> List[str]:
    """Devolve a lista de problemas da variante (vazia = aprovada)."""
    problems: List[str] = []
    cand = (candidate or "").strip()
    if not cand:
        return ["variante vazia"]
    if len(cand) > MAX_B:
        problems.append(f"passa de {MAX_B} caracteres")
    if cand == (original or "").strip():
        problems.append("igual à original")
    # Termos proibidos e hashtags valem para o que a IA escreveu; o texto original (que pode trazer a linha legal do
    # painel, com "recomendação") é de confiança e sai da checagem.
    own = cand.replace((original or "").strip(), "") if (original or "").strip() in cand else cand
    if HASHTAG_RE.search(own):
        problems.append("traz hashtag (isso é adicionado depois)")
    flat = _strip_accents(own).lower()
    for term in BANNED:
        if term in flat:
            problems.append(f"termo proibido: {term.strip()}")
    want, got = facts(original), facts(cand)
    missing, invented = sorted(want - got), sorted(got - want)
    if missing:
        problems.append("números da original ausentes: " + ", ".join(missing[:8]))
    if invented:
        problems.append("números que não existem na original: " + ", ".join(invented[:8]))
    return problems


def validate_phrases(original: str, hook: str, closing: str) -> List[str]:
    """Problemas das duas frases escritas pela IA (vazia = aprovadas)."""
    problems: List[str] = []
    allowed = facts(original)
    for name, text, limit in (("gancho", hook, MAX_HOOK), ("fechamento", closing, MAX_CLOSING)):
        t = (text or "").strip()
        if not t:
            problems.append(f"{name} vazio")
            continue
        if len(t) > limit:
            problems.append(f"{name} passa de {limit} caracteres")
        if "\n" in t:
            problems.append(f"{name} com mais de uma linha")
        if HASHTAG_RE.search(t):
            problems.append(f"{name} traz hashtag")
        flat = _strip_accents(t).lower()
        for term in BANNED:
            if term in flat:
                problems.append(f"{name} com termo proibido: {term.strip()}")
        invented = sorted(facts(t) - allowed)
        if invented:
            problems.append(f"{name} com número que não existe na original: " + ", ".join(invented[:6]))
    return problems


def assemble(original: str, hook: str, closing: str) -> str:
    """Variante B = gancho + original intacta + fechamento."""
    return f"{hook.strip()}\n\n{original.strip()}\n\n{closing.strip()}"


def load_key() -> str:
    try:
        data = json.loads(KEY_FILE.read_text(encoding="utf-8"))
        key = data["api_key"]
        if isinstance(key, str) and key:
            return key
    except (OSError, ValueError, KeyError):
        pass
    raise BridgeError(503, "NO_KEY", f"chave do gateway ausente em {KEY_FILE}")


def call_gateway(key: str, original: str, asset: str, feedback: Optional[List[str]], tone: str = DEFAULT_TONE) -> Tuple[Dict[str, str], Dict]:
    user = f"Ativo: {asset}\n\nLegenda original:\n{original}"
    if feedback:
        user += "\n\nA tentativa anterior foi recusada por: " + "; ".join(feedback) + ". Corrija e use apenas números da legenda."
    payload = {
        "project": PROJECT,
        "messages": [{"role": "system", "content": system_prompt(tone)}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "variante_legenda", "strict": True, "schema": SCHEMA}},
        "max_tokens": 1200,
        "temperature": 0.6,
    }
    req = urllib.request.Request(
        GATEWAY_URL + "/v1/structured/local",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        status = exc.code
        if status in (401, 403):
            raise BridgeError(502, "GATEWAY_AUTH", f"gateway recusou a chave ({status})") from exc
        if status == 429:
            raise BridgeError(429, "GATEWAY_BUSY", "o Strata está ocupado; tente em instantes") from exc
        raise BridgeError(502, "GATEWAY_ERROR", f"gateway respondeu {status}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise BridgeError(502, "GATEWAY_DOWN", "gateway fora do ar ou sem resposta") from exc
    result = body.get("result")
    if not isinstance(result, dict) or not all(isinstance(result.get(k), str) for k in ("gancho", "fechamento")):
        raise BridgeError(502, "GATEWAY_SHAPE", "resposta do gateway sem gancho e fechamento")
    meta = {k: body.get(k) for k in ("model_resolved", "latency_ms", "input_tokens", "output_tokens", "request_id")}
    return {"gancho": result["gancho"].strip(), "fechamento": result["fechamento"].strip()}, meta


_lock = threading.Lock()


def suggest(original: str, asset: str, tone: str = DEFAULT_TONE) -> Dict:
    original = (original or "").strip()
    if tone not in TONES:
        raise BridgeError(422, "TONE", "tom inválido (use sobrio, equilibrado ou chamativo)")
    if not original:
        raise BridgeError(422, "EMPTY", "legenda vazia")
    if len(original) > MAX_BODY_IN:
        raise BridgeError(422, "TOO_LONG", f"legenda original passa de {MAX_BODY_IN} caracteres")
    if not re.fullmatch(r"[A-Z0-9]{1,8}", asset or ""):
        raise BridgeError(422, "ASSET", "ativo inválido")
    if not _lock.acquire(blocking=False):
        raise BridgeError(429, "BUSY", "já há uma sugestão em andamento")
    try:
        key = load_key()
        feedback: Optional[List[str]] = None
        problems: List[str] = []
        meta: Dict = {}
        for attempt in range(1, ATTEMPTS + 1):
            phrases, meta = call_gateway(key, original, asset, feedback, tone)
            problems = validate_phrases(original, phrases["gancho"], phrases["fechamento"])
            if not problems:
                candidate = assemble(original, phrases["gancho"], phrases["fechamento"])
                final = validate_variant(original, candidate)  # defesa em profundidade sobre a legenda inteira
                if not final:
                    return {"ok": True, "variant_b": candidate, "hook": phrases["gancho"], "closing": phrases["fechamento"], "attempts": attempt, "tone": tone, "meta": meta}
                problems = final
            feedback = problems
        raise BridgeError(422, "VARIANT_REJECTED", "a IA não gerou uma variante válida: " + "; ".join(problems))
    finally:
        _lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "caption-bridge/1"

    def log_message(self, *args):  # nunca registrar corpo nem cabeçalhos
        return

    def _cors(self) -> bool:
        origin = self.headers.get("Origin", "")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            return True
        return False

    def _send(self, status: int, obj: Dict):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        allowed = (self.headers.get("Origin", "") in ALLOWED_ORIGINS) and bool(self.headers.get("Origin"))
        self.send_response(204 if allowed else 403)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path != "/health":
            return self._send(404, {"ok": False})
        try:
            load_key()
            self._send(200, {"ok": True, "key": True})
        except BridgeError as exc:
            self._send(200, {"ok": False, "key": False, "detail": exc.detail})

    def do_POST(self):
        if self.path != "/suggest":
            return self._send(404, {"ok": False})
        origin = self.headers.get("Origin", "")
        if origin and origin not in ALLOWED_ORIGINS:
            return self._send(403, {"ok": False, "code": "ORIGIN", "detail": "origem não permitida"})
        try:
            size = int(self.headers.get("Content-Length") or 0)
            if size > 16384:
                raise BridgeError(413, "BODY", "corpo grande demais")
            body = json.loads(self.rfile.read(size) or b"{}")
            result = suggest(str(body.get("body") or ""), str(body.get("asset") or ""), str(body.get("tone") or DEFAULT_TONE))
            self._send(200, result)
        except BridgeError as exc:
            self._send(exc.status, {"ok": False, "code": exc.code, "detail": exc.detail})
        except ValueError:
            self._send(400, {"ok": False, "code": "JSON", "detail": "JSON inválido"})


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8095)
    args = ap.parse_args(argv)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"ponte de legendas em http://127.0.0.1:{args.port} (gateway {GATEWAY_URL})", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
