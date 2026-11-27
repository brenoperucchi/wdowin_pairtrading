"""Testes da ponte de legendas com IA (scripts/caption_bridge.py), com um gateway falso."""

import importlib.util
import json
import pathlib
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ORIGINAL = (
    "Magic Walls — Resumo do pregão · Mini-Índice (WIN) (Qui, 26/11/2026)\n\n"
    "• #1 · 11:35 · X Venda (175.105) → +1.325 pts [Melhor pernada]\n"
    "• #2 · 13:10 · W Compra (174.500) → Stop -250 pts (Wall 174.250 às 13:20)\n"
    "• #3 · 18:00 · X Venda (178.485) → 0 pts\n\n"
    "Total: 3 sinais (2 protegidos >150 pts, 1 stop (-250 pts))."
)
GOOD_B = (
    "Três entradas no WIN em 26/11/2026, uma pernada de +1.325 pts.\n\n"
    "• #1 · 11:35 · X Venda (175.105) → +1.325 pts [Melhor pernada]\n"
    "• #2 · 13:10 · W Compra (174.500) → Stop −250 pts (Wall 174.250 às 13:20)\n"
    "• #3 · 18:00 · X Venda (178.485) → 0 pts\n\n"
    "Total: 3 sinais (2 protegidos >150 pts, 1 stop (-250 pts))."
)


HOOK = "Uma pernada de +1.325 pts no WIN em 26/11."
CLOSING = "Estudo educacional, sem promessa de resultado."
FULL_B = f"{HOOK}\n\n{ORIGINAL}\n\n{CLOSING}"


class FakeGateway:
    """Gateway falso: devolve respostas programadas e guarda as requisições."""

    def __init__(self):
        self.responses = []  # lista de (status, corpo) consumida em ordem; a última se repete
        self.requests = []
        self.delay = 0.0
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_POST(self):
                size = int(self.headers.get("Content-Length") or 0)
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": json.loads(self.rfile.read(size))})
                time.sleep(outer.delay)
                status, body = outer.responses.pop(0) if len(outer.responses) > 1 else outer.responses[0]
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def reply(self, hook, closing=CLOSING, status=200):
        body = {"result": {"gancho": hook, "fechamento": closing}, "model_resolved": "strata-fake", "latency_ms": 5, "input_tokens": 1, "output_tokens": 1, "request_id": "r1"}
        return status, body


@pytest.fixture()
def env(tmp_path, monkeypatch):
    gw = FakeGateway()
    key = tmp_path / "gateway-key.json"
    key.write_text(json.dumps({"api_key": "chave-de-teste", "scope": ["structured-local"]}))
    monkeypatch.setenv("MW_GATEWAY_URL", gw.url)
    monkeypatch.setenv("MW_GATEWAY_KEY_FILE", str(key))
    spec = importlib.util.spec_from_file_location("caption_bridge_under_test", ROOT / "scripts" / "caption_bridge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod, gw, key
    gw.server.shutdown()


# ── validação ───────────────────────────────────────────────────────────────

def test_valid_variant_passes(env):
    mod, _, _ = env
    assert mod.validate_variant(ORIGINAL, GOOD_B) == []


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda s: s.replace("+1.325 pts [", "+1.425 pts ["), "números que não existem"),
        (lambda s: s.replace("(175.105)", ""), "ausentes"),
        (lambda s: s.replace("11:35", "11:36"), "não existem"),
        (lambda s: s + "\n#WIN #B3", "hashtag"),
        (lambda s: s.replace("Três entradas", "#MagicWalls três entradas"), "hashtag"),
        (lambda s: s.replace("Três entradas", "Resultado garantido: três entradas"), "termo proibido: garantid"),
        (lambda s: s.replace("Três entradas", "Não perca, três entradas"), "termo proibido"),
        (lambda s: s + "\nRecomendamos acompanhar.", "termo proibido: recomend"),
    ],
)
def test_bad_variants_are_rejected(env, mutate, fragment):
    mod, _, _ = env
    problems = mod.validate_variant(ORIGINAL, mutate(GOOD_B))
    assert problems and any(fragment in p for p in problems), problems


def test_identical_and_empty_are_rejected(env):
    mod, _, _ = env
    assert "igual à original" in mod.validate_variant(ORIGINAL, ORIGINAL)
    assert mod.validate_variant(ORIGINAL, "  ") == ["variante vazia"]


def test_signal_numbers_like_hash_one_are_not_hashtags(env):
    mod, _, _ = env
    assert mod.validate_variant(ORIGINAL, GOOD_B) == []
    assert mod.HASHTAG_RE.search("#1 · 11:35") is None and mod.HASHTAG_RE.search("#WIN")


def test_minus_sign_variants_are_equivalent(env):
    mod, _, _ = env
    assert mod.facts("Stop −250 pts") == mod.facts("Stop -250 pts")
    assert mod.facts("+1.325 pts") == mod.facts("1.325 pts")


# ── fluxo com o gateway falso ───────────────────────────────────────────────

def test_success_sends_the_right_contract(env):
    mod, gw, _ = env
    gw.responses = [gw.reply(HOOK)]
    out = mod.suggest(ORIGINAL, "WIN")
    assert out["ok"] and out["variant_b"] == FULL_B and out["attempts"] == 1
    assert ORIGINAL in out["variant_b"], "a legenda original precisa sair intacta"
    req = gw.requests[0]
    assert req["path"] == "/v1/structured/local" and req["auth"] == "Bearer chave-de-teste"
    assert req["body"]["project"] == "magicwalls-marketing"
    assert req["body"]["response_format"]["json_schema"]["strict"] is True
    assert set(req["body"]["response_format"]["json_schema"]["schema"]["properties"]) == {"gancho", "fechamento"}
    assert req["body"]["max_tokens"] <= 4096 and "model" not in req["body"]
    assert "chave-de-teste" not in json.dumps(out)


def test_retries_once_with_feedback_then_succeeds(env):
    mod, gw, _ = env
    gw.responses = [gw.reply(HOOK.replace("1.325", "9.999")), gw.reply(HOOK)]
    out = mod.suggest(ORIGINAL, "WIN")
    assert out["attempts"] == 2 and len(gw.requests) == 2
    assert "recusada" in gw.requests[1]["body"]["messages"][1]["content"]


def test_two_bad_attempts_fail_without_third_call(env):
    mod, gw, _ = env
    gw.responses = [gw.reply("Resultado garantido: " + HOOK)]
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(ORIGINAL, "WIN")
    assert err.value.status == 422 and err.value.code == "VARIANT_REJECTED"
    assert len(gw.requests) == 2


def test_missing_key_is_clear_error(env):
    mod, gw, key = env
    key.unlink()
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(ORIGINAL, "WIN")
    assert err.value.code == "NO_KEY" and gw.requests == []


@pytest.mark.parametrize(
    "hook, closing, fragment",
    [
        ("Pernada de +2.000 pts", CLOSING, "número que não existe"),
        ("Pernada de +1.325 pts #WIN", CLOSING, "hashtag"),
        ("Linha um\nlinha dois", CLOSING, "mais de uma linha"),
        (HOOK, "", "fechamento vazio"),
        ("Lucro garantido hoje", CLOSING, "termo proibido"),
        ("x" * 130, CLOSING, "passa de 110"),
        (HOOK, "A gestão protege o capital do trader.", "termo proibido"),
        (HOOK, "Nem toda operação termina em lucro.", "termo proibido"),
    ],
)
def test_phrases_are_validated(env, hook, closing, fragment):
    mod, _, _ = env
    problems = mod.validate_phrases(ORIGINAL, hook, closing)
    assert any(fragment in p for p in problems), problems


def test_phrases_may_reuse_numbers_from_the_original(env):
    mod, _, _ = env
    assert mod.validate_phrases(ORIGINAL, "Venda de 11:35 rendeu +1.325 pts", "Foram 3 sinais no dia.") == []


LEGAL_ORIGINAL = ORIGINAL + "\n\nEstudo quantitativo de caráter estritamente educacional. Não constitui recomendação de investimento."


def test_legal_line_inside_the_original_is_not_blamed_on_the_model(env):
    mod, gw, _ = env
    gw.responses = [gw.reply(HOOK)]
    out = mod.suggest(LEGAL_ORIGINAL, "WIN")
    assert out["ok"] and LEGAL_ORIGINAL in out["variant_b"]


def test_banned_term_written_by_the_model_is_still_caught_with_legal_original(env):
    mod, gw, _ = env
    gw.responses = [gw.reply("Recomendamos acompanhar o WIN")]
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(LEGAL_ORIGINAL, "WIN")
    assert err.value.code == "VARIANT_REJECTED"


def test_model_cannot_alter_the_original_numbers(env):
    mod, gw, _ = env
    gw.responses = [gw.reply("Venda das 11:35 abre o pregão")]
    out = mod.suggest(ORIGINAL, "WIN")
    assert mod.facts(out["variant_b"]) == mod.facts(ORIGINAL)


@pytest.mark.parametrize("status, code, out_status", [(401, "GATEWAY_AUTH", 502), (403, "GATEWAY_AUTH", 502), (429, "GATEWAY_BUSY", 429), (500, "GATEWAY_ERROR", 502)])
def test_gateway_errors_are_mapped(env, status, code, out_status):
    mod, gw, _ = env
    gw.responses = [(status, {"detail": "x"})]
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(ORIGINAL, "WIN")
    assert (err.value.code, err.value.status) == (code, out_status)


def test_second_request_while_busy_is_refused(env):
    mod, gw, _ = env
    gw.delay = 0.6
    gw.responses = [gw.reply(HOOK)]
    first = {}
    t = threading.Thread(target=lambda: first.update(mod.suggest(ORIGINAL, "WIN")))
    t.start()
    time.sleep(0.2)
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(ORIGINAL, "WIN")
    assert err.value.code == "BUSY" and err.value.status == 429
    t.join()
    assert first.get("ok") and len(gw.requests) == 1


@pytest.mark.parametrize("body, asset, code", [("", "WIN", "EMPTY"), ("x" * 2300, "WIN", "TOO_LONG"), (ORIGINAL, "win; drop", "ASSET")])
def test_input_is_validated_before_calling_gateway(env, body, asset, code):
    mod, gw, _ = env
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(body, asset)
    assert err.value.code == code and gw.requests == []


# ── camada HTTP ─────────────────────────────────────────────────────────────

@pytest.fixture()
def http_bridge(env):
    mod, gw, key = env
    server = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield mod, gw, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _post(url, payload, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url + "/suggest", data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), json.load(r)
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.load(exc)


def test_http_allowed_origin_gets_cors_and_variant(http_bridge):
    mod, gw, url = http_bridge
    gw.responses = [gw.reply(HOOK)]
    status, headers, body = _post(url, {"body": ORIGINAL, "asset": "WIN"}, origin="http://127.0.0.1:8098")
    assert status == 200 and body["variant_b"] == FULL_B
    assert headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:8098"
    assert headers["Access-Control-Allow-Private-Network"] == "true"
    assert "chave-de-teste" not in json.dumps(body)


def test_http_unknown_origin_is_refused_without_calling_gateway(http_bridge):
    mod, gw, url = http_bridge
    gw.responses = [gw.reply(HOOK)]
    status, headers, body = _post(url, {"body": ORIGINAL, "asset": "WIN"}, origin="https://evil.example")
    assert status == 403 and body["code"] == "ORIGIN" and gw.requests == []
    assert "Access-Control-Allow-Origin" not in headers


def test_http_preflight(http_bridge):
    mod, gw, url = http_bridge
    req = urllib.request.Request(url + "/suggest", method="OPTIONS", headers={"Origin": "https://app.magicwalls.com.br", "Access-Control-Request-Method": "POST"})
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 204 and r.headers["Access-Control-Allow-Origin"] == "https://app.magicwalls.com.br"


def test_http_health_reports_key_state(http_bridge, env):
    mod, gw, url = http_bridge
    _, _, key = env
    with urllib.request.urlopen(url + "/health", timeout=10) as r:
        assert json.load(r)["key"] is True
    key.unlink()
    with urllib.request.urlopen(url + "/health", timeout=10) as r:
        assert json.load(r)["key"] is False


# ── níveis de tom ───────────────────────────────────────────────────────────

def _system_text(gw):
    return gw.requests[-1]["body"]["messages"][0]["content"]


@pytest.mark.parametrize("tone, marker", [("sobrio", "sem emoji"), ("equilibrado", "com personalidade"), ("chamativo", "despertar curiosidade")])
def test_each_tone_sends_its_own_style_and_is_echoed(env, tone, marker):
    mod, gw, _ = env
    gw.responses = [gw.reply(HOOK)]
    out = mod.suggest(ORIGINAL, "WIN", tone)
    assert out["ok"] and out["tone"] == tone
    system = _system_text(gw)
    assert marker in system
    others = {"sobrio": "sem emoji", "equilibrado": "com personalidade", "chamativo": "despertar curiosidade"}
    assert all(m not in system for t, m in others.items() if t != tone)


def test_default_tone_is_equilibrado(env):
    mod, gw, _ = env
    gw.responses = [gw.reply(HOOK)]
    assert mod.suggest(ORIGINAL, "WIN")["tone"] == "equilibrado"


def test_unknown_tone_is_refused_before_calling_gateway(env):
    mod, gw, _ = env
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(ORIGINAL, "WIN", "agressivo")
    assert err.value.code == "TONE" and gw.requests == []


@pytest.mark.parametrize("tone", ["sobrio", "equilibrado", "chamativo"])
def test_same_guardrails_apply_to_every_tone(env, tone):
    mod, gw, _ = env
    gw.responses = [gw.reply("Quem seguiu lucrou hoje no WIN")]
    with pytest.raises(mod.BridgeError) as err:
        mod.suggest(ORIGINAL, "WIN", tone)
    assert err.value.code == "VARIANT_REJECTED" and len(gw.requests) == 2


def test_generic_risk_claim_is_blocked(env):
    mod, _, _ = env
    assert any("define o resultado" in p for p in mod.validate_phrases(ORIGINAL, HOOK, "A gestão do risco define o resultado final"))


def test_prompt_demands_signed_numbers(env):
    mod, _, _ = env
    assert "-250" in mod.system_prompt("sobrio")


def test_http_accepts_tone_and_rejects_unknown(http_bridge):
    mod, gw, url = http_bridge
    gw.responses = [gw.reply(HOOK)]
    status, _, body = _post(url, {"body": ORIGINAL, "asset": "WIN", "tone": "chamativo"})
    assert status == 200 and body["tone"] == "chamativo"
    status, _, body = _post(url, {"body": ORIGINAL, "asset": "WIN", "tone": "xyz"})
    assert status == 422 and body["code"] == "TONE"
