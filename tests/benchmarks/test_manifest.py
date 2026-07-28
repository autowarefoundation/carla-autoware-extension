import pytest
from benchmarks.analysis.manifest import RunManifest, known_cell_ids, load_manifest


def _placement(**over):
    p = {"run_mode": "editor-game", "container_image": "img@sha256:x",
         "observer_env": "bench-observer:universe-devel",
         "engine_build_id": "b4c93e55-fc8f-42fc-b377-358910364e1c"}
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
    object.__setattr__(m, "exclusion_reason", "sensor dropout mid-run")
    assert m.validate() == []


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


def test_placement_engine_build_id_not_required_for_bridge(valid_kwargs):
    p = _placement()
    del p["engine_build_id"]
    m = RunManifest(**{**valid_kwargs, "approach": "python-bridge",
                       "cell": "E", "placement": p})
    assert m.validate() == []
