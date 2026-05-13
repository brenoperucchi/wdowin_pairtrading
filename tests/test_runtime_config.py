"""Tests for core.runtime_config (load/save/validate)."""
from __future__ import annotations

import copy
import json
from pathlib import Path

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
    """DEFAULTS has both profiles and every runtime field per profile."""
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
        ("z_anomaly", 0.0),
        ("z_anomaly", -1.0),
        ("z_anomaly", 10.5),
        ("z_anomaly", "4.0"),
        ("z_anomaly", True),
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
    assert live["eg_bars"] == runtime_config.DEFAULTS["live"]["eg_bars"]
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


def test_validate_runtime_config_normalises_without_writing(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["replay"]["eg_threshold"] = 1

    validated = runtime_config.validate_runtime_config(payload)

    assert validated["replay"]["eg_threshold"] == 1.0
    assert not target.exists()


@pytest.mark.parametrize(
    "value",
    [
        "CONS_BASE",          # not a list
        ["CONS_BASE", 1],     # entry not a string
        ["CONS_BASE", "FOO"], # unknown strategy
        ["CONS_BASE", "CONS_BASE"],  # duplicate
    ],
)
def test_validation_rejects_bad_eg_strategies(tmp_path, value):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["eg_strategies"] = value
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_validation_accepts_empty_eg_strategies(tmp_path):
    """Empty list = EG bypassed for ALL strategies (legitimate config)."""
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["eg_strategies"] = []
    saved = runtime_config.save_runtime_config(payload, target)
    assert saved["live"]["eg_strategies"] == []


def test_validation_accepts_full_eg_strategies(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["eg_strategies"] = list(runtime_config.VALID_STRATEGIES)
    saved = runtime_config.save_runtime_config(payload, target)
    assert saved["live"]["eg_strategies"] == list(runtime_config.VALID_STRATEGIES)


def test_defaults_eg_strategies_match_miqueias_split():
    """Live + replay default to checking EG only on CONS_BASE and WDO_NWE."""
    expected = ["CONS_BASE", "WDO_NWE"]
    assert runtime_config.DEFAULTS["live"]["eg_strategies"] == expected
    assert runtime_config.DEFAULTS["replay"]["eg_strategies"] == expected


def test_defaults_beta_delta_max_aligned_with_upstream():
    """Both profiles default to 15.0 — matches upstream `beta_status.level < 2`."""
    assert runtime_config.DEFAULTS["live"]["beta_delta_max"] == 15.0
    assert runtime_config.DEFAULTS["replay"]["beta_delta_max"] == 15.0


def test_defaults_z_anomaly_matches_core_config():
    """Both profiles default to 4.0 — same as core.config.Z_ANOMALY fallback."""
    assert runtime_config.DEFAULTS["live"]["z_anomaly"] == 4.0
    assert runtime_config.DEFAULTS["replay"]["z_anomaly"] == 4.0


def test_committed_runtime_json_matches_aligned_defaults():
    target = Path(__file__).resolve().parents[1] / "config" / "runtime.json"
    raw = json.loads(target.read_text(encoding="utf-8"))
    loaded = runtime_config.load_runtime_config(target)

    assert raw["live"]["beta_delta_max"] == runtime_config.DEFAULTS["live"]["beta_delta_max"]
    assert raw["replay"]["beta_delta_max"] == runtime_config.DEFAULTS["replay"]["beta_delta_max"]
    assert "z_anomaly" in raw["live"]
    assert "z_anomaly" in raw["replay"]
    assert loaded == raw


def test_load_backfills_missing_fields_from_defaults(tmp_path):
    """An on-disk config from an older slice (no eg_strategies) must still load."""
    target = tmp_path / "runtime.json"
    legacy = {
        "live": {
            "eg_threshold": 0.05,
            "eg_bars": 250,
            "eg_recalc": "bar",
            "rho_breakdown_level": 2,
            "beta_delta_max": 25.0,
        },
        "replay": {
            "eg_threshold": 0.10,
            "eg_bars": 2240,
            "eg_recalc": "daily",
            "rho_breakdown_level": 2,
            "beta_delta_max": 25.0,
        },
    }
    target.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = runtime_config.load_runtime_config(target)

    # Original fields preserved
    assert loaded["live"]["eg_threshold"] == 0.05
    assert loaded["replay"]["eg_bars"] == 2240
    # Missing field backfilled from DEFAULTS
    assert loaded["live"]["eg_strategies"] == runtime_config.DEFAULTS["live"]["eg_strategies"]
    assert loaded["replay"]["eg_strategies"] == runtime_config.DEFAULTS["replay"]["eg_strategies"]


# ─── simulation sub-block ───────────────────────────────────────────────────


def test_simulation_defaults_disabled_in_both_profiles():
    """enabled=false in both profiles preserves parity until operator flips it."""
    for profile in runtime_config.PROFILES:
        sim = runtime_config.DEFAULTS[profile]["simulation"]
        assert sim["enabled"] is False
        assert sim["entry_slippage_pts"] == 5.0
        assert sim["exit_slippage_pts"] == 5.0
        assert sim["cost_per_contract_rt_brl"] == 1.0
        assert sim["intra_bar_sl_tp"] is True
        assert sim["exit_at_sl_tp_level"] is True
        assert sim["conflict_rule"] == "sl_first"


def test_simulation_defaults_in_committed_runtime_json():
    target = Path(__file__).resolve().parents[1] / "config" / "runtime.json"
    raw = json.loads(target.read_text(encoding="utf-8"))
    for profile in runtime_config.PROFILES:
        assert "simulation" in raw[profile]
        assert raw[profile]["simulation"]["enabled"] is False


def test_simulation_roundtrip_with_enabled_replay(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["replay"]["simulation"]["enabled"] = True
    payload["replay"]["simulation"]["entry_slippage_pts"] = 7.5
    payload["replay"]["simulation"]["conflict_rule"] = "tp_first"

    saved = runtime_config.save_runtime_config(payload, target)
    assert saved["replay"]["simulation"]["enabled"] is True
    assert saved["replay"]["simulation"]["entry_slippage_pts"] == 7.5
    assert saved["replay"]["simulation"]["conflict_rule"] == "tp_first"
    # Live still defaulted, untouched
    assert saved["live"]["simulation"]["enabled"] is False

    reloaded = runtime_config.load_runtime_config(target)
    assert reloaded == saved


@pytest.mark.parametrize(
    "field,value",
    [
        ("enabled", "true"),       # string, not bool
        ("enabled", 1),            # int, not bool
        ("enabled", None),
        ("entry_slippage_pts", -0.1),
        ("entry_slippage_pts", 50.1),
        ("entry_slippage_pts", "5"),
        ("entry_slippage_pts", True),       # bool isn't a number
        ("exit_slippage_pts", -1.0),
        ("exit_slippage_pts", 50.1),
        ("cost_per_contract_rt_brl", -0.01),
        ("cost_per_contract_rt_brl", 50.1),
        ("intra_bar_sl_tp", "yes"),
        ("intra_bar_sl_tp", 1),
        ("exit_at_sl_tp_level", "no"),
        ("conflict_rule", "first"),         # not in enum
        ("conflict_rule", ""),
        ("conflict_rule", None),
    ],
)
def test_simulation_validation_rejects_bad_values(tmp_path, field, value):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["replay"]["simulation"][field] = value
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_simulation_validation_rejects_unknown_subfield(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["simulation"]["foo"] = "bar"
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_simulation_validation_requires_all_subfields(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    del payload["replay"]["simulation"]["conflict_rule"]
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_simulation_validation_rejects_when_not_object(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["simulation"] = "disabled"
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_load_backfills_missing_simulation_block(tmp_path):
    """Legacy on-disk config without ``simulation`` must still load."""
    target = tmp_path / "runtime.json"
    legacy = {
        "live": {
            "eg_threshold": 0.05,
            "eg_bars": 250,
            "eg_recalc": "bar",
            "rho_breakdown_level": 2,
            "beta_delta_max": 25.0,
            "eg_strategies": ["CONS_BASE"],
            "z_anomaly": 4.0,
            # simulation missing
        },
        "replay": copy.deepcopy(runtime_config.DEFAULTS["replay"]),
    }
    target.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = runtime_config.load_runtime_config(target)

    assert loaded["live"]["simulation"] == runtime_config.SIMULATION_DEFAULTS
    # Operator-set fields preserved
    assert loaded["live"]["eg_threshold"] == 0.05


def test_load_backfills_missing_simulation_subfields(tmp_path):
    """Partial ``simulation`` block: missing sub-keys fill from SIMULATION_DEFAULTS."""
    target = tmp_path / "runtime.json"
    partial = copy.deepcopy(runtime_config.DEFAULTS)
    # Operator only declared two keys — the rest were added in a later slice.
    partial["replay"]["simulation"] = {
        "enabled": True,
        "entry_slippage_pts": 8.0,
    }
    target.write_text(json.dumps(partial), encoding="utf-8")

    loaded = runtime_config.load_runtime_config(target)

    sim = loaded["replay"]["simulation"]
    assert sim["enabled"] is True             # operator value preserved
    assert sim["entry_slippage_pts"] == 8.0   # operator value preserved
    assert sim["exit_slippage_pts"] == runtime_config.SIMULATION_DEFAULTS["exit_slippage_pts"]
    assert sim["conflict_rule"] == runtime_config.SIMULATION_DEFAULTS["conflict_rule"]


def test_save_rejects_missing_simulation_block(tmp_path):
    """Save stays strict: dropping ``simulation`` entirely must be rejected."""
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    del payload["live"]["simulation"]
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(payload, target)


def test_save_does_not_backfill_missing_fields(tmp_path):
    """POST stays strict — payloads missing required fields must still be rejected."""
    target = tmp_path / "runtime.json"
    incomplete = {
        "live": {
            "eg_threshold": 0.10,
            "eg_bars": 250,
            "eg_recalc": "bar",
            "rho_breakdown_level": 2,
            "beta_delta_max": 25.0,
            # eg_strategies missing — save() must reject
        },
        "replay": copy.deepcopy(runtime_config.DEFAULTS["replay"]),
    }
    with pytest.raises(ValueError):
        runtime_config.save_runtime_config(incomplete, target)
    assert not target.exists()
