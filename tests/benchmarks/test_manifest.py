import json

import pytest
from benchmarks.analysis.manifest import (
    RunManifest,
    known_cell_ids,
    known_exclusion_reason,
    load_manifest,
)


def _placement(**over):
    p = {
        "run_mode": "editor-game",
        "container_image": "img@sha256:x",
        "observer_env": "bench-observer:universe-devel",
        "engine_build_id": "b4c93e55-fc8f-42fc-b377-358910364e1c",
    }
    p.update(over)
    return p


def _valid_kwargs() -> dict:
    return {
        "cell": "A",
        "approach": "extension",
        "map_name": "Town10HD_Opt",
        "run_index": 1,
        "arm": "static",
        "harness_git_sha": "abc123",
        "patches_git_sha": "def456",
        "transport": {
            "rmw": "rmw_cyclonedds_cpp",
            "shm_enabled": False,
            "dds_profile_sha256": "0" * 64,
        },
        "carla_version": "0.10-fork",
        "autoware_image": "ghcr.io/x@sha256:aa",
        "started_at_ns": 1_000,
        "placement": _placement(),
    }


@pytest.fixture
def valid_kwargs() -> dict:
    return _valid_kwargs()


def _valid() -> RunManifest:
    return RunManifest(**_valid_kwargs())


def test_roundtrip(tmp_path):
    m = _valid()
    m.save(tmp_path / "manifest.json")
    loaded = load_manifest(tmp_path / "manifest.json")
    assert loaded == m
    assert loaded.validate() == []


def test_validate_rejects_bad_approach():
    m = _valid()
    object.__setattr__(m, "approach", "banana")
    errs = m.validate()
    assert any("approach" in e for e in errs)


def test_validate_requires_transport_keys():
    m = _valid()
    object.__setattr__(m, "transport", {"rmw": "x"})
    errs = m.validate()
    assert any("transport" in e for e in errs)


def test_validate_rejects_bad_arm():
    m = _valid()
    object.__setattr__(m, "arm", "banana")
    errs = m.validate()
    assert any("arm" in e for e in errs)


def test_validate_requires_exclusion_reason_when_excluded():
    m = _valid()
    object.__setattr__(m, "excluded", True)
    errs = m.validate()
    assert any("exclusion_reason" in e for e in errs)


def test_validate_excluded_with_reason_is_clean():
    m = _valid()
    object.__setattr__(m, "excluded", True)
    object.__setattr__(m, "exclusion_reason", "crash:observer")
    assert m.validate() == []


def test_validate_excluded_with_prefixed_reason_is_clean():
    """`harness:<commit>` (criterion 3) carries a variable detail after the
    prefix, unlike the fixed-string reasons above."""
    m = _valid()
    object.__setattr__(m, "excluded", True)
    object.__setattr__(m, "exclusion_reason", "harness:abc1234")
    assert m.validate() == []


def test_validate_rejects_an_unregistered_exclusion_reason():
    """The fix for the drift where run.sh emitted exclusion reasons
    config/exclusions.md never registered: validate() used to only check
    that exclusion_reason was non-empty, so an unregistered reason (a typo,
    or a criterion that was dropped from exclusions.md) reached the results
    tree silently. Free text -- not a known prefix or literal -- must be
    rejected the same way an empty reason already is."""
    m = _valid()
    object.__setattr__(m, "excluded", True)
    object.__setattr__(m, "exclusion_reason", "sensor dropout mid-run")
    errs = m.validate()
    assert any("exclusion_reason" in e and "does not match" in e for e in errs)


@pytest.mark.parametrize(
    "reason",
    [
        "crash:cell-launch",
        "crash:observer",
        "crash:sampler",
        "crash:collect_gt",
        "crash:clock_watchdog",
        "gate:arm-failed",
        "gate:control_cmd-silent",
        "gate:injector-failed",
        "stall:clock",
        "stall:unpaced-window-cap",
        "warmup:nishi",
        "harness:0123abcd",
        "hostload:9.5",
        "port:2000",
        "buildid:/home/x/carla-extension",
    ],
)
def test_known_exclusion_reason_accepts_every_reason_run_sh_can_emit(reason):
    """One entry per emit site in run.sh (and preflight.sh's mid-run cases),
    so a future reason string added there without a matching registration
    here fails this test instead of Task 22's tabulation."""
    assert known_exclusion_reason(reason)


def test_known_exclusion_reason_rejects_free_text():
    assert not known_exclusion_reason("something went wrong")


def test_known_cell_ids_comes_from_the_pre_registered_registry():
    ids = known_cell_ids()
    assert {"A", "B", "E0", "CAL-rmw"} <= ids
    assert "A-typo" not in ids


def test_validate_rejects_unregistered_cell():
    """A typo'd cell id files the run under its own results/<typo>/, which
    report.main() then renders as a separate cell -- splitting a duel's runs
    across two tables so neither meets the pre-registered n >= 10. It has to
    be caught at the manifest, which is the only place the id is written."""
    m = _valid()
    object.__setattr__(m, "cell", "AA")
    errs = m.validate()
    assert any("cell" in e for e in errs)


def test_save_refuses_to_write_an_invalid_manifest(tmp_path):
    m = _valid()
    object.__setattr__(m, "arm", "banana")
    path = tmp_path / "manifest.json"
    with pytest.raises(ValueError, match="arm"):
        m.save(path)
    assert not path.exists()


def test_placement_missing_keys_rejected(valid_kwargs):
    m = RunManifest(**{**valid_kwargs, "placement": {}})
    errs = m.validate()
    assert any("placement missing keys" in e for e in errs)


def test_placement_engine_build_id_required_for_ue_approaches(valid_kwargs):
    p = _placement()
    del p["engine_build_id"]
    m = RunManifest(**{**valid_kwargs, "approach": "extension", "placement": p})
    assert any("engine_build_id" in e for e in m.validate())


def test_duel_admissible_defaults_false(valid_kwargs):
    """Fail-closed default (amendment 2026-07-30, Task 15b). Defaulting
    TRUE would make a forgotten declaration silently contaminate the
    primary duel's equivalence verdict; defaulting FALSE makes it show up
    as an already-implemented UNDER-N / insufficient-data row. The duel
    path declares it explicitly (scripts/duel.sh -> run.sh --duel), so
    this default costs the duel nothing."""
    assert RunManifest(**valid_kwargs).duel_admissible is False


def test_validate_rejects_a_non_bool_duel_admissible(valid_kwargs):
    """The string "false" is TRUTHY. A truthiness test at the consumer
    would read a hand-edited or externally-generated `"duel_admissible":
    "false"` as ADMISSIBLE -- silent contamination through the one path
    this field exists to close -- so the type is checked at the manifest,
    the single place the value is written."""
    m = RunManifest(**{**valid_kwargs, "duel_admissible": "false"})
    errs = m.validate()
    assert any("duel_admissible must be a bool" in e for e in errs)


def test_duel_admissible_survives_a_roundtrip(tmp_path, valid_kwargs):
    m = RunManifest(**{**valid_kwargs, "duel_admissible": True})
    m.save(tmp_path / "manifest.json")
    assert load_manifest(tmp_path / "manifest.json").duel_admissible is True


def test_a_manifest_written_before_the_amendment_reads_as_not_duel_data(tmp_path):
    """Every manifest already in benchmarks/results/ predates the field,
    so its JSON has no such key. Those runs must load (the dataclass
    default supplies it) and must read as NOT duel data -- which is both
    true of them and the safe direction. Byte-identical retention of the
    existing results tree depends on this: nothing has to be rewritten."""
    m = _valid()
    path = tmp_path / "manifest.json"
    m.save(path)
    doc = json.loads(path.read_text())
    del doc["duel_admissible"]
    path.write_text(json.dumps(doc))
    loaded = load_manifest(path)
    assert loaded.duel_admissible is False
    assert loaded.validate() == []


def test_placement_engine_build_id_not_required_for_bridge(valid_kwargs):
    p = _placement()
    del p["engine_build_id"]
    m = RunManifest(**{**valid_kwargs, "approach": "python-bridge", "cell": "E", "placement": p})
    assert m.validate() == []
