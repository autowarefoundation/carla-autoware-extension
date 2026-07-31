"""Behavioural pins for benchmarks/scripts/verify_tier4_artifact.sh -- the
B-family counterpart to cell A's scripts/e2e/verify_editor_artifact.sh.

These exist because the gap they close was MEASURED, not imagined (Task 17b,
2026-07-30): `grep -rn verify_editor_artifact` over the tree returned exactly
one call site, scripts/e2e/run_e2e.sh:126, which cells/extension.sh reaches at
cells/extension.sh:192 -- and neither cells/tier4-native.sh nor
cells/tier4_autoware.sh reached it or anything like it. Every B-family run in
benchmarks/results/B was therefore produced with no check standing between a
stale plugin .so and a filed measurement, and its manifest recorded
`placement.carla_tree`, a PATH, as the whole of the tree's provenance.

WHAT IS FAITHFUL about the synthetic tree below, and what is not:

* Faithful -- the directory layout, the two gated artifacts and their location
  under Unreal/CarlaUnreal/Plugins/Carla/Binaries/Linux, and the fact that the
  campaign's changes to the tier4 fork live in the WORKING TREE (uncommitted)
  rather than in a commit. That last one is why check 4 (artifact vs HEAD) is
  the weak axis here and check 3 (artifact vs newest source) is the real one.
* Faithful -- the registered-patch comparison is driven, in one test, by the
  REAL benchmarks/patches/tier4-native/*.patch files, so the parser is pinned
  against the artifacts it will actually read.
* NOT faithful -- the ".so" files are a few bytes of text and nothing is
  compiled, linked or loaded. These tests pin the STALENESS ARITHMETIC and the
  identity contract; they do not show that any real build is correct. Live
  validation rides along with the first gated B run.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
GATE = REPO / "benchmarks" / "scripts" / "verify_tier4_artifact.sh"
REAL_PATCH_DIR = REPO / "benchmarks" / "patches" / "tier4-native"

# Fixed epochs, far from `now`, so nothing here depends on wall-clock time.
SRC_EPOCH = 1_700_000_000
ART_EPOCH = SRC_EPOCH + 3600
COMMIT_EPOCH = SRC_EPOCH - 86_400

SOURCES = (
    "LibCarla/source/carla/ros2/ROS2.cpp",
    "LibCarla/source/carla/ros2/publishers/CarlaLidarPublisher.cpp",
    "Unreal/CarlaUnreal/Plugins/Carla/Source/Carla/Carla.cpp",
    "LibCarla/CMakeLists.txt",
    "CMake/Toolchain.cmake",
    "PythonAPI/examples/autoware_demo.py",
)
ARTIFACT_DIR = "Unreal/CarlaUnreal/Plugins/Carla/Binaries/Linux"
EDITOR_SO = f"{ARTIFACT_DIR}/libUnrealEditor-Carla.so"
ROS2_SO = f"{ARTIFACT_DIR}/libcarla-ros2-native.so"


def _git(tree: Path, *args: str, commit_epoch: int = COMMIT_EPOCH) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "bench",
        "GIT_AUTHOR_EMAIL": "bench@example.invalid",
        "GIT_COMMITTER_NAME": "bench",
        "GIT_COMMITTER_EMAIL": "bench@example.invalid",
        "GIT_AUTHOR_DATE": f"{commit_epoch} +0000",
        "GIT_COMMITTER_DATE": f"{commit_epoch} +0000",
    }
    subprocess.run(["git", "-C", str(tree), *args], check=True, env=env, capture_output=True)


def _write(tree: Path, rel: str, text: str) -> Path:
    path = tree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _stamp(tree: Path, *, src: float = SRC_EPOCH, art: float = ART_EPOCH) -> None:
    """Set every source mtime to `src` and every gated artifact's to `art`.

    Called LAST in every setup, because writing a file is itself an mtime
    change: a test that dirties a source and forgets this would be measuring
    `now`, not the epoch it meant to set.
    """
    for rel in SOURCES:
        if (tree / rel).exists():
            os.utime(tree / rel, (src, src))
    for rel in (EDITOR_SO, ROS2_SO):
        if (tree / rel).exists():
            os.utime(tree / rel, (art, art))
    # Any file the test itself added under a scanned root, e.g. the untracked
    # GlibcCompat.c the registered patch set creates.
    for root in ("LibCarla/source", "Unreal/CarlaUnreal/Plugins/Carla/Source", "CMake"):
        for path in (tree / root).rglob("*"):
            if path.is_file():
                os.utime(path, (src, src))


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A synthetic tier4 fork: committed sources, built artifacts, clean."""
    t = tmp_path / "carla-autoware-native"
    t.mkdir()
    _git(t, "init", "-q")
    for rel in SOURCES:
        _write(t, rel, f"// {rel}\n")
    _write(t, EDITOR_SO, "editor plugin bytes\n")
    _write(t, ROS2_SO, "ros2 native bytes\n")
    _git(t, "add", "-A")
    _git(t, "commit", "-q", "-m", "synthetic tier4 tree")
    _stamp(t)
    return t


def run_gate(tree: Path, patch_dir: Path | None = None, **env_extra: str):
    env = {**os.environ, "TIER4_TREE": str(tree)}
    # TIER4_STALE_ACK is read as "set or not set", and set-but-empty is itself a
    # refusal, so an export leaking in from the developer's shell would change
    # what most of these tests measure. Only a test that names it gets it.
    env.pop("TIER4_STALE_ACK", None)
    if patch_dir is not None:
        env["TIER4_PATCH_DIR"] = str(patch_dir)
    env.update(env_extra)
    return subprocess.run(["bash", str(GATE)], capture_output=True, text=True, env=env)


def make_stale(tree: Path, rel: str = "LibCarla/source/carla/ros2/ROS2.cpp") -> None:
    """Push one scanned source past both artifacts -- what check 3 refuses on."""
    os.utime(tree / rel, (ART_EPOCH + 60, ART_EPOCH + 60))


def write_patch(patch_dir: Path, name: str, *paths: str) -> None:
    """A patch file carrying only the `+++ b/<path>` lines the gate actually reads."""
    patch_dir.mkdir(parents=True, exist_ok=True)
    body = "".join(f"--- /dev/null\n+++ b/{p}\n" for p in paths)
    (patch_dir / name).write_text(body)


def kv(stdout: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in stdout.splitlines() if line)


# --- the gate passes on a fresh tree, and says what ran --------------------


def test_fresh_artifacts_pass_and_record_the_trees_identity(tree):
    r = run_gate(tree)
    assert r.returncode == 0, r.stderr
    got = kv(r.stdout)
    assert set(got) == {
        "tier4_git_sha",
        "tier4_worktree",
        "tier4_worktree_paths_sha256",
        "tier4_worktree_content_sha256",
        "tier4_source_sha256",
        "tier4_plugin_sha256",
        "tier4_ros2_native_sha256",
        "tier4_plugin_mtime",
        "tier4_ros2_native_mtime",
        "tier4_newest_source_mtime",
        "tier4_stale_ack",
        "tier4_stale_ack_reason",
        "tier4_stale_ack_artifacts",
    }
    head = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert got["tier4_git_sha"] == head
    assert got["tier4_plugin_mtime"] == str(ART_EPOCH)
    assert got["tier4_newest_source_mtime"] == str(SRC_EPOCH)
    # Emitted unconditionally, exactly as preflight.sh emits map_bundle_pin: an
    # omitted key would make "no acknowledgement was needed" and "this gate is an
    # older version with no acknowledgement at all" the same manifest.
    assert got["tier4_stale_ack"] == "none"
    assert got["tier4_stale_ack_reason"] == "-"
    assert got["tier4_stale_ack_artifacts"] == "-"


def test_stdout_carries_key_value_lines_and_nothing_else(tree):
    """The contract with preflight.sh, which forwards this stdout verbatim into
    the manifest's `placement` block: one stray prose line becomes a junk
    placement key on every B-family run. All prose goes to stderr."""
    r = run_gate(tree)
    assert r.returncode == 0
    for line in r.stdout.splitlines():
        assert "=" in line and " " not in line.split("=", 1)[0], line
    assert "OK:" in r.stderr


def test_the_recorded_digests_are_of_the_artifacts_actually_gated(tree):
    r = run_gate(tree)
    got = kv(r.stdout)
    for key, rel in (("tier4_plugin_sha256", EDITOR_SO), ("tier4_ros2_native_sha256", ROS2_SO)):
        assert got[key] == hashlib.sha256((tree / rel).read_bytes()).hexdigest()


# --- staleness: the one refusal this gate is specified to make -------------


def test_a_source_newer_than_the_editor_plugin_is_refused(tree):
    os.utime(tree / "LibCarla/source/carla/ros2/ROS2.cpp", (ART_EPOCH + 60, ART_EPOCH + 60))
    r = run_gate(tree)
    assert r.returncode == 2
    assert "tier4-artifact-stale" in r.stderr
    assert "libUnrealEditor-Carla.so" in r.stderr
    assert "ROS2.cpp" in r.stderr


def test_a_source_newer_than_the_ros2_native_lib_alone_is_refused(tree):
    """The second half of the ROS 2 path gets its own staleness verdict.
    MEASURED on the real tree 2026-07-30: libUnrealEditor-Carla.so DEFINES
    carla::ros2::ROS2::ProcessDataFromLidar and carries an UNDEFINED reference
    to carla::ros2::CarlaLidarPublisher::SetDataEx, which
    libcarla-ros2-native.so defines -- so a fresh editor plugin over a stale
    native lib is a real, reachable half-rebuild."""
    os.utime(tree / ROS2_SO, (SRC_EPOCH - 60, SRC_EPOCH - 60))
    r = run_gate(tree)
    assert r.returncode == 2
    assert "tier4-artifact-stale" in r.stderr
    assert "libcarla-ros2-native.so" in r.stderr


def test_a_source_touched_within_the_artifacts_own_second_still_passes(tree):
    """Sub-second parts are truncated on both sides deliberately: a build reads
    a source and relinks moments later, and that must not read as staleness."""
    os.utime(tree / "LibCarla/CMakeLists.txt", (ART_EPOCH + 0.9, ART_EPOCH + 0.9))
    os.utime(tree / EDITOR_SO, (ART_EPOCH + 0.1, ART_EPOCH + 0.1))
    os.utime(tree / ROS2_SO, (ART_EPOCH + 0.1, ART_EPOCH + 0.1))
    r = run_gate(tree)
    assert r.returncode == 0, r.stderr


def test_a_build_input_outside_libcarla_source_also_counts(tree):
    """CMake/Toolchain.cmake is registered patch 0001's target; a change there
    changes the binary just as much as a .cpp edit does."""
    os.utime(tree / "CMake/Toolchain.cmake", (ART_EPOCH + 60, ART_EPOCH + 60))
    r = run_gate(tree)
    assert r.returncode == 2
    assert "tier4-artifact-stale" in r.stderr
    assert "Toolchain.cmake" in r.stderr


# --- the acknowledgement: a refusal must never be unresolvable -------------
#
# Check 3 compares MTIMES over whole directory trees, and mtime moves without
# content moving: `git apply` of the registered patches
# (benchmarks/patches/tier4-native/README.md:15-17 writes CMake/Toolchain.cmake,
# LibCarla/CMakeLists.txt and LibCarla/source/carla/GlibcCompat.c, all three
# under the scanned roots), a git checkout, a stash pop, an editor save. The one
# remedy the gate first named was a rebuild, which the campaign forbids
# mid-campaign -- so a false refusal had no resolution at all. These tests pin
# both halves of the fix and the thing that must NOT be possible.


def test_an_acknowledged_staleness_warns_records_and_does_not_block(tree):
    make_stale(tree)
    r = run_gate(tree, TIER4_STALE_ACK="re-applied registered patches; content unchanged")
    assert r.returncode == 0, r.stderr
    # Loud: the WARN still names the check, and still names the stale artifact.
    assert "WARN" in r.stderr
    assert "tier4-artifact-stale" in r.stderr
    assert "libUnrealEditor-Carla.so" in r.stderr
    # Recorded: the condition travels in THIS run's own manifest, so no reader of
    # the filed data can meet the number without meeting the acknowledgement.
    got = kv(r.stdout)
    assert got["tier4_stale_ack"] == "applied"
    assert got["tier4_stale_ack_reason"] == "re-applied registered patches; content unchanged"
    assert set(got["tier4_stale_ack_artifacts"].split(",")) == {
        "libUnrealEditor-Carla.so",
        "libcarla-ros2-native.so",
    }


@pytest.mark.parametrize("reason", ["", "   ", "\n\t "])
def test_an_unexplained_acknowledgement_cannot_pass(tree, reason):
    """No reason, no acknowledgement. Set-but-empty is the shape a typo and an
    unset shell lookup both take, and an acknowledgement nobody can read later is
    indistinguishable from having hidden the condition. Refused BY NAME, and
    refused whether or not anything is actually stale, so a misconfigured
    acknowledgement can never be silently ignored."""
    make_stale(tree)
    r = run_gate(tree, TIER4_STALE_ACK=reason)
    assert r.returncode == 2
    assert "tier4-stale-ack-unexplained" in r.stderr
    assert r.stdout == ""


def test_an_unexplained_acknowledgement_is_refused_even_on_a_fresh_tree(tree):
    r = run_gate(tree, TIER4_STALE_ACK="")
    assert r.returncode == 2
    assert "tier4-stale-ack-unexplained" in r.stderr


def test_an_acknowledgement_that_was_not_needed_is_recorded_as_unused(tree):
    """Loud in the other direction too: a leftover export is armed for the next
    run, and `unused` in the manifest distinguishes that from `none`."""
    r = run_gate(tree, TIER4_STALE_ACK="left over from yesterday")
    assert r.returncode == 0, r.stderr
    assert kv(r.stdout)["tier4_stale_ack"] == "unused"
    assert kv(r.stdout)["tier4_stale_ack_reason"] == "left over from yesterday"
    assert "WARN" in r.stderr


def test_a_multiline_reason_stays_a_single_key_value_line(tree):
    """preflight.sh forwards this stdout verbatim and run.sh:481 splits on the
    first `=` PER LINE, so a reason carrying a newline would become a second,
    junk placement key on every affected run."""
    make_stale(tree)
    r = run_gate(tree, TIER4_STALE_ACK="  first line\nsecond\tline  ")
    assert r.returncode == 0, r.stderr
    assert len([line for line in r.stdout.splitlines() if line.startswith("tier4_stale_ack")]) == 3
    assert kv(r.stdout)["tier4_stale_ack_reason"] == "first line second line"


def test_the_source_digest_is_unchanged_by_an_mtime_only_touch(tree):
    """The other half of the fix. The acknowledgement is the operator ASSERTING
    that content did not move; tier4_source_sha256 is what makes the assertion
    checkable against the last run that passed without one."""
    before = kv(run_gate(tree).stdout)["tier4_source_sha256"]
    make_stale(tree)
    after = kv(run_gate(tree, TIER4_STALE_ACK="mtime only").stdout)["tier4_source_sha256"]
    assert after == before


def test_the_source_digest_changes_when_a_scanned_source_changes(tree):
    """...and it is a real content digest, so an acknowledgement cannot paper over
    an edit: the digest moves and the difference is in both manifests."""
    before = kv(run_gate(tree).stdout)["tier4_source_sha256"]
    (tree / "LibCarla/source/carla/ros2/ROS2.cpp").write_text("// actually edited\n")
    _stamp(tree)
    assert kv(run_gate(tree).stdout)["tier4_source_sha256"] != before


def test_the_head_staleness_check_cannot_be_acknowledged(tree):
    """Scoped to check 3 on purpose: check 4 can only fire when HEAD MOVED, which
    is a real content change and not mtime drift."""
    _write(tree, "LibCarla/source/carla/ros2/Newer.cpp", "// newer\n")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "upstream moves on", commit_epoch=ART_EPOCH + 3600)
    _stamp(tree)
    r = run_gate(tree, TIER4_STALE_ACK="please do not block me")
    assert r.returncode == 2
    assert "tier4-artifact-older-than-head" in r.stderr


def test_an_artifact_older_than_head_is_refused(tree):
    """Cell A's own check, kept for parity. Reached by committing on top of the
    built artifacts, which is what a fast-forward onto newer upstream without a
    rebuild looks like."""
    _write(tree, "LibCarla/source/carla/ros2/Newer.cpp", "// newer\n")
    _git(tree, "add", "-A")
    _git(tree, "commit", "-q", "-m", "upstream moves on", commit_epoch=ART_EPOCH + 3600)
    _stamp(tree)
    r = run_gate(tree)
    assert r.returncode == 2
    assert "tier4-artifact-older-than-head" in r.stderr


# --- the other named refusals ----------------------------------------------


@pytest.mark.parametrize("missing", [EDITOR_SO, ROS2_SO])
def test_a_missing_artifact_gets_its_own_named_check(tree, missing):
    """Named apart from staleness on purpose: "never built in this tree" and
    "built, then left behind by a partial rebuild" need different fixes."""
    (tree / missing).unlink()
    r = run_gate(tree)
    assert r.returncode == 2
    assert "tier4-artifact-missing" in r.stderr
    assert missing.rsplit("/", 1)[-1] in r.stderr


def test_a_tree_that_is_not_a_git_worktree_is_refused(tmp_path):
    t = tmp_path / "not-a-repo"
    _write(t, EDITOR_SO, "x\n")
    _write(t, ROS2_SO, "x\n")
    r = run_gate(t)
    assert r.returncode == 2
    assert "tier4-tree" in r.stderr


def test_a_missing_tree_is_refused(tmp_path):
    r = run_gate(tmp_path / "nope")
    assert r.returncode == 2
    assert "tier4-tree" in r.stderr


def test_a_tree_nested_inside_another_repository_is_refused(tmp_path):
    """`git rev-parse --git-dir` WALKS UP, so a $TIER4_TREE that is merely a
    subdirectory of another repository answers with the ENCLOSING repo's git dir
    and every recorded identity would be that repo's. A wrong identity is worse
    than a missing one: nothing downstream can tell that it is wrong."""
    outer = tmp_path / "outer"
    _write(outer, "README.md", "outer repo\n")
    _git(outer, "init", "-q")
    _git(outer, "add", "-A")
    _git(outer, "commit", "-q", "-m", "outer")
    nested = outer / "nested"
    _write(nested, EDITOR_SO, "editor plugin bytes\n")
    _write(nested, ROS2_SO, "ros2 native bytes\n")
    _write(nested, "CMake/Toolchain.cmake", "// tc\n")
    _stamp(nested)
    r = run_gate(nested)
    assert r.returncode == 2
    assert "tier4-tree" in r.stderr
    assert str(outer) in r.stderr


def test_a_tree_with_no_commit_is_refused_by_name(tmp_path):
    """Reached at check 4. A bare `COMMIT_EPOCH="$(git show ... HEAD)"` would abort
    here under `set -e` with git's own message and NO named check, while both
    callers go on to print "named reason above"."""
    t = tmp_path / "no-commits"
    _write(t, EDITOR_SO, "editor plugin bytes\n")
    _write(t, ROS2_SO, "ros2 native bytes\n")
    _write(t, "CMake/Toolchain.cmake", "// tc\n")
    _git(t, "init", "-q")
    _stamp(t)
    r = run_gate(t)
    assert r.returncode == 2
    assert "PREFLIGHT FAIL: tier4-tree" in r.stderr


def test_a_tree_identity_failure_still_names_a_check(tree, tmp_path):
    """Every exit path owes a named check, including the ones nothing raises
    deliberately: both callers print "named reason above" on any non-zero exit, so
    a bare python traceback sends the operator hunting for a line that was never
    printed. Triggered here with a `*.patch` that is a DIRECTORY, which is a
    deterministic IsADirectoryError inside the identity reader."""
    patch_dir = tmp_path / "broken-patches"
    write_patch(patch_dir, "0001-fine.patch", "CMake/Toolchain.cmake")
    (patch_dir / "0002-broken.patch").mkdir()
    r = run_gate(tree, patch_dir=patch_dir)
    assert r.returncode == 2
    assert "PREFLIGHT FAIL: tier4-identity" in r.stderr
    # python's own traceback is kept, ahead of the named line, because only
    # stdout is captured from the block.
    assert "IsADirectoryError" in r.stderr


def test_an_unset_tree_is_refused_before_anything_else():
    """Env-driven like scripts/e2e/verify_editor_artifact.sh:20's
    `CARLA_ROOT=${CARLA_ROOT:?...}`, so a caller that forgets the variable gets
    a refusal and never a check against some default tree."""
    env = {k: v for k, v in os.environ.items() if k != "TIER4_TREE"}
    r = subprocess.run(["bash", str(GATE)], capture_output=True, text=True, env=env)
    assert r.returncode != 0
    assert "TIER4_TREE" in r.stderr


# --- worktree state against the REGISTERED patch set -----------------------


def test_a_clean_worktree_reports_clean(tree):
    assert kv(run_gate(tree).stdout)["tier4_worktree"] == "clean"


def test_the_real_registered_patch_set_is_recognised_as_such(tree):
    """Driven by the REAL benchmarks/patches/tier4-native/*.patch files, so the
    `+++ b/<path>` parser is pinned against the artifacts it will read -- 0002
    creates GlibcCompat.c from /dev/null, so the `---` side cannot be used."""
    (tree / "CMake/Toolchain.cmake").write_text("// patched\n")
    (tree / "LibCarla/CMakeLists.txt").write_text("// patched\n")
    (tree / "PythonAPI/examples/autoware_demo.py").write_text("# patched\n")
    _write(tree, "LibCarla/source/carla/GlibcCompat.c", "// new, untracked\n")
    _stamp(tree)
    r = run_gate(tree, patch_dir=REAL_PATCH_DIR)
    assert r.returncode == 0, r.stderr
    assert kv(r.stdout)["tier4_worktree"] == "registered-patches"


def test_an_unregistered_edit_is_reported_diverged_and_does_NOT_block(tree):
    """Recorded, warned, and NOT refused. The gate is specified to make exactly
    one refusal (staleness); turning a stray local edit into a hard stop would
    add a run-blocking condition nothing pre-registered supports. The value in
    placement is what makes the divergence a finding someone can act on."""
    (tree / "LibCarla/source/carla/ros2/ROS2.cpp").write_text("// local hack\n")
    _stamp(tree)
    r = run_gate(tree, patch_dir=REAL_PATCH_DIR)
    assert r.returncode == 0, r.stderr
    state = kv(r.stdout)["tier4_worktree"]
    assert state.startswith("diverged:+LibCarla/source/carla/ros2/ROS2.cpp")
    assert "WARN" in r.stderr


def test_a_registered_patch_that_is_not_applied_is_reported_diverged(tree):
    (tree / "CMake/Toolchain.cmake").write_text("// patched\n")
    _stamp(tree)
    r = run_gate(tree, patch_dir=REAL_PATCH_DIR)
    assert r.returncode == 0, r.stderr
    state = kv(r.stdout)["tier4_worktree"]
    assert state.startswith("diverged:")
    assert "LibCarla/source/carla/GlibcCompat.c" in state.split(":-", 1)[1]


def test_the_worktree_digest_tracks_the_dirty_path_set(tree):
    before = kv(run_gate(tree).stdout)["tier4_worktree_paths_sha256"]
    (tree / "CMake/Toolchain.cmake").write_text("// patched\n")
    _stamp(tree)
    after = kv(run_gate(tree).stdout)["tier4_worktree_paths_sha256"]
    assert before != after


def test_the_worktree_content_digest_moves_where_the_paths_digest_cannot(tree):
    """tier4_worktree_paths_sha256 hashes only the sorted PATH list, so an edit to
    an ALREADY-dirty file left it unchanged -- including an edit to
    PythonAPI/examples/autoware_demo.py, registered patch 0003, the file that sets
    --lidar-pps and --lidar-rotation-hz. That reproduced, for the sensor
    configuration, the exact "a path is not an identity" gap this gate exists to
    close, which is why the content digest exists beside it."""
    (tree / "PythonAPI/examples/autoware_demo.py").write_text("# --lidar-pps 288000\n")
    _stamp(tree)
    first = kv(run_gate(tree).stdout)
    (tree / "PythonAPI/examples/autoware_demo.py").write_text("# --lidar-pps 1152000\n")
    _stamp(tree)
    second = kv(run_gate(tree).stdout)
    assert first["tier4_worktree_paths_sha256"] == second["tier4_worktree_paths_sha256"]
    assert first["tier4_worktree_content_sha256"] != second["tier4_worktree_content_sha256"]


def test_the_worktree_content_digest_covers_untracked_file_content(tree):
    """Untracked files are absent from `git diff HEAD`, so they are appended by
    content -- otherwise patch 0002's GlibcCompat.c, which is untracked in the real
    tree, would be identity-free."""
    _write(tree, "LibCarla/source/carla/GlibcCompat.c", "// v1\n")
    _stamp(tree)
    first = kv(run_gate(tree).stdout)["tier4_worktree_content_sha256"]
    (tree / "LibCarla/source/carla/GlibcCompat.c").write_text("// v2\n")
    _stamp(tree)
    assert kv(run_gate(tree).stdout)["tier4_worktree_content_sha256"] != first


def test_an_untracked_registered_path_in_a_new_directory_is_not_diverged(tree, tmp_path):
    """`git status --porcelain` defaults to -unormal, which COLLAPSES a wholly
    untracked directory to one `dir/` entry -- so a registered patch creating files
    in a NEW directory would compare `dir/` against `+++ b/dir/file` and report a
    spurious `diverged:` on every run. -uall is what makes this pass. The reason
    -unormal happened to work is narrow: patch 0002's GlibcCompat.c lands in an
    already-tracked directory."""
    patch_dir = tmp_path / "patches"
    write_patch(patch_dir, "0001-new-dir.patch", "LibCarla/source/carla/newdir/Shim.c")
    _write(tree, "LibCarla/source/carla/newdir/Shim.c", "// new, untracked, new dir\n")
    _stamp(tree)
    # The collapsing this guards against, asserted rather than assumed.
    collapsed = subprocess.run(
        ["git", "-C", str(tree), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert collapsed.strip() == "?? LibCarla/source/carla/newdir/"
    r = run_gate(tree, patch_dir=patch_dir)
    assert r.returncode == 0, r.stderr
    assert kv(r.stdout)["tier4_worktree"] == "registered-patches"


def test_a_staged_rename_is_reported_by_its_new_path(tree, tmp_path):
    """The `R  <old> -> <new>` branch of the porcelain parser. The NEW path is the
    one that describes the tree as it stands, so that is what has to land in
    placement -- reporting `old -> new` verbatim would make the whole entry
    unmatchable against any registered patch's `+++ b/` path."""
    patch_dir = tmp_path / "patches"
    write_patch(patch_dir, "0001-noop.patch", "LibCarla/CMakeLists.txt")
    _git(tree, "mv", "CMake/Toolchain.cmake", "CMake/Toolchain2.cmake")
    _stamp(tree)
    porcelain = subprocess.run(
        ["git", "-C", str(tree), "status", "--porcelain", "-uall"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert porcelain.strip().startswith("R  CMake/Toolchain.cmake -> CMake/Toolchain2.cmake")
    r = run_gate(tree, patch_dir=patch_dir)
    assert r.returncode == 0, r.stderr
    state = kv(r.stdout)["tier4_worktree"]
    extra = state.split(":+", 1)[1].split(":-", 1)[0].split(",")
    assert extra == ["CMake/Toolchain2.cmake"]
    assert "->" not in state


# --- wiring: a gate nothing calls is a comment ------------------------------


def test_preflight_runs_the_gate_for_the_tier4_approach_and_forwards_its_keys():
    pf = (REPO / "benchmarks" / "scripts" / "preflight.sh").read_text()
    assert 'if [ "$APPROACH" = "tier4-native" ]; then' in pf
    assert 'TIER4_TREE="$CARLA_TREE" bash "$HERE/verify_tier4_artifact.sh"' in pf
    # Forwarded into the KEY=VALUE report, which run.sh folds into placement.
    assert 'echo "$TIER4_KV"' in pf


def test_the_tier4_launcher_runs_the_gate_before_it_boots_the_editor():
    """cells/tier4-native.sh is a documented direct entry point, so it must not
    depend on preflight having run. The call has to sit in the block that runs
    for BOTH `plan` and `up`, i.e. above the `if [ "$MODE" = "plan" ]` exit."""
    launcher = (REPO / "benchmarks" / "cells" / "tier4-native.sh").read_text()
    call = 'TIER4_TREE="$BENCH_CARLA_TREE" bash "$TIER4_GATE"'
    assert call in launcher
    assert launcher.index(call) < launcher.index('if [ "$MODE" = "plan" ]')


def test_every_tier4_family_cell_routes_through_the_gated_launcher():
    """B, B-hf, B45 and D are the family (cells/tier4-native.sh:2). The gate is
    per-APPROACH, so this is what makes it per-cell."""
    import yaml

    cells = yaml.safe_load((REPO / "benchmarks" / "config" / "cells.yaml").read_text())
    tier4 = {c["id"] for c in cells["cells"] if c.get("approach") == "tier4-native"}
    assert tier4 == {"B", "B-hf", "B45", "D"}
