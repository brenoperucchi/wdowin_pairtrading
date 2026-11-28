"""Regressão: a falta do catálogo de instrumentos da B3 não pode degradar as Walls em silêncio.

Em 28/11/2026 a B3 estava sem publicar o InstrumentsConsolidatedFile desde 12/11 (a tabela pública vem vazia
e o download responde 400). O parser caía no fallback legado (strike/vencimento deduzidos do ticker) e as Walls
divergiam das do Miqueias. Estes testes garantem que:
  - o que o MT5 resolve fica guardado por ISIN e é reaproveitado quando B3 e MT5 estão fora do ar;
  - o fallback legado nunca é gravado no cache (senão ele viraria "verdade");
  - cair no fallback legado gera um aviso explícito.
"""
import importlib
import sys
import types
from pathlib import Path

import pytest

pd = pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

bp = importlib.import_module("gex.engine.b3_parser")

HEADER = "Instrumento financeiro;ISIN;Col3;Col4;Segmento;Col6;Col7;Col8;Col9;Col10;Col11;Posicao em aberto\n"


def _row(ticker, isin, oi):
    return f"{ticker};{isin};x;x;EQUITY CALL;x;x;x;x;x;x;{oi}\n"


@pytest.fixture
def csv_file(tmp_path):
    f = tmp_path / "Posições em aberto-26-11-2026.csv"
    f.write_text(
        "Relatorio;teste\n" + HEADER
        + _row("IBOVL171", "BRIBOVISIN01", 100)
        + _row("IBOVL172", "BRIBOVISIN02", 200),
        encoding="latin1",
    )
    return f


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    cache = tmp_path / "catalog.json"
    monkeypatch.setattr(bp, "_INSTRUMENTS_CACHE_PATH", str(cache))
    monkeypatch.setattr(bp, "_fetch_b3_instruments_for_date", lambda d: {})  # B3 sem publicar
    return cache


def test_mt5_resolution_is_persisted_by_isin(isolated, csv_file, monkeypatch):
    monkeypatch.setattr(bp, "_fetch_mt5_ibov_metadata", lambda: {
        "IBOVL171": {"strike": 171000.0, "expiry": "2026-12-16"},
        "IBOVL172": {"strike": 172000.0, "expiry": "2026-12-16"},
    })
    df = bp._parse_single_csv(str(csv_file))
    assert sorted(df["strike"]) == [171000.0, 172000.0]
    saved = bp._load_ibov_catalog_cache()
    assert saved["BRIBOVISIN01"]["strike"] == 171000.0
    assert saved["BRIBOVISIN01"]["expiry"] == "2026-12-16"


def test_cached_catalog_is_used_when_b3_and_mt5_are_down(isolated, csv_file, monkeypatch, capsys):
    bp._save_ibov_catalog_cache({
        "BRIBOVISIN01": {"ticker": "IBOVL171", "type": "CALL", "strike": 171500.0, "expiry": "2026-12-16"},
        "BRIBOVISIN02": {"ticker": "IBOVL172", "type": "CALL", "strike": 172500.0, "expiry": "2026-12-16"},
    })

    def mt5_must_not_be_needed():
        raise AssertionError("o MT5 não devia ser consultado quando o cache já resolve tudo")

    monkeypatch.setattr(bp, "_fetch_mt5_ibov_metadata", mt5_must_not_be_needed)
    df = bp._parse_single_csv(str(csv_file))
    assert sorted(df["strike"]) == [171500.0, 172500.0]  # vem do cache, não do ticker (171000/172000)
    assert "ATENCAO" not in capsys.readouterr().out


def test_legacy_fallback_is_never_persisted_and_warns(isolated, csv_file, monkeypatch, capsys):
    monkeypatch.setattr(bp, "_fetch_mt5_ibov_metadata", lambda: {})  # MT5 sem símbolos
    df = bp._parse_single_csv(str(csv_file))
    assert len(df) == 2
    assert bp._load_ibov_catalog_cache() == {}, "o fallback legado não pode virar cache"
    out = capsys.readouterr().out
    assert "ATENCAO" in out and "fallback legado" in out
