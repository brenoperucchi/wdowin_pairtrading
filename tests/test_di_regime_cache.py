import time

import pytest

import server


def test_di_regime_uses_fresh_cache_by_default(monkeypatch):
    cached = {"current_z": 1.23, "history": []}
    monkeypatch.setattr(server, "_di_cache", cached)
    monkeypatch.setattr(server, "_di_cache_ts", time.time())

    def fail_if_called():
        raise AssertionError("connect_mt5 should not be called when cache is fresh")

    monkeypatch.setattr(server, "connect_mt5", fail_if_called)

    assert server.di_regime() is cached


def test_di_regime_force_bypasses_fresh_cache(monkeypatch):
    monkeypatch.setattr(server, "_di_cache", {"current_z": 1.23, "history": []})
    monkeypatch.setattr(server, "_di_cache_ts", time.time())

    def prove_bypass():
        raise RuntimeError("cache bypassed")

    monkeypatch.setattr(server, "connect_mt5", prove_bypass)

    with pytest.raises(RuntimeError, match="cache bypassed"):
        server.di_regime(force=True)
