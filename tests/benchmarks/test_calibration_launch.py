"""Behavioural pins for benchmarks/cells/calibration.sh's CAL-seam `plan`
branch (Task 8, P4 transport-sweep plan, fix round 1).

This campaign has a binding rule that a substring/text-scan assertion over a
script's SOURCE is not a pin for a safety property (see
tests/benchmarks/test_teardown.py's and
tests/benchmarks/test_verify_tier4_artifact.py's own module docstrings for
the prior violations that established it). The first cut of Task 8's CAL-seam
coverage broke that rule: three of its six text-scan assertions
(`"WITH_AUTOWARE=0" in seam_branch`, `"run_e2e.sh" in seam_branch`, and the
`CARLA_BENCH_*_CLOUD=1` pair against a slice wide enough to include an
explanatory comment) passed on COMMENT TEXT alone and would keep passing with
the real assignments deleted.

What this file does instead: run the REAL `calibration.sh plan` as a
subprocess and assert on the REAL generated `launch.env`. This is possible
without a live CARLA at all -- `plan` mode's whole job is to validate
preflight conditions and write `launch.env`; it `exit 0`s before ever
touching docker, `run_e2e.sh`, or a real CARLA process (see
`benchmarks/cells/calibration.sh`'s own `if [ "$MODE" = "plan" ]; then exit
0; fi`, immediately after the `cat >"$BENCH_LAUNCH_ENV"` heredoc). Every
preflight the CAL-seam branch runs before that point is satisfiable with
synthetic stand-ins: a placeholder `.so` file, an empty directory standing in
for the extension CARLA fork tree, a real (synthetic) route YAML, and a
trivial always-succeeds script standing in for the GT Python interpreter
(`plan` mode only checks it is executable and that `-c "import carla"`
exits 0 -- it never actually drives a CARLA client in this mode).

WHAT IS FAITHFUL about the stand-ins below, and what is not:

* Faithful -- the REAL `calibration.sh` runs as a REAL subprocess, so its
  actual preflight checks (RPC port 2000, `.so` presence, CARLA tree
  presence, route file presence, GT interpreter executability) and its
  actual `launch.env`-writing logic both execute for real. Every field
  asserted below comes from parsing the file the script itself wrote, not
  from a mock.
* Faithful -- the route YAML parsing (`SPAWN_ARGS`) is exercised for real
  too: the script's own embedded `python3` snippet reads the real file this
  test writes and the value asserted on is what that snippet actually
  printed.
* NOT faithful -- nothing here boots CARLA, Autoware, or the UnrealEditor.
  These tests pin the PLAN-TIME CONTRACT (what `launch.env` says CAL-seam
  will do); they do not show that a live run of it behaves as planned. Task
  10 owns the first live collection. Two assignments that live inside the
  `up`-mode subshell (`$CARLA_BENCH_SEAM_CLOUD=1` /
  `$CARLA_BENCH_INCORE_CLOUD=1` reaching the `run_e2e.sh` invocation, plus
  `WITH_AUTOWARE=0` on that same command line) are therefore NOT reachable
  from `plan` mode and are not asserted here -- they stay a narrowly-scoped,
  explicitly-disclosed text pin in
  tests/benchmarks/test_cell_info.py::test_cal_seam_branch_exports_both_bench_env_vars_into_the_run_e2e_invocation.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CALIBRATION_SH = REPO / "benchmarks" / "cells" / "calibration.sh"

# A trivial stand-in for the GT Python interpreter. `plan` mode only checks
# `[ -x "$GT_PYTHON" ]` and that `"$GT_PYTHON" -c "import carla"` exits 0 --
# it never actually imports carla or talks to a CARLA server in this mode
# (that only happens in the up-mode readiness-poll loop, which `plan` never
# reaches), so a script that unconditionally exits 0 is a faithful stand-in
# for exactly what this mode exercises.
GT_PYTHON_STUB = "#!/usr/bin/env bash\nexit 0\n"


def _parse_launch_env(path: Path) -> dict[str, str]:
    """`launch.env` is a flat `KEY="value"` bash source file (see
    calibration.sh's own heredoc). Parsed with a plain split rather than
    sourcing it, so this test does not itself need bash to read the file --
    only to have run calibration.sh, which already required it."""
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition("=")
        out[key] = rest.strip('"')
    return out


@pytest.fixture
def cal_seam_env(tmp_path):
    """A minimal but real set of CAL-seam `plan`-mode preflight inputs, all
    synthetic and self-contained under tmp_path -- no CARLA, no docker, no
    touch of the real repo tree."""
    bench_repo = tmp_path / "bench_repo"
    ext_so = bench_repo / "extension" / "build" / "libcarla-autoware-extension.so"
    ext_so.parent.mkdir(parents=True)
    ext_so.write_bytes(b"placeholder .so -- plan mode only checks presence")

    carla_tree = tmp_path / "carla_tree"
    carla_tree.mkdir()

    route_file = tmp_path / "route.yaml"
    route_file.write_text(
        "map: Town10HD_Opt\n"
        "spawn_index: null\n"
        "spawn_pose: { x: 55.33, y: 141.161, z: 0.5, yaw_deg: 0.32 }\n"
    )

    gt_python = tmp_path / "gt_python_stub.sh"
    gt_python.write_text(GT_PYTHON_STUB)
    gt_python.chmod(gt_python.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    run_dir = tmp_path / "run_dir"
    launch_env = tmp_path / "launch.env"

    return {
        **os.environ,
        "BENCH_REPO": str(bench_repo),
        "BENCH_CELL": "CAL-seam",
        "BENCH_ARM": "static",
        "BENCH_RUN_DIR": str(run_dir),
        "BENCH_LAUNCH_ENV": str(launch_env),
        "BENCH_RMW": "rmw_cyclonedds_cpp",
        "BENCH_SHM": "none",
        "BENCH_MAP": "Town10HD_Opt",
        "BENCH_RPC_PORT": "2000",
        "BENCH_ROUTE_FILE": str(route_file),
        "BENCH_CARLA_TREE": str(carla_tree),
        "BENCH_GT_PYTHON": str(gt_python),
    }


def run_plan(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(CALIBRATION_SH), "plan"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def test_cal_seam_plan_writes_the_expected_launch_env(cal_seam_env):
    """The real script, run for real, against real (synthetic) preflight
    inputs: every field a live CAL-seam launch depends on for teardown
    routing, arming, ground-truth collection and injection is asserted on
    the actual file the script wrote -- not on its source text."""
    result = run_plan(cal_seam_env)
    assert result.returncode == 0, (
        f"plan mode should succeed with all preflights satisfied:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )

    launch_env_path = Path(cal_seam_env["BENCH_LAUNCH_ENV"])
    assert launch_env_path.is_file(), "plan mode must write BENCH_LAUNCH_ENV"
    fields = _parse_launch_env(launch_env_path)

    assert fields["LAUNCH_CELL"] == "CAL-seam"
    # teardown.sh's case-select key: CAL-seam reuses the "extension" family's
    # graceful CARLA_PID_FILE teardown, NOT cells.yaml's own
    # `approach: calibration` (that stays the authoritative record
    # elsewhere -- see the manifest writer and preflight.sh).
    assert fields["APPROACH"] == "extension"
    assert fields["RUN_MODE"] == "editor-game"
    assert fields["LAUNCH_MAP"] == "Town10HD_Opt"
    assert fields["LAUNCH_ARM"] == "static"
    assert fields["CARLA_TREE"] == cal_seam_env["BENCH_CARLA_TREE"]
    assert fields["CARLA_RPC_PORT"] == "2000"
    # No Autoware container for this cell.
    assert fields["AW_CONTAINER"] == ""
    assert fields["AW_EXEC"] == ""
    assert fields["AW_SETUP"] == ""
    assert fields["AW_COMPOSE"] == ""
    # CAL-seam is a transport/serialization calibration, not a drive: no
    # ground truth, nothing armed, nothing injected.
    assert fields["GT_ENABLED"] == "0"
    assert fields["GT_CMD"] == ""
    assert fields["GT_OUT_DIR"] == ""
    assert fields["GT_COUNT_LIDAR"] == "0"
    assert fields["INJECTOR_ENABLED"] == "0"
    assert fields["ARM_ENABLED"] == "0"
    assert fields["EXTRA_CONTAINERS"] == ""
    # Derived from the route file's spawn_pose (x, y, z, 0, 0, yaw_deg) --
    # the real embedded python3/yaml snippet parsed the real synthetic route
    # file this test wrote.
    assert fields["SPAWN_ARGS"] == "--initial-pose 55.33 141.161 0.5 0 0 0.32"


def test_cal_seam_plan_derives_spawn_index_when_the_route_uses_one(cal_seam_env, tmp_path):
    """The route-parsing branch this cell shares with cell A's own launcher
    has two shapes (`spawn_index` vs `spawn_pose`) -- covering only the pose
    shape above would leave the index shape's real behaviour unpinned."""
    route_file = tmp_path / "route_index.yaml"
    route_file.write_text("map: Town10HD_Opt\nspawn_index: 3\nspawn_pose: null\n")
    cal_seam_env["BENCH_ROUTE_FILE"] = str(route_file)

    result = run_plan(cal_seam_env)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"

    fields = _parse_launch_env(Path(cal_seam_env["BENCH_LAUNCH_ENV"]))
    assert fields["SPAWN_ARGS"] == "--spawn-index 3"


def test_cal_seam_plan_refuses_a_non_2000_rpc_port(cal_seam_env):
    """CAL-seam boots through scripts/e2e/run_e2e.sh, which hardcodes RPC
    port 2000 in both the editor invocation and its own port_bound() probe
    -- the same disagreement cells/extension.sh refuses on. A real refusal,
    not a comment describing one: this must actually exit non-zero and must
    not write a launch.env a caller could mistake for a validated plan."""
    cal_seam_env["BENCH_RPC_PORT"] = "3000"
    result = run_plan(cal_seam_env)
    assert result.returncode != 0
    assert "RPC port 2000" in result.stderr
    assert not Path(cal_seam_env["BENCH_LAUNCH_ENV"]).exists()


def test_cal_seam_plan_refuses_a_missing_extension_so(cal_seam_env):
    """A stale/never-built extension .so must not silently plan a launch
    that would fail much later, deeper into an editor boot."""
    so_path = Path(cal_seam_env["BENCH_REPO"]) / "extension" / "build" / "libcarla-autoware-extension.so"
    so_path.unlink()
    result = run_plan(cal_seam_env)
    assert result.returncode != 0
    assert "extension .so missing" in result.stderr
    assert not Path(cal_seam_env["BENCH_LAUNCH_ENV"]).exists()


@pytest.mark.skipif(
    os.geteuid() == 0,
    reason="root ignores the 0o644 permissions this test uses to make -x fail",
)
def test_cal_seam_plan_refuses_a_non_executable_gt_python(cal_seam_env):
    """The GT client doubles as this cell's bring-up readiness probe (see
    calibration.sh's own comment on GT_PYTHON) -- an interpreter that is not
    even executable must refuse in `plan`, not surface only once `up` is
    already mid-boot."""
    gt_python = Path(cal_seam_env["BENCH_GT_PYTHON"])
    gt_python.chmod(0o644)
    result = run_plan(cal_seam_env)
    assert result.returncode != 0
    assert "GT interpreter not executable" in result.stderr
    assert not Path(cal_seam_env["BENCH_LAUNCH_ENV"]).exists()
