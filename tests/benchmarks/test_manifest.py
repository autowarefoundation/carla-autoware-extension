from benchmarks.analysis.manifest import RunManifest, load_manifest


def _valid() -> RunManifest:
    return RunManifest(
        cell="A",
        approach="extension",
        map_name="Town10HD_Opt",
        run_index=1,
        arm="static",
        harness_git_sha="abc123",
        patches_git_sha="def456",
        transport={
            "rmw": "rmw_cyclonedds_cpp",
            "shm_enabled": False,
            "dds_profile_sha256": "0" * 64,
        },
        carla_version="0.10-fork",
        autoware_image="ghcr.io/x@sha256:aa",
        started_at_ns=1_000,
    )


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
