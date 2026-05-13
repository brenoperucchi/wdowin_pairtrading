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
        # Engine params — signals/regime
        ("window", 29),
        ("window", 1001),
        ("window", 240.0),
        ("window", "240"),
        ("window", True),
        ("z_entry", 0.1),       # exclusive lower bound
        ("z_entry", 0.05),
        ("z_entry", 5.01),
        ("z_entry", "1.4"),
        ("z_entry", True),
        ("z_attention", 0.1),   # exclusive lower bound
        ("z_attention", 0.05),
        ("z_attention", 5.01),
        ("z_attention", "1.2"),
        ("z_attention", True),
        # Engine params — session hours
        ("entry_start_h", -1),
        ("entry_start_h", 24),
        ("entry_start_h", 9.0),
        ("entry_start_m", -1),
        ("entry_start_m", 60),
        ("entry_end_h", -1),
        ("entry_end_h", 24),
        ("entry_end_m", 60),
        ("force_close_h", -1),
        ("force_close_h", 24),
        ("force_close_m", -1),
        ("force_close_m", 60),
        # Engine params — trade SL/TP/BE (BUY)
        ("buy_sl", 9),
        ("buy_sl", 5001),
        ("buy_sl", 300.0),
        ("buy_sl", "300"),
        ("buy_tp", 9),
        ("buy_tp", 5001),
        ("buy_be_act", -1),
        ("buy_be_act", 5001),
        ("buy_be_lock", -1),
        ("buy_be_lock", 5001),
        # Engine params — trade SL/TP/BE (SELL)
        ("sell_sl", 9),
        ("sell_sl", 5001),
        ("sell_tp", 9),
        ("sell_tp", 5001),
        ("sell_be_act", -1),
        ("sell_be_act", 5001),
        ("sell_be_lock", -1),
        ("sell_be_lock", 5001),
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


# ─── engine params (A'.1 / TASK-16.1) ───────────────────────────────────────


_ENGINE_PARAM_FIELDS = (
    "window",
    "z_entry",
    "z_attention",
    "entry_start_h",
    "entry_start_m",
    "entry_end_h",
    "entry_end_m",
    "force_close_h",
    "force_close_m",
    "buy_sl",
    "buy_tp",
    "buy_be_act",
    "buy_be_lock",
    "sell_sl",
    "sell_tp",
    "sell_be_act",
    "sell_be_lock",
)


def test_engine_params_present_in_fields_tuple():
    for field in _ENGINE_PARAM_FIELDS:
        assert field in runtime_config.FIELDS


def test_engine_param_defaults_match_legacy_core_config():
    """DEFAULTS mirror core.config constants so this slice is a behaviour no-op."""
    from core import config as core_config

    for profile in runtime_config.PROFILES:
        d = runtime_config.DEFAULTS[profile]
        assert d["window"] == core_config.WINDOW
        assert d["z_entry"] == core_config.Z_ENTRY
        assert d["z_attention"] == core_config.Z_ATTENTION
        assert d["entry_start_h"] == core_config.ENTRY_START_H
        assert d["entry_start_m"] == core_config.ENTRY_START_M
        assert d["entry_end_h"] == core_config.ENTRY_END_H
        assert d["entry_end_m"] == core_config.ENTRY_END_M
        assert d["force_close_h"] == core_config.FORCE_CLOSE_H
        assert d["force_close_m"] == core_config.FORCE_CLOSE_M
        assert d["buy_sl"] == core_config.BUY_SL
        assert d["buy_tp"] == core_config.BUY_TP
        assert d["buy_be_act"] == core_config.BUY_BE_ACT
        assert d["buy_be_lock"] == core_config.BUY_BE_LOCK
        assert d["sell_sl"] == core_config.SELL_SL
        assert d["sell_tp"] == core_config.SELL_TP
        assert d["sell_be_act"] == core_config.SELL_BE_ACT
        assert d["sell_be_lock"] == core_config.SELL_BE_LOCK


def test_load_backfills_missing_engine_params(tmp_path):
    """Legacy config (7 risk-gate fields only) loads with engine defaults backfilled.

    AC1 of TASK-16.1: legacy file → load returns 24 leaf fields per profile
    (excluding the ``simulation`` sub-block). Bumped from 23 in TASK-16.2 when
    ``z_attention`` was lifted from core.config into the runtime profile.
    """
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
            # no engine params, no simulation
        },
        "replay": {
            "eg_threshold": 0.10,
            "eg_bars": 2240,
            "eg_recalc": "daily",
            "rho_breakdown_level": 2,
            "beta_delta_max": 15.0,
            "eg_strategies": ["CONS_BASE", "WDO_NWE"],
            "z_anomaly": 4.0,
        },
    }
    target.write_text(json.dumps(legacy), encoding="utf-8")

    loaded = runtime_config.load_runtime_config(target)

    for profile in runtime_config.PROFILES:
        # Risk-gate values preserved
        keys = set(loaded[profile])
        # 7 risk-gate + 17 engine + 1 simulation = 25 keys
        assert keys == set(runtime_config.FIELDS)
        # Engine params populated from DEFAULTS
        for field in _ENGINE_PARAM_FIELDS:
            assert loaded[profile][field] == runtime_config.DEFAULTS[profile][field]
        # Simulation backfilled too
        assert loaded[profile]["simulation"] == runtime_config.SIMULATION_DEFAULTS

    # 7 risk-gate + 17 engine = 24 leaf fields if simulation (sub-block) is
    # excluded. Bumped from 23 in TASK-16.2 when z_attention was lifted into
    # the runtime profile.
    leaf_count = len([k for k in runtime_config.FIELDS if k != "simulation"])
    assert leaf_count == 24


def test_engine_params_roundtrip_save_load(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["window"] = 360
    payload["live"]["z_entry"] = 1.8
    payload["live"]["buy_sl"] = 250
    payload["replay"]["window"] = 480
    payload["replay"]["force_close_m"] = 35
    payload["replay"]["sell_be_lock"] = 50

    saved = runtime_config.save_runtime_config(payload, target)
    assert saved["live"]["window"] == 360
    assert saved["live"]["z_entry"] == 1.8
    assert saved["live"]["buy_sl"] == 250
    assert saved["replay"]["window"] == 480
    assert saved["replay"]["force_close_m"] == 35
    assert saved["replay"]["sell_be_lock"] == 50

    reloaded = runtime_config.load_runtime_config(target)
    assert reloaded == saved


def test_engine_params_z_entry_normalises_int_to_float(tmp_path):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["z_entry"] = 2  # int → float
    saved = runtime_config.save_runtime_config(payload, target)
    assert isinstance(saved["live"]["z_entry"], float)
    assert saved["live"]["z_entry"] == 2.0


def test_engine_params_accept_boundary_values(tmp_path):
    """Inclusive bounds — boundary values must validate."""
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["window"] = 30          # lower bound (inclusive)
    payload["replay"]["window"] = 1000      # upper bound (inclusive)
    payload["live"]["z_entry"] = 5.0        # upper bound (inclusive)
    # entry_end_m = 59 is field-bound max; bump force_close to match so the
    # cross-field rule (entry_end <= force_close) still holds.
    payload["replay"]["entry_end_h"] = 17
    payload["replay"]["entry_end_m"] = 59
    payload["replay"]["force_close_h"] = 17
    payload["replay"]["force_close_m"] = 59
    payload["live"]["buy_sl"] = 10
    payload["replay"]["sell_tp"] = 5000
    payload["live"]["buy_be_act"] = 0
    saved = runtime_config.save_runtime_config(payload, target)
    assert saved["live"]["window"] == 30
    assert saved["replay"]["window"] == 1000
    assert saved["live"]["z_entry"] == 5.0
    assert saved["replay"]["entry_end_m"] == 59


def test_committed_runtime_json_has_engine_params():
    """The on-disk runtime.json includes every engine param after this slice."""
    target = Path(__file__).resolve().parents[1] / "config" / "runtime.json"
    raw = json.loads(target.read_text(encoding="utf-8"))
    for profile in runtime_config.PROFILES:
        for field in _ENGINE_PARAM_FIELDS:
            assert field in raw[profile], f"missing {profile}.{field}"
        assert raw[profile]["window"] == runtime_config.DEFAULTS[profile]["window"]
        assert raw[profile]["z_entry"] == runtime_config.DEFAULTS[profile]["z_entry"]


# ─── cross-field validators (review of A'.1) ────────────────────────────────


@pytest.mark.parametrize(
    "overrides,error_substring",
    [
        # session hours: start >= end → reject
        ({"entry_start_h": 18}, "entry_start"),
        ({"entry_end_h": 8}, "entry_start"),
        ({"entry_start_h": 17, "entry_start_m": 25}, "entry_start"),  # == end
        ({"entry_start_h": 17, "entry_start_m": 30}, "entry_start"),  # > end
        # session hours: end > force_close → reject
        ({"entry_end_h": 18, "force_close_h": 17, "force_close_m": 40}, "entry_end"),
        ({"entry_end_h": 17, "entry_end_m": 45, "force_close_m": 40}, "entry_end"),
    ],
)
def test_validation_rejects_session_hours_out_of_order(tmp_path, overrides, error_substring):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"].update(overrides)
    with pytest.raises(ValueError, match=error_substring):
        runtime_config.save_runtime_config(payload, target)


@pytest.mark.parametrize(
    "side,overrides,error_substring",
    [
        # be_lock > be_act
        ("buy", {"buy_be_act": 100, "buy_be_lock": 200}, "buy_be_lock"),
        ("sell", {"sell_be_act": 100, "sell_be_lock": 200}, "sell_be_lock"),
        # be_lock == tp (equal not allowed; must be strictly less)
        ("buy", {"buy_be_lock": 800, "buy_be_act": 800}, "buy_be_lock"),
        ("sell", {"sell_be_lock": 800, "sell_be_act": 800}, "sell_be_lock"),
        # be_lock > tp
        ("buy", {"buy_be_lock": 900, "buy_be_act": 900, "buy_tp": 800}, "buy_be_lock"),
        # be_act > tp
        ("buy", {"buy_be_act": 900, "buy_tp": 800}, "buy_be_act"),
        ("sell", {"sell_be_act": 900, "sell_tp": 800}, "sell_be_act"),
    ],
)
def test_validation_rejects_be_tp_inversions(tmp_path, side, overrides, error_substring):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"].update(overrides)
    with pytest.raises(ValueError, match=error_substring):
        runtime_config.save_runtime_config(payload, target)


def test_validation_accepts_boundary_cross_field_values(tmp_path):
    """Non-strict boundaries must validate: end == force_close, be_act == tp, be_lock == be_act."""
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    # entry_end == force_close (allowed)
    payload["live"]["entry_end_h"] = 17
    payload["live"]["entry_end_m"] = 40
    payload["live"]["force_close_h"] = 17
    payload["live"]["force_close_m"] = 40
    # be_act == tp (allowed)
    payload["live"]["buy_be_act"] = 800
    payload["live"]["buy_be_lock"] = 800 - 1  # be_lock < tp strict
    # be_lock == be_act (allowed — silly but not impossible)
    payload["replay"]["sell_be_lock"] = 300
    payload["replay"]["sell_be_act"] = 300
    saved = runtime_config.save_runtime_config(payload, target)
    assert saved["live"]["entry_end_m"] == 40
    assert saved["live"]["buy_be_act"] == 800
    assert saved["replay"]["sell_be_lock"] == 300


def test_committed_defaults_pass_cross_field_validation():
    """The DEFAULTS dict itself must satisfy every cross-field rule (config sanity)."""
    target_path = Path(__file__).resolve().parents[1] / "config" / "runtime.json"
    # load_runtime_config triggers full validation including cross-field checks
    loaded = runtime_config.load_runtime_config(target_path)
    for profile in runtime_config.PROFILES:
        p = loaded[profile]
        start = p["entry_start_h"] * 60 + p["entry_start_m"]
        end = p["entry_end_h"] * 60 + p["entry_end_m"]
        fc = p["force_close_h"] * 60 + p["force_close_m"]
        assert start < end <= fc
        assert p["z_attention"] < p["z_entry"]
        for side in ("buy", "sell"):
            assert p[f"{side}_be_lock"] <= p[f"{side}_be_act"]
            assert p[f"{side}_be_lock"] < p[f"{side}_tp"]
            assert p[f"{side}_be_act"] <= p[f"{side}_tp"]


@pytest.mark.parametrize(
    "z_entry,z_attention",
    [
        (1.4, 1.4),   # equal not allowed; must be strictly less
        (1.2, 1.5),   # attention above entry
        (2.0, 2.0001),
    ],
)
def test_validation_rejects_z_attention_not_below_entry(tmp_path, z_entry, z_attention):
    target = tmp_path / "runtime.json"
    payload = _valid_payload()
    payload["live"]["z_entry"] = z_entry
    payload["live"]["z_attention"] = z_attention
    with pytest.raises(ValueError, match="z_attention"):
        runtime_config.save_runtime_config(payload, target)
