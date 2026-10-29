"""
chain_archive.py — Arquivo diário das cadeias de opções BRUTAS usadas no cálculo do GEX.

Por que existe:
    As APIs gratuitas (CBOE delayed quotes, Deribit) só fornecem a foto do momento — não há
    histórico. Guardando a resposta bruta de cada run, qualquer dia passado pode ser recalculado
    no futuro (ex.: mudança de metodologia), sem depender de provedores pagos.

Formato:
    gex/data/chain_archive/YYYY-MM-DD/{source}_{ticker}_{HHMM}.json.gz
    {
      "source": "cboe" | "deribit",
      "ticker": "_SPX",
      "url": "...",
      "fetched_at_utc": "2026-10-29T10:31:02Z",
      "fetched_at_local": "2026-10-29T07:31:02",
      "payload": <resposta JSON original, sem alterações>
    }

Uso para recálculo: load_archived_payload("cboe", "_SPX", "2026-10-29") devolve o payload
original (o run mais recente do dia, ou o run de um horário específico via `hhmm`).

O arquivamento NUNCA interrompe o pipeline: qualquer erro de disco é apenas registrado.
"""

import datetime
import glob
import gzip
import json
import os

ARCHIVE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chain_archive")

# Evita gravar o mesmo ticker duas vezes no mesmo processo (ex.: refetch com DTE maior)
_archived_this_run = set()


def _safe_name(ticker: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in ticker)


def archive_payload(source: str, ticker: str, url: str, payload) -> str | None:
    """Grava a resposta bruta comprimida. Retorna o caminho do arquivo ou None em caso de erro."""
    key = (source, ticker)
    if key in _archived_this_run:
        return None
    try:
        now_local = datetime.datetime.now()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        day_dir = os.path.join(ARCHIVE_ROOT, now_local.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        path = os.path.join(day_dir, f"{source}_{_safe_name(ticker)}_{now_local.strftime('%H%M')}.json.gz")
        record = {
            "source": source,
            "ticker": ticker,
            "url": url,
            "fetched_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fetched_at_local": now_local.strftime("%Y-%m-%dT%H:%M:%S"),
            "payload": payload,
        }
        tmp = path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=6) as f:
            json.dump(record, f, separators=(",", ":"))
        os.replace(tmp, path)
        _archived_this_run.add(key)
        return path
    except Exception as e:  # nunca derrubar o cálculo do GEX por causa do arquivo
        print(f"      [Arquivo de cadeias] Aviso: não consegui gravar {source}/{ticker}: {e}")
        return None


def list_archived(source: str, ticker: str, date_str: str) -> list[str]:
    """Arquivos de um ticker em um dia, em ordem cronológica."""
    pattern = os.path.join(ARCHIVE_ROOT, date_str, f"{source}_{_safe_name(ticker)}_*.json.gz")
    return sorted(glob.glob(pattern))


def load_archived_payload(source: str, ticker: str, date_str: str, hhmm: str | None = None):
    """Carrega o registro arquivado (dict com metadados + 'payload'). None se não existir."""
    files = list_archived(source, ticker, date_str)
    if hhmm:
        files = [f for f in files if f.endswith(f"_{hhmm}.json.gz")]
    if not files:
        return None
    with gzip.open(files[-1], "rt", encoding="utf-8") as f:
        return json.load(f)

