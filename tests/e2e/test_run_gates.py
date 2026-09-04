"""Regression guard for ``run_gates.sh``'s verdict harvesting.

The defect this pins: ``run_gates.sh`` used to harvest verdicts by the ``"Gn "``
prefix alone, so ``gate_g2_closed_loop.sh``'s pre-measurement progress echo was
collected as if it were G2's verdict. That line carries no ``FAIL``, so a G2 that
printed it and *then* died -- CARLA absent on ``--rpc-port``, no CARLA egg, the ego
never spawning, a malformed ``--goal`` -- yielded exit 0 with G2 having measured
nothing. A false pass burns a whole live cell, and the defect survived a round of
dedicated review because the throwaway check used a G2 stub that printed only a
verdict or nothing at all.

So the load-bearing case here is ``G2_ECHO_THEN_DIE``: progress line first, death
second. The other two cases hold the ends of the range honest -- an all-PASS run
must still exit 0, and a genuine ``-> FAIL`` verdict must still exit non-zero.

These drive a **verbatim copy** of the real ``scripts/e2e/run_gates.sh`` (not an
edited one) with stub gate scripts beside it, so the harvesting logic under test is
the shipped logic. ``SETTLE_S=0`` skips the 20 s settle wait; nothing else is
overridden, and no simulator, container or network is involved.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RUN_GATES = REPO / "scripts" / "e2e" / "run_gates.sh"

GOAL = "-1.16,28.37,0.16"
GOAL_ECHO = f"echo \"goal: CARLA '{GOAL}' -> map (-1.160, -28.370)\""

G1_PASS = 'echo "G1 NDT: ndt_samples=600 gt_samples=600 max_err=0.213 m threshold=1.0 m -> PASS"'
# A real G3 scores LiDAR and control separately, so it emits two verdict lines.
G3_PASS = (
    'echo "G3 LiDAR: measured=9.99 Hz target=10.0+-1.0 Hz -> PASS"\n'
    'echo "G3 control: measured=19.96 Hz target=20.0+-5.0 Hz -> PASS"'
)
G2_PASS = f'{GOAL_ECHO}\necho "G2 route: samples=3000 closest_approach=0.412 m tol=1.0 m -> PASS"'
G2_FAIL = (
    f'{GOAL_ECHO}\necho "G2 route: samples=3000 closest_approach=7.902 m tol=1.0 m -> FAIL"\nexit 1'
)
G2_ECHO_THEN_DIE = f"{GOAL_ECHO}\necho \"ModuleNotFoundError: No module named 'carla'\" >&2\nexit 1"


def _run_gates(tmp_path: Path, g2_body: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the real run_gates.sh over stub gates; G1/G3 always pass, G2 varies."""
    stack = tmp_path / "e2e"
    stack.mkdir()
    shutil.copy(RUN_GATES, stack / "run_gates.sh")
    for name, body in (
        ("gate_g1_localization.sh", G1_PASS),
        ("gate_g2_closed_loop.sh", g2_body),
        ("gate_g3_performance.sh", G3_PASS),
    ):
        script = stack / name
        script.write_text(f"#!/usr/bin/env bash\n{body}\n")
        script.chmod(0o755)
    # run_gates.sh preflights the container record before launching any gate.
    (tmp_path / "carla_autoware.containers").write_text("stub-autoware-container\n")
    out = tmp_path / "gates"
    proc = subprocess.run(
        [
            "bash",
            str(stack / "run_gates.sh"),
            "--log-dir",
            str(tmp_path),
            "--goal",
            GOAL,
            "--out",
            str(out),
        ],
        env={**os.environ, "SETTLE_S": "0"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc, out


def _verdicts(out: Path) -> list[str]:
    return (out / "gates.txt").read_text().splitlines()


def test_g2_that_prints_progress_then_dies_is_not_a_pass(tmp_path):
    """The Critical: a G2 progress line must never be harvested as G2's verdict."""
    proc, out = _run_gates(tmp_path, G2_ECHO_THEN_DIE)
    assert proc.returncode != 0, f"crashed G2 read as a pass\n{proc.stdout}{proc.stderr}"
    assert "G2 produced no verdict" in proc.stderr
    verdicts = _verdicts(out)
    assert not [ln for ln in verdicts if ln.startswith("G2 ")]
    # The gates that did score are still reported, so the operator sees what ran.
    assert [ln.startswith("G1 ") for ln in verdicts].count(True) == 1
    assert [ln.startswith("G3 ") for ln in verdicts].count(True) == 2


def test_all_pass_exits_zero_with_every_gate_represented(tmp_path):
    proc, out = _run_gates(tmp_path, G2_PASS)
    assert proc.returncode == 0, f"{proc.stdout}{proc.stderr}"
    verdicts = _verdicts(out)
    assert [ln.split(":")[0] for ln in verdicts] == ["G1 NDT", "G2 route", "G3 LiDAR", "G3 control"]
    assert all(ln.endswith("-> PASS") for ln in verdicts)


def test_genuine_g2_fail_verdict_exits_nonzero(tmp_path):
    proc, out = _run_gates(tmp_path, G2_FAIL)
    assert proc.returncode != 0, f"{proc.stdout}{proc.stderr}"
    assert "produced no verdict" not in proc.stderr  # G2 *did* score; it scored FAIL
    assert [ln for ln in _verdicts(out) if ln.startswith("G2 ") and ln.endswith("-> FAIL")]
