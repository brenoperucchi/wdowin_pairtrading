"""Tests for core.runtime_config (load/save/validate)."""
from __future__ import annotations

import copy
import json

import pytest

from core import runtime_config


def _valid_payload():
    return copy.deepcopy(runtime_config.DEFAULTS)


def test_defaults_returned_when_file_missing(tmp_path):
    target = tmp_path / "runtime.json"
    cfg = runtime_config.load_runtime_config(target)
    assert cfg == runtime_config.DEFAULTS
    # Crucially, the loader must NOT auto-create the file.
    assert not target.exists()


def test_defaults_shape():
    """DEFAULTS has both profiles and all five fields per profile."""
    assert set(runtime_config.DEFAULTS) == set(runtime_config.PROFILES)
    for profile in runtime_config.PROFILES:
        assert set(runtime_config.DEFAULTS[profile]) == set(runtime_config.FIELDS)


def test_save_then_load_roundtrip(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["replay"]["eg_bars"] = 2240
    payload["replay"]["eg_recalc"] = "daily"
    payload["live"]["eg_threshold"] = 0.05

    saved = runtime_config.save_runtime_config(payload, target)
    assert saved["replay"]["eg_bars"] == 2240
    assert saved["live"]["eg_threshold"] == 0.05

    reloaded = runtime_config.load_runtime_config(target)
    assert reloaded == saved


def test_save_writes_atomically(tmp_path):
    """A successful save replaces the file in one operation, leaving no tmp file behind."""
    target = tmp_path / "runtime.json"
    runtime_config.save_runtime_config(_valid_payload(), target)
    assert target.exists()
    leftovers = [
        p for p in tmp_path.iterdir()
        if p.name.startswith(".runtime.") and p.name.endswith(".json")
    ]
    assert leftovers == []


def test_save_failure_does_not_clobber_existing(tmp_path):
    target = tmp_path / "runtime.json"
    runtime_config.save_runtime_config(_valid_payload(), target)
    original = target.read_text(encoding="utf-8")

    bad = _valid_payload()
    bad["live"]["eg_bars"] = 10  # too small
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(bad, target)

    # File still has the original contents, no tmp leaked.
    assert target.read_text(encoding="utf-8") == original
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".runtime.")]
    assert leftovers == []


def test_load_rejects_malformed_json(tmp_path):
    target = tmp_path / "runtime.json"
    target.write_text("not json{", encoding="utf-8")
    with pytest.raises(ValueError):
        runtime_config.load_runtime_config(target)


@pytest.mark.parametrize(
    "field,value",
    [
        ("eg_threshold", 0.0),
        ("eg_threshold", -0.1),
        ("eg_threshold", 1.5),
        ("eg_threshold", "0.10"),
        ("eg_bars", 59),
        ("eg_bars", 0),
        ("eg_bars", 250.5),
        ("eg_bars", "250"),
        ("eg_recalc", "weekly"),
        ("eg_recalc", ""),
        ("rho_breakdown_level", 0),
        ("rho_breakdown_level", 4),
        ("rho_breakdown_level", 2.0),
        ("beta_delta_max", 0.0),
        ("beta_delta_max", -1.0),
        ("beta_delta_max", 200.0),
        ("beta_delta_max", "25"),
    ],
)
def test_validation_rejects_bad_values(tmp_path, field, value):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"][field] = value
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_validation_rejects_unknown_profile(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["paper"] = payload["live"]
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_validation_rejects_unknown_field(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["foo"] = "bar"
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_validation_requires_all_fields(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    del payload["live"]["eg_threshold"]
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_validation_requires_both_profiles(tmp_path):
    target = tmp_path / "runtime.json"
    payload = {"live": _valid_payload()["live"]}
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_get_profile_returns_validated_section(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["replay"]["eg_bars"] = 1000
    runtime_config.save_runtime_config(payload, target)

    live = runtime_config.get_profile("live", target)
    replay = runtime_config.get_profile("replay", target)
    assert live["eg_bars"] == 250
    assert replay["eg_bars"] == 1000


def test_get_profile_rejects_unknown_name(tmp_path):
    with pytest.raises(ValueError):
        runtime_config.get_profile("paper", tmp_path / "runtime.json")


def test_save_normalises_int_to_float(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["eg_threshold"] = 1  # int 1 → float 1.0
    payload["live"]["beta_delta_max"] = 25  # int → float
    saved = runtime_config.save_runtime_config(payload, target)
    assert isinstance(saved["live"]["eg_threshold"], float)
    assert isinstance(saved["live"]["beta_delta_max"], float)
    on_disk = json.loads(target.read_text(encoding="utf-8"))
    assert on_disk["live"]["eg_threshold"] == 1.0
