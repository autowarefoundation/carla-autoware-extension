"""write_manifest: the CLI that puts manifest.json in a run directory.

Every test drives `main()` exactly as run.sh does (argv in, exit code out),
so what is verified is the command contract, not an internal helper.
"""

from __future__ import annotations

import json

import pytest

from benchmarks.analysis.manifest import load_manifest
from benchmarks.scripts import write_manifest

PLACEMENT = {
    "run_mode": "editor-game",
    "container_image": "ghcr.io/x@sha256:aa",
    "observer_env": {"image": "bench-observer:universe-devel"},
    "engine_build_id": "4210e602-78ec-46e1-8f2f-03fadbe036a3",
}


def _argv(run_dir, **over) -> list[str]:
    args = {
        "--run-dir": str(run_dir),
        "--cell": "A",
        "--arm": "static",
        "--rmw": "rmw_cyclonedds_cpp",
        "--shm": "off",
        "--dds-profile": "none",
        "--carla-version": "0.10-fork",
        "--autoware-image": "ghcr.io/x@sha256:aa",
        "--placement-json": json.dumps(PLACEMENT),
    }
    args.update(over)
    return [tok for kv in args.items() for tok in kv]


def test_creates_a_valid_manifest(tmp_path):
    run_dir = tmp_path / "A" / "run-007"
    assert write_manifest.main(_argv(run_dir)) == 0
    m = load_manifest(run_dir / "manifest.json")
    assert m.validate() == []
    assert m.cell == "A"
    # approach/map come from cells.yaml, never from the command line.
    assert (m.approach, m.map_name) == ("extension", "Town10HD_Opt")
    # run_index is derived from the directory name, not passed separately.
    assert m.run_index == 7
    assert m.transport == {
        "rmw": "rmw_cyclonedds_cpp",
        "shm_enabled": False,
        "dds_profile_sha256": "",
    }
    assert m.placement == PLACEMENT
    assert m.excluded is False
    # Provenance is computed, so it is present and looks like a sha -- with the
    # `-dirty` marker when the working tree is not HEAD, which is the normal
    # state while developing and must not fail this assertion.
    assert len(m.harness_git_sha.removesuffix("-dirty")) == 40
    assert m.started_at_ns > 0


def test_provenance_marks_a_dirty_tree(tmp_path, monkeypatch):
    """A dirty tree must be VISIBLE in the record, not silently absorbed.

    Without the marker the field asserts benchmarks/README.md's tie-back
    guarantee ("any result can be tied back to the exact analysis code that
    scored it") for code that was never committed -- which is how
    results/E/run-002..004 came to name a commit that cannot contain the
    `save_stage_logs` output those runs carry.
    """
    monkeypatch.setattr(write_manifest, "tree_is_dirty", lambda: True)
    run_dir = tmp_path / "A" / "run-001"
    assert write_manifest.main(_argv(run_dir)) == 0
    m = load_manifest(run_dir / "manifest.json")
    assert m.harness_git_sha.endswith("-dirty")
    assert len(m.harness_git_sha) == 40 + len("-dirty")


def test_provenance_is_unsuffixed_on_a_clean_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(write_manifest, "tree_is_dirty", lambda: False)
    run_dir = tmp_path / "A" / "run-001"
    assert write_manifest.main(_argv(run_dir)) == 0
    m = load_manifest(run_dir / "manifest.json")
    assert not m.harness_git_sha.endswith("-dirty")
    assert len(m.harness_git_sha) == 40


def test_dirty_test_excludes_the_results_tree_and_untracked_files(monkeypatch):
    """The run writes into benchmarks/results/ AS IT RUNS.

    If that path counted, every manifest would be marked dirty by its own run
    directory and the marker would carry no information at all. Asserted on the
    git invocation because that is where the exclusion lives; a fixture repo
    would test git's pathspec handling rather than this function's contract.
    """
    seen: list[tuple] = []
    monkeypatch.setattr(write_manifest, "_git", lambda *a: seen.append(a) or "")
    assert write_manifest.tree_is_dirty() is False
    assert seen == [
        (
            "status",
            "--porcelain",
            "--untracked-files=no",
            "--",
            ".",
            ":(exclude)benchmarks/results",
        )
    ]


def test_dirty_test_reports_a_modified_tracked_file(monkeypatch):
    monkeypatch.setattr(write_manifest, "_git", lambda *a: " M benchmarks/run.sh\n")
    assert write_manifest.tree_is_dirty() is True


def test_shm_on_records_true(tmp_path):
    run_dir = tmp_path / "A" / "run-001"
    assert write_manifest.main(_argv(run_dir, **{"--shm": "on"})) == 0
    assert load_manifest(run_dir / "manifest.json").transport["shm_enabled"] is True


def test_dds_profile_hashes_the_file(tmp_path):
    profile = tmp_path / "cyclonedds.xml"
    profile.write_text("<CycloneDDS/>\n")
    run_dir = tmp_path / "A" / "run-002"
    assert write_manifest.main(_argv(run_dir, **{"--dds-profile": str(profile)})) == 0
    recorded = load_manifest(run_dir / "manifest.json").transport["dds_profile_sha256"]
    import hashlib

    assert recorded == hashlib.sha256(profile.read_bytes()).hexdigest()


def test_missing_dds_profile_file_refuses_to_write(tmp_path, capsys):
    run_dir = tmp_path / "A" / "run-003"
    rc = write_manifest.main(_argv(run_dir, **{"--dds-profile": str(tmp_path / "nope.xml")}))
    assert rc == write_manifest.EXIT_BAD_ARGS
    assert "is not a file" in capsys.readouterr().err
    assert not run_dir.exists()


def test_unregistered_cell_refuses_to_write(tmp_path, capsys):
    """The typo-guard: an unregistered cell never reaches the results tree.

    cell_info's lookup fires before RunManifest.save() does, so this asserts
    the OUTCOME (nothing written, exit 2, the id named) rather than which of
    the two layers rejected it.
    """
    run_dir = tmp_path / "Q" / "run-001"
    assert write_manifest.main(_argv(run_dir, **{"--cell": "Q"})) == write_manifest.EXIT_BAD_ARGS
    assert "unknown cell 'Q'" in capsys.readouterr().err
    assert not run_dir.exists()


def test_invalid_arm_refuses_to_write(tmp_path, capsys):
    """Reaches the manifest's own validation: the arm is passed straight
    through (cells.yaml's per-cell `arms` is run.sh's step-1 check), so
    validate() is what rejects it -- the P0 guarantee, exercised through the
    CLI that every run uses.

    Regression: the directory itself must not survive either. It used to be
    created before the write was attempted, so a refusal left an empty
    run-NNN/ with no manifest -- a directory that consumed a run index and
    that no consumer could read or attribute, because there was no manifest
    to mark excluded.
    """
    run_dir = tmp_path / "A" / "run-004"
    rc = write_manifest.main(_argv(run_dir, **{"--arm": "sideways"}))
    assert rc == write_manifest.EXIT_BAD_ARGS
    assert "invalid run manifest" in capsys.readouterr().err
    assert not run_dir.exists()


def test_bad_placement_json_refuses_to_write(tmp_path, capsys):
    run_dir = tmp_path / "A" / "run-005"
    rc = write_manifest.main(_argv(run_dir, **{"--placement-json": "{not json"}))
    assert rc == write_manifest.EXIT_BAD_ARGS
    assert "not valid JSON" in capsys.readouterr().err
    assert not run_dir.exists()


def test_placement_missing_required_key_refuses_to_write(tmp_path, capsys):
    run_dir = tmp_path / "A" / "run-006"
    thin = {k: v for k, v in PLACEMENT.items() if k != "engine_build_id"}
    rc = write_manifest.main(_argv(run_dir, **{"--placement-json": json.dumps(thin)}))
    assert rc == write_manifest.EXIT_BAD_ARGS
    assert "engine_build_id" in capsys.readouterr().err
    assert not run_dir.exists()


def test_misnamed_run_dir_refuses_to_write(tmp_path, capsys):
    run_dir = tmp_path / "A" / "run7"
    assert write_manifest.main(_argv(run_dir)) == write_manifest.EXIT_BAD_ARGS
    assert "run-<NNN>" in capsys.readouterr().err
    assert not run_dir.exists()


def test_exclude_rewrites_in_place(tmp_path):
    run_dir = tmp_path / "A" / "run-009"
    assert write_manifest.main(_argv(run_dir)) == 0
    before = load_manifest(run_dir / "manifest.json")

    rc = write_manifest.main(["--run-dir", str(run_dir), "--exclude", "stall:clock"])
    assert rc == 0
    after = load_manifest(run_dir / "manifest.json")
    assert after.excluded is True
    assert after.exclusion_reason == "stall:clock"
    assert after.validate() == []
    # Nothing else moves: an excluded run keeps its full provenance.
    assert after.started_at_ns == before.started_at_ns
    assert after.harness_git_sha == before.harness_git_sha
    assert after.transport == before.transport


def test_exclude_without_a_manifest_fails(tmp_path, capsys):
    run_dir = tmp_path / "A" / "run-010"
    run_dir.mkdir(parents=True)
    rc = write_manifest.main(["--run-dir", str(run_dir), "--exclude", "stall:clock"])
    assert rc == write_manifest.EXIT_BAD_ARGS
    assert "no manifest to exclude" in capsys.readouterr().err


def test_exclude_with_empty_reason_refuses(tmp_path, capsys):
    run_dir = tmp_path / "A" / "run-011"
    assert write_manifest.main(_argv(run_dir)) == 0
    rc = write_manifest.main(["--run-dir", str(run_dir), "--exclude", ""])
    assert rc == write_manifest.EXIT_BAD_ARGS
    assert "exclusion_reason" in capsys.readouterr().err
    # The un-excluded manifest survives the refusal.
    assert load_manifest(run_dir / "manifest.json").excluded is False


def test_create_mode_names_every_missing_argument(tmp_path, capsys):
    rc = write_manifest.main(["--run-dir", str(tmp_path / "A" / "run-001")])
    assert rc == write_manifest.EXIT_BAD_ARGS
    err = capsys.readouterr().err
    for flag in ("--cell", "--arm", "--rmw", "--placement-json"):
        assert flag in err


@pytest.mark.parametrize("name,expected", [("run-000", 0), ("run-012", 12), ("run-105", 105)])
def test_run_index_from_dir(tmp_path, name, expected):
    assert write_manifest.run_index_from_dir(tmp_path / name) == expected


def test_duel_flag_is_opt_in(tmp_path):
    """`--duel` is the ONE thing this tool cannot compute (amendment
    2026-07-30, Task 15b): whether the run belongs to the primary duel's
    interleaved A,B,A,B design. Absent, the run is not duel data."""
    plain = tmp_path / "A" / "run-020"
    assert write_manifest.main(_argv(plain)) == 0
    assert load_manifest(plain / "manifest.json").duel_admissible is False

    declared = tmp_path / "A" / "run-021"
    assert write_manifest.main([*_argv(declared), "--duel"]) == 0
    assert load_manifest(declared / "manifest.json").duel_admissible is True


def test_exclude_preserves_the_duel_declaration(tmp_path):
    """Excluding a duel run must not silently reclassify it: `excluded`
    and `duel_admissible` answer different questions, and a run that was
    duel data and then crashed is still duel data that crashed."""
    run_dir = tmp_path / "A" / "run-022"
    assert write_manifest.main([*_argv(run_dir), "--duel"]) == 0
    assert write_manifest.main(["--run-dir", str(run_dir), "--exclude", "stall:clock"]) == 0
    after = load_manifest(run_dir / "manifest.json")
    assert (after.excluded, after.duel_admissible) == (True, True)


def test_create_stamps_duel_id(tmp_path):
    """duel_id partitions admission POOLS: duel_admissible says "this run
    is duel data", duel_id says WHICH duel. Without it, `duel_verdict.py
    A B-cyc` would pull cell A's P3 static pool (run-003..012) into the P4
    duel -- mixing pre/post-harness-sha runs and non-interleaved partners
    (spec 2026-08-03, section 1d)."""
    run_dir = tmp_path / "A" / "run-001"
    assert write_manifest.main([*_argv(run_dir), "--duel", "--duel-id", "A+B-cyc"]) == 0
    m = load_manifest(run_dir / "manifest.json")
    assert m.duel_id == "A+B-cyc"


def test_create_defaults_duel_id_empty(tmp_path):
    run_dir = tmp_path / "A" / "run-002"
    assert write_manifest.main(_argv(run_dir)) == 0
    m = load_manifest(run_dir / "manifest.json")
    assert m.duel_id == ""


def test_create_stamps_class_id(tmp_path):
    """class_id partitions SWEEP scoring pools the way duel_id partitions
    duel admission pools (Amendment 2026-08-04): `arm` says which sweep arm
    a run belongs to, class_id says which sweep CLASS's point it measures.
    Without it, `sweep_verdict.py A --class 32ch` renders Task 14's vlp16
    rows under a "class 32ch" heading -- demonstrated live, and guaranteed
    to corrupt the next task's gate facts once 32ch runs land in the same
    flat run-NNN/ sequence."""
    run_dir = tmp_path / "A" / "run-003"
    assert write_manifest.main([*_argv(run_dir, **{"--arm": "paced"}), "--class-id", "32ch"]) == 0
    m = load_manifest(run_dir / "manifest.json")
    assert m.class_id == "32ch"


def test_create_defaults_class_id_empty(tmp_path):
    """The legacy/no-class value, matching RunManifest.class_id's own
    default: a duel run (or any run taken with no `--class`) carries no
    class, and the pool rule's legacy clause is what decides what "" means
    at scoring time -- not this tool."""
    run_dir = tmp_path / "A" / "run-004"
    assert write_manifest.main(_argv(run_dir)) == 0
    m = load_manifest(run_dir / "manifest.json")
    assert m.class_id == ""


def test_exclude_preserves_the_class_declaration(tmp_path):
    """Same rationale as `test_exclude_preserves_the_duel_declaration`
    above: `excluded` and `class_id` answer different questions, and a
    32ch run that crashed is still a 32ch run that crashed. Rewrite mode
    must not silently reclassify it into the legacy "" pool, which the
    pool rule would then read as vlp16."""
    run_dir = tmp_path / "A" / "run-005"
    assert write_manifest.main([*_argv(run_dir, **{"--arm": "paced"}), "--class-id", "32ch"]) == 0
    assert write_manifest.main(["--run-dir", str(run_dir), "--exclude", "stall:clock"]) == 0
    after = load_manifest(run_dir / "manifest.json")
    assert (after.excluded, after.class_id) == (True, "32ch")
