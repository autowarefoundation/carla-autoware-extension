"""Behavioural pins for duel.sh's inter-run pacing (Task 18a, D1-D4).

Task 18 filed pair 1 of the primary duel (results/A/run-003,
results/B/run-013), then hit a hard blocker on pair 2: duel.sh chained
run.sh invocations with zero cooldown, a completed run leaves the host far
above preflight.sh's loadavg gate (MAX_LOADAVG=8, exclusions.md criterion 6),
so the very next run was refused at preflight and two consecutive refusals
tripped duel.sh's own abort. duel.sh gained a floor-then-bounded-top-up wait
between chained runs to fix this -- see the pacing block at the top of
benchmarks/scripts/duel.sh for the full derivation, and
benchmarks/results/PROVENANCE.md section 3 for the dated disclosure.

This campaign has a binding rule that a substring/text-scan assertion is NOT
a pin (six prior violations on record). Every test below therefore runs the
REAL benchmarks/scripts/duel.sh as a subprocess -- copied byte-for-byte into
a throwaway fake repo layout, never edited -- against a stand-in `run.sh`
that stands in exactly where duel.sh's own contract with run.sh lives
(`bash "$BENCH/run.sh" "$cell" --duel ...`, one exit code decides success or
failure). Every assertion reads a REAL effect the real code produced: a real
wall-clock gap measured between two real subprocess invocations, a real exit
code, a real line the real script appended to a real file -- not a string
that happens to appear in duel.sh's source.

WHAT IS FAITHFUL, and what is not, about the `run.sh` stand-in below:

* Faithful -- duel.sh resolves `$BENCH` from its OWN location
  (`$(dirname duel.sh)/..`) and invokes `bash "$BENCH/run.sh"` by that
  resolved path, never via PATH lookup. Placing the copied duel.sh at
  `<fake-repo>/benchmarks/scripts/duel.sh` and the stand-in at
  `<fake-repo>/benchmarks/run.sh` means duel.sh's OWN path resolution finds
  the stand-in for real, exactly the way it finds the real run.sh in
  production -- nothing here monkeypatches or intercepts that call.
* Faithful -- pace_between_runs' own /proc/loadavg read is redirected via
  `DUEL_LOADAVG_SRC`, the SAME "overridable by env var for tests only,
  default unchanged" pattern scripts/e2e/stop_launch_tree.sh's signal ladder
  uses (STOP_INT_WAIT_S and siblings). The real `awk '{print $1}'` parse
  runs against a fake file instead of the real host's /proc/loadavg; nothing
  about the parse or the comparison logic is stubbed.
* NOT faithful -- the stand-in `run.sh` does no launching, no preflight, no
  manifest write; it only timestamps its own invocation and exits. These
  tests pin the PACING (the wait's real duration, its ceiling behaviour, the
  record it leaves), not run.sh's own preflight refusing a hot host -- that
  is preflight.sh's own concern and is untouched by this task.

A fourth pin (`test_check_args_skips_pacing_entirely`) was added after this
task's own verification pass caught a real regression: pacing between
`--check-args` invocations broke the pre-existing, previously-instant,
side-effect-free `--check-args` contract that
tests/benchmarks/test_duel_verdict.py depends on. It is not one of the
four pacing properties in duel.sh's own design-rationale comment, but it
is pinned here for the same reason those four are: it is a real behaviour
this change must keep, verified against the real code path, not a
text-scan.

A fifth pin (`test_two_consecutive_failures_still_pace_and_abort_with_real_
exit_code`) was added in fix round 1 (finding F6): the pre-existing
test_duel_verdict.py exit-status tests all pass --check-args, so once that
mode skips pacing (the fourth pin above), duel.sh's own 2-consecutive-
failure abort was left with no test exercising it while pacing is active.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DUEL = REPO / "benchmarks" / "scripts" / "duel.sh"

# Logs its own invocation time (wall clock, sub-second) and argv, then exits
# 0 -- the stand-in for `bash "$BENCH/run.sh" "$cell" --duel ...`. Every test
# below cares only about WHEN duel.sh invoked this, never what it did.
FAKE_RUN_SH = """#!/usr/bin/env bash
set -u
: "${FAKE_RUN_LOG:?FAKE_RUN_LOG not set}"
printf '%s %s\\n' "$(date +%s.%N)" "$*" >>"$FAKE_RUN_LOG"
exit "${FAKE_RUN_EXIT:-0}"
"""


@pytest.fixture
def fake_repo(tmp_path):
    """<tmp_path>/benchmarks/scripts/duel.sh is a byte-identical copy of the
    REAL duel.sh (so a change to the real file is what these tests run, not
    this fixture's memory of it); <tmp_path>/benchmarks/run.sh is the
    stand-in above, at the exact path duel.sh's own $BENCH resolution will
    find. Returns <tmp_path> (the fake repo root)."""
    scripts_dir = tmp_path / "benchmarks" / "scripts"
    scripts_dir.mkdir(parents=True)
    duel_copy = scripts_dir / "duel.sh"
    duel_copy.write_bytes(DUEL.read_bytes())
    duel_copy.chmod(duel_copy.stat().st_mode | stat.S_IEXEC)

    fake_run = tmp_path / "benchmarks" / "run.sh"
    fake_run.write_text(FAKE_RUN_SH)
    fake_run.chmod(fake_run.stat().st_mode | stat.S_IEXEC)

    return tmp_path


def _parse_run_log(path: Path) -> list[float]:
    """Wall-clock timestamp of each fake run.sh invocation, in call order."""
    if not path.exists():
        return []
    times = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        ts_str, _, _ = line.partition(" ")
        times.append(float(ts_str))
    return times


def _run_duel(
    tmp_path: Path,
    fake_repo: Path,
    extra_args: tuple[str, ...] = (),
    proc_timeout: float = 30,
    **pace_env,
) -> subprocess.CompletedProcess:
    duel = fake_repo / "benchmarks" / "scripts" / "duel.sh"
    env = {**os.environ, **pace_env}
    return subprocess.run(
        ["bash", str(duel), "cellA", "cellB", "--arm", "static", "--pairs", "1", *extra_args],
        capture_output=True,
        text=True,
        env=env,
        timeout=proc_timeout,
        check=False,
    )


# --- D4 pin 1: the floor genuinely elapses between two chained runs -------


def test_floor_actually_elapses_between_chained_runs(tmp_path, fake_repo):
    """The real-code-path pin for D1's floor: with the ceiling at 0 and a
    fake loadavg already under the target (so the top-up loop never runs),
    the ONLY source of delay between the two chained run.sh invocations is
    the real `sleep "$PACE_FLOOR_S"` call. Neutralising the pacing (deleting
    that sleep, or skipping pace_between_runs entirely) collapses the gap to
    sub-second process-spawn overhead, which the lower bound below catches;
    a text-scan for the string "sleep" in duel.sh's source would not."""
    loadavg_file = tmp_path / "loadavg"
    loadavg_file.write_text("1.0 1.0 1.0 1/200 12345\n")
    run_log = tmp_path / "fake-run.log"

    invoked_at = time.time()
    result = _run_duel(
        tmp_path,
        fake_repo,
        FAKE_RUN_LOG=str(run_log),
        DUEL_PACE_LOG=str(tmp_path / "pacing.log"),
        DUEL_LOADAVG_SRC=str(loadavg_file),
        DUEL_PACE_FLOOR_S="2",
        DUEL_PACE_CEILING_S="0",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )
    assert result.returncode == 0, result.stderr

    times = _parse_run_log(run_log)
    assert len(times) == 2, f"expected 2 run.sh invocations, got {times}"

    # D1's own-call decision: no floor before the FIRST run of the whole
    # invocation. A regression that pends it before every run (including
    # run 1) would show up here as a ~2s delay before the first invocation.
    assert times[0] - invoked_at < 1.5, "a floor was applied before the first run"

    # The floor genuinely elapses between run 1 and run 2.
    gap = times[1] - times[0]
    assert gap >= 1.9, f"floor did not elapse for real (gap={gap:.3f}s, want >= ~2s)"
    assert gap < 6.0, f"gap far exceeds the 2s floor + 0s ceiling (gap={gap:.3f}s)"


# --- D4 pin 2: the ceiling proceeds rather than refusing; exit status -----
# --- unaffected ------------------------------------------------------------


def test_ceiling_reached_proceeds_and_exit_status_unaffected(tmp_path, fake_repo):
    """The real-code-path pin for D1's ceiling: with a fake loadavg source
    that reports a constant, always-hot reading, the top-up poll can NEVER
    see loadavg drop under the target -- the only way the second run.sh
    invocation ever fires is the ceiling's own break, not the loadavg-cleared
    path. If pacing were neutralised into an unconditional/unbounded poll
    instead, this test would hang until its own subprocess timeout rather
    than complete inside the asserted bound below. If it were neutralised
    into a REFUSAL (aborting rather than proceeding once the ceiling is
    reached -- exactly the failure mode this task must never introduce, per
    six recorded precedents of a correctness check blocking a legitimate
    measurement), duel.sh's own exit code would flip non-zero, which the
    exit-code assertion below catches."""
    loadavg_file = tmp_path / "loadavg"
    loadavg_file.write_text("999.0 999.0 999.0 1/999 99999\n")
    run_log = tmp_path / "fake-run.log"

    result = _run_duel(
        tmp_path,
        fake_repo,
        FAKE_RUN_LOG=str(run_log),
        DUEL_PACE_LOG=str(tmp_path / "pacing.log"),
        DUEL_LOADAVG_SRC=str(loadavg_file),
        DUEL_PACE_FLOOR_S="1",
        DUEL_PACE_CEILING_S="2",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )

    # The exit-status contract duel.sh already has (a fully successful duel
    # exits 0) must survive a ceiling hit: both fake runs succeed (exit 0),
    # so the duel must still report full success, not a refusal.
    assert result.returncode == 0, result.stderr
    assert "duel complete" in result.stdout

    times = _parse_run_log(run_log)
    assert len(times) == 2, f"expected 2 run.sh invocations, got {times}"
    gap = times[1] - times[0]
    # Bounded by floor (1s) + ceiling (2s), with slack for poll granularity
    # and process overhead -- NOT hanging, and not merely "eventually
    # proceeds" after some unrelated long delay.
    assert 2.5 <= gap <= 8.0, f"gap not bounded by floor+ceiling (gap={gap:.3f}s)"
    # Corroborating, not load-bearing on its own (see module docstring): the
    # operator-facing message the real ceiling-break branch prints.
    assert "ceiling" in result.stdout and "reached" in result.stdout


# --- D4 pin 3: the recorded wait is actually emitted -----------------------


def test_recorded_wait_is_emitted(tmp_path, fake_repo):
    """The real-code-path pin for D1 property 4: the actual wait for a paced
    run lands in the duel-level pacing log this task added, carrying the
    REAL figures the real run just measured -- read off the file
    pace_between_runs itself appended to, not a hardcoded expectation."""
    loadavg_file = tmp_path / "loadavg"
    loadavg_file.write_text("1.0 1.0 1.0 1/200 12345\n")
    pace_log = tmp_path / "pacing.log"

    result = _run_duel(
        tmp_path,
        fake_repo,
        FAKE_RUN_LOG=str(tmp_path / "fake-run.log"),
        DUEL_PACE_LOG=str(pace_log),
        DUEL_LOADAVG_SRC=str(loadavg_file),
        DUEL_PACE_FLOOR_S="2",
        DUEL_PACE_CEILING_S="0",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )
    assert result.returncode == 0, result.stderr

    assert pace_log.exists(), "no pacing log was written at all"
    lines = [ln for ln in pace_log.read_text().splitlines() if ln.strip()]
    # --pairs 1 makes exactly one chained gap (run 1 -> run 2); the first
    # run of the whole invocation is never paced (D1), so exactly one line.
    assert len(lines) == 1, lines
    fields = dict(kv.split("=", 1) for kv in lines[0].split())

    # before_cell/before_pair (F5) name the run this wait PRECEDES, not the
    # one that just finished -- pair 1's B-then-A order (see the counter-
    # balancing loop) means the paced wait precedes cellB.
    assert fields["before_cell"] == "cellB"
    assert fields["before_pair"] == "1"
    assert fields["floor_s"] == "2"
    assert fields["target"] == "6"
    assert fields["ceiling_s"] == "0"
    # topup_s is real elapsed wall time, not scripted -- allow the 0/1s
    # rounding a SECONDS-granularity clock can introduce right at a
    # whole-second boundary, rather than asserting an exact literal.
    topup = int(fields["topup_s"])
    assert topup in (0, 1), fields
    assert int(fields["total_wait_s"]) == 2 + topup
    assert float(fields["loadavg_end"]) < 6


# --- D4 pin 4 (found during this task's own verification, not in the -----
# --- original brief): --check-args must skip pacing entirely -------------


def test_check_args_skips_pacing_entirely(tmp_path, fake_repo):
    """Found by running the pre-existing, real
    tests/benchmarks/test_duel_verdict.py::
    test_duel_sh_really_produces_duel_admissible_invocations_end_to_end
    after adding the pacing above: that test chains TWO real `duel.sh` ->
    `run.sh --check-args` invocations, and `--check-args` exits run.sh
    before preflight ever runs (see run.sh's own --check-args block and
    that test's block comment: "nothing under benchmarks/results/ is
    written"). Pacing between --check-args runs has no gate to help clear
    and silently broke that documented, previously-instant, side-effect-
    free contract -- turning it into a 120s-floor call that ALSO appended
    to the real benchmarks/results/duel-pacing.log on every test run. This
    pins the fix: pacing must be skipped entirely whenever --check-args is
    among the passthrough args, not merely bounded or made faster.

    floor is set enormous (30s) and the subprocess timeout tight (8s) on
    purpose: if the --check-args skip is neutralised, this test does not
    merely run slower, it blows the subprocess timeout and fails with
    TimeoutExpired -- a real, not textual, signal."""
    loadavg_file = tmp_path / "loadavg"
    loadavg_file.write_text("1.0 1.0 1.0 1/200 12345\n")
    run_log = tmp_path / "fake-run.log"
    pace_log = tmp_path / "pacing.log"

    result = _run_duel(
        tmp_path,
        fake_repo,
        extra_args=("--check-args",),
        proc_timeout=8,
        FAKE_RUN_LOG=str(run_log),
        DUEL_PACE_LOG=str(pace_log),
        DUEL_LOADAVG_SRC=str(loadavg_file),
        DUEL_PACE_FLOOR_S="30",
        DUEL_PACE_CEILING_S="0",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )
    assert result.returncode == 0, result.stderr

    times = _parse_run_log(run_log)
    assert len(times) == 2, f"expected 2 run.sh invocations, got {times}"
    gap = times[1] - times[0]
    assert gap < 2.0, f"--check-args did not skip pacing (gap={gap:.3f}s)"
    assert not pace_log.exists(), "--check-args run must write no pacing record"


# --- fix-round F6: the 2-consecutive-failure abort path is unpinned with ---
# --- pacing active, and it must still exit and pace correctly -------------


def test_two_consecutive_failures_still_pace_and_abort_with_real_exit_code(tmp_path, fake_repo):
    """F6 (fix round 1): the pre-existing test_duel_verdict.py exit-status
    tests all pass --check-args, so after the check-args fix above they no
    longer traverse pacing at all -- duel.sh's own 2-consecutive-failure
    abort (MAX_CONSECUTIVE_FAILURES, the mechanism that stopped Task 18's own
    duel) had no test exercising it WITH pacing active. --pairs 1 makes
    exactly two chained runs (cellA then cellB, pair 1 is odd); FAKE_RUN_EXIT
    fails both, so the second failure trips the abort. This asserts the real
    exit code (2, from duel.sh's own `die`) AND that pacing still genuinely
    ran before the second, ultimately-failing, run -- neutralising either the
    abort or the pacing-still-runs property changes a measured effect (exit
    code or wall-clock gap), not a substring."""
    loadavg_file = tmp_path / "loadavg"
    loadavg_file.write_text("1.0 1.0 1.0 1/200 12345\n")
    run_log = tmp_path / "fake-run.log"
    pace_log = tmp_path / "pacing.log"

    result = _run_duel(
        tmp_path,
        fake_repo,
        FAKE_RUN_LOG=str(run_log),
        FAKE_RUN_EXIT="1",
        DUEL_PACE_LOG=str(pace_log),
        DUEL_LOADAVG_SRC=str(loadavg_file),
        DUEL_PACE_FLOOR_S="2",
        DUEL_PACE_CEILING_S="0",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )

    # duel.sh's own die() exits 2; a refusal-shaped or hung pacing defect
    # would not reproduce this exact code.
    assert result.returncode == 2, result.stderr
    assert "2 consecutive failed runs; stopping the duel" in result.stderr

    # Both fake runs still fired (the abort happens AFTER the second run,
    # not instead of it) -- and pacing still elapsed a real gap before the
    # second, doomed run: the abort must not short-circuit pacing.
    times = _parse_run_log(run_log)
    assert len(times) == 2, f"expected 2 run.sh invocations, got {times}"
    gap = times[1] - times[0]
    assert gap >= 1.9, f"pacing did not run before the failing 2nd run (gap={gap:.3f}s)"

    # The wait is recorded even though the run it preceded went on to fail --
    # pacing's own record-keeping is not conditional on the run's outcome.
    assert pace_log.exists(), "pacing record missing even though pacing ran"
    lines = [ln for ln in pace_log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1, lines


# --- fix-round F1: pacing's own I/O faults must not abort the duel --------


def test_unreadable_loadavg_source_does_not_abort_the_duel(tmp_path, fake_repo):
    """F1 (fix round 1): under set -euo pipefail, an unreadable
    $LOADAVG_SRC used to propagate awk's own exit 2 straight out of
    pace_between_runs and abort the WHOLE duel before the second run ever
    fired -- a pacing infrastructure fault masquerading as a run failure.
    DUEL_LOADAVG_SRC below points at a path that is never created, so every
    read of it fails; if the isolation (`2>/dev/null || true`) were removed,
    duel.sh would exit 2 here and run 2 would never be invoked, which the
    length and exit-code assertions below both catch."""
    missing_loadavg = tmp_path / "does-not-exist" / "loadavg"
    run_log = tmp_path / "fake-run.log"

    result = _run_duel(
        tmp_path,
        fake_repo,
        FAKE_RUN_LOG=str(run_log),
        DUEL_PACE_LOG=str(tmp_path / "pacing.log"),
        DUEL_LOADAVG_SRC=str(missing_loadavg),
        DUEL_PACE_FLOOR_S="1",
        DUEL_PACE_CEILING_S="1",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )

    assert result.returncode == 0, result.stderr
    assert "duel complete" in result.stdout
    times = _parse_run_log(run_log)
    assert len(times) == 2, f"expected 2 run.sh invocations, got {times}"


def test_unwritable_pace_log_does_not_abort_the_duel(tmp_path, fake_repo):
    """F1 (fix round 1): an unwritable pacing-log path used to make
    `mkdir -p`'s own non-zero exit trip set -e and abort the duel with exit
    1 -- duel.sh's own documented "some runs failed" status, even though no
    run actually failed. DUEL_PACE_LOG is pointed inside a REGULAR FILE
    (not a directory), so `mkdir -p "$(dirname ...)"` genuinely fails every
    time; if the isolation around it were removed, this would surface as a
    non-zero exit code instead of the warning-and-proceed asserted below."""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory\n")
    unwritable_log = blocker / "nested" / "pacing.log"
    loadavg_file = tmp_path / "loadavg"
    loadavg_file.write_text("1.0 1.0 1.0 1/200 12345\n")
    run_log = tmp_path / "fake-run.log"

    result = _run_duel(
        tmp_path,
        fake_repo,
        FAKE_RUN_LOG=str(run_log),
        DUEL_PACE_LOG=str(unwritable_log),
        DUEL_LOADAVG_SRC=str(loadavg_file),
        DUEL_PACE_FLOOR_S="1",
        DUEL_PACE_CEILING_S="0",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )

    assert result.returncode == 0, result.stderr
    assert "duel complete" in result.stdout
    assert "WARNING" in result.stderr
    assert not unwritable_log.exists()
    times = _parse_run_log(run_log)
    assert len(times) == 2, f"expected 2 run.sh invocations, got {times}"
