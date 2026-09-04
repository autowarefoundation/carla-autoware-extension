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
import re
import shlex
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


# --- Task 4 (P4 transport-sweep plan): cell B-cyc's registered transport ---
# --- resolves by DEFAULT, the real run.sh code path ------------------------
#
# Unlike the --check-args pin just above (which drives duel.sh against a
# STAND-IN run.sh -- see the module docstring's "NOT faithful" note), this
# one drives the REAL benchmarks/run.sh directly: it is pinning run.sh's OWN
# per-cell transport correction, not duel.sh's pacing around it, so the
# stand-in would test nothing. --check-args is still what makes it cheap and
# hermetic to run here (run.sh's own comment: "the last point before
# anything touches the host" -- no preflight, no docker, no results/ write).

RUN_SH = REPO / "benchmarks" / "run.sh"


def test_bcyc_default_transport_is_row11():
    """Cell B-cyc's registered transport is cyclone/off/none (P4 spec Task 4,
    config/cells.yaml's B-cyc entry). run.sh must resolve it by DEFAULT --
    with no --rmw/--dds-profile passed -- so `duel.sh A B-cyc`, which passes
    IDENTICAL flags to both cells, still gives each cell its own registered
    transport, exactly as the tier4-native family correction already does
    for cell B (run.sh's `$CELL = "B-cyc"` branch, immediately after that
    family block)."""
    proc = subprocess.run(
        ["bash", str(RUN_SH), "B-cyc", "--arm", "static", "--check-args"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "rmw=rmw_cyclonedds_cpp" in proc.stdout, proc.stdout
    assert "shm=off" in proc.stdout, proc.stdout


# --- Task C2 (Amendment 2026-08-04): run.sh must RESOLVE the sweep class ---
# --- and FORWARD it to write_manifest as --class-id -------------------------
#
# Same reason `test_bcyc_default_transport_is_row11` just above lives here
# rather than in a duel test: this is run.sh's OWN resolution, so duel.sh's
# stand-in would test nothing, and --check-args is what makes driving the
# REAL run.sh cheap and hermetic. Two properties, pinned separately because
# they can break independently:
#
#   (1) --class resolves into run.sh's CLASS_ID and is echoed in the
#       --check-args block (the two tests immediately below), and
#   (2) that resolved value is actually FORWARDED to write_manifest as
#       `--class-id <value>` (the extract-then-execute tests after them).
#
# (2) cannot be reached through --check-args -- it exits at step 2, and the
# write_manifest invocation is step 4 -- and cannot be reached through
# --dry-run either, which deliberately DOES run preflight (host load, engine
# BuildId) and so needs the CARLA trees. So the forwarding block is pulled
# out of the real run.sh by regex and executed as real bash, the same
# extract-then-execute idiom tests/benchmarks/test_sweep_args.py uses for
# the launchers' class -> sensor-argument derivation and test_teardown.py
# uses for its sidecar polling loops. What is asserted is the REAL argv the
# real block builds, so deleting the `class_args+=(...)` line, inverting the
# guard, or dropping the array from the write_manifest call site all show up
# as a failure -- none of which a source text-scan would catch.


def test_run_sh_really_resolves_class_id_empty_by_default():
    """The legacy/no-class value: a plain (non-sweep) invocation must
    resolve to "", which is what RunManifest.class_id defaults to and what
    the pool rule's legacy clause (sweep_verdict._class_admits) reads as
    vlp16 -- the value every manifest predating the field carries."""
    proc = subprocess.run(
        ["bash", str(RUN_SH), "A", "--arm", "static", "--check-args"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "class_id=\n" in proc.stdout + "\n", proc.stdout


def test_run_sh_really_resolves_class_id_from_the_class_flag():
    """The other direction, so the pin above cannot be satisfied by a
    resolver hardwired to empty: `--class 32ch` must resolve VERBATIM.
    This is the value the launchers already derive their sensor arguments
    from (BENCH_CLASS_ID -> cells/extension.sh, cells/tier4-native.sh), so
    the manifest label and the rig actually booted come from one resolution,
    not two."""
    proc = subprocess.run(
        ["bash", str(RUN_SH), "A", "--arm", "paced", "--class", "32ch", "--check-args"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "class_id=32ch" in proc.stdout, proc.stdout


_CLASS_ARGS_BLOCK = re.compile(r'(  local class_args=\(\) class_show=""\n.*?\n  fi\n)', re.DOTALL)


def _extract_class_args_block() -> str:
    """The REAL `class_args` forwarding block out of benchmarks/run.sh, by
    regex -- so a change to the real file is what these tests run, not this
    file's memory of it (test_sweep_args._extract_derivation_block's idiom)."""
    m = _CLASS_ARGS_BLOCK.search(RUN_SH.read_text())
    assert m, "class_args forwarding block not found in run.sh"
    return m.group(1)


def _resolve_class_args(class_id: str) -> tuple[list[str], str]:
    """Run the extracted block as real bash for `CLASS_ID=<class_id>` and
    return (the argv elements it appends, the string it prints in the echoed
    command line). `local` needs a function body, so the snippet is wrapped
    in one -- exactly as run.sh itself has it, inside do_run()."""
    script = (
        "set -euo pipefail\n"
        f"CLASS_ID={shlex.quote(class_id)}\n"
        "probe() {\n"
        f"{_extract_class_args_block()}"
        "  printf 'COUNT<<%s>>\\n' \"${#class_args[@]}\"\n"
        '  for a in ${class_args[@]+"${class_args[@]}"}; do printf \'ARG<<%s>>\\n\' "$a"; done\n'
        "  printf 'SHOW<<%s>>\\n' \"$class_show\"\n"
        "}\n"
        "probe\n"
    )
    proc = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10, check=False
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    args = re.findall(r"ARG<<(.*?)>>", proc.stdout)
    count = int(re.search(r"COUNT<<(\d+)>>", proc.stdout).group(1))
    assert count == len(args), (count, args)
    show = re.search(r"SHOW<<(.*?)>>", proc.stdout, re.DOTALL).group(1)
    return args, show


def test_run_sh_forwards_the_resolved_class_to_write_manifest():
    """The forwarding half: a resolved class must reach write_manifest as
    `--class-id <value>` -- two separate argv elements, so a class id is
    never re-split or re-quoted on the way."""
    assert _resolve_class_args("32ch")[0] == ["--class-id", "32ch"]


def test_run_sh_forwards_nothing_when_no_class_was_requested():
    """A non-sweep run must append NO argument at all, not `--class-id ""`:
    an empty array element would become a stray argument, the same failure
    the --duel/--duel-id blocks above are shaped to avoid. write_manifest's
    own default ("") is then what lands in the manifest."""
    args, show = _resolve_class_args("")
    assert args == []
    assert show == ""


def test_run_sh_echoed_command_line_shows_the_class_id_flag():
    """The printed form must show the flag only when it is actually
    non-empty (the `duel_show` split's own rule): a run.sh transcript is
    evidence, and a printed command line that does not match the command
    that ran is a misstatement of the record."""
    assert _resolve_class_args("vlp16")[1] == " --class-id vlp16"


# --- Task C2 fix round 1 (finding I2): the array-BUILDING pin above does ----
# --- not pin that the array is PASSED, so pin the assembled argv -----------
#
# The three tests above extract only the block that BUILDS `class_args`
# (`local class_args=() … fi`). Removing `"${class_args[@]+"${class_args[@]}"}"`
# from the `write_manifest` invocation leaves every one of them green --
# measured: 382 tests across every suite module that touches run.sh, 0
# failures. The control mutation shows `duel_args` at the same call site is
# EQUALLY unpinned, so this is a gap inherited from Task 2's pattern, not a
# new one; this block closes it for both arrays at once.
#
# The span extracted here runs from `local duel_args=()` all the way through
# `die "manifest refused; nothing measured"`, so it contains the array
# construction AND the call site AND everything between. It is executed as
# real bash with `python3` replaced by a shell function that records its argv
# (functions are visible inside the `(cd "$REPO" && …)` subshell, and the
# recorder writes to a file so the block's own `>/dev/null` cannot swallow
# it). What is asserted is therefore the ACTUAL argument vector
# `write_manifest` would receive -- the only thing that decides what lands in
# the manifest.

_MANIFEST_CALL_BLOCK = re.compile(
    r'(  local duel_args=\(\) duel_show=""\n.*?\n    die "manifest refused; nothing measured"\n)',
    re.DOTALL,
)


def _extract_manifest_call_block() -> str:
    """The REAL span of run.sh that builds the optional-argument arrays and
    invokes `write_manifest`, by regex. Fails LOUDLY rather than silently
    passing if the span's anchors move (verified for the `class_args` block's
    own extractor, which this mirrors)."""
    m = _MANIFEST_CALL_BLOCK.search(RUN_SH.read_text())
    assert m, "write_manifest call block not found in run.sh"
    return m.group(1)


def _write_manifest_argv(tmp_path, *, duel="0", duel_id="", class_id="") -> list[str]:
    """Run the extracted span for real and return the argv `write_manifest`
    was actually called with. Every variable the span reads is stubbed to a
    recognisable placeholder; only DUEL / DUEL_ID / CLASS_ID vary."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    log = tmp_path / "argv.log"
    script = (
        "set -euo pipefail\n"
        'die() { echo "DIE: $*" >&2; exit 3; }\n'
        "show() { :; }\n"
        'python3() { for a in "$@"; do printf \'ARGV<<%s>>\\n\' "$a"; done >>"$PROBE_LOG"; }\n'
        f"PROBE_LOG={shlex.quote(str(log))}\n"
        f"REPO={shlex.quote(str(repo))}\n"
        "CELL=A\n"
        "run_dir=/results/A/run-007\n"
        "work_dir=/results/A/run-007\n"
        "next_idx=7\n"
        "effective_arm=paced\n"
        "RMW=rmw_cyclonedds_cpp\n"
        "SHM=off\n"
        "DDS_PROFILE=none\n"
        "carla_kind=0.10-fork\n"
        "autoware_image=img@sha256:aa\n"
        "placement_json={}\n"
        "DRY_RUN=0\n"
        f"DUEL={shlex.quote(duel)}\n"
        f"DUEL_ID={shlex.quote(duel_id)}\n"
        f"CLASS_ID={shlex.quote(class_id)}\n"
        "probe() {\n"
        f"{_extract_manifest_call_block()}"
        "}\n"
        "probe\n"
    )
    proc = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10, check=False
    )
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    return re.findall(r"ARGV<<(.*?)>>", log.read_text())


def _flag_value(argv: list[str], flag: str) -> str | None:
    """The argument following `flag`, or None when the flag is absent. Reads
    the PAIR, so a forwarding that passes the flag without its value (or with
    the wrong one) is not mistaken for a correct one."""
    return argv[argv.index(flag) + 1] if flag in argv else None


def test_write_manifest_argv_actually_carries_the_class_id(tmp_path):
    """THE pin for finding I2, class half: the assembled argv must contain
    `--class-id 32ch`. Fails when the class_args array is dropped from the
    write_manifest call site -- which every source-extraction test above
    passes straight over."""
    argv = _write_manifest_argv(tmp_path, class_id="32ch")
    assert _flag_value(argv, "--class-id") == "32ch", argv


def test_write_manifest_argv_actually_carries_the_duel_declaration(tmp_path):
    """The same pin for `duel_args` (Task 2's arrays, equally unpinned until
    now): both the bare `--duel` flag and the `--duel-id` pair must survive
    into the real argv. Closing I2 for one array and not the other would
    leave the identical defect one field over."""
    argv = _write_manifest_argv(tmp_path, duel="1", duel_id="A+B-cyc")
    assert "--duel" in argv, argv
    assert _flag_value(argv, "--duel-id") == "A+B-cyc", argv


def test_write_manifest_argv_carries_both_arrays_at_once(tmp_path):
    """Both arrays are appended at the same call site, so a mutation that
    drops the LAST one only (the shape the shipped code happens to have) is
    caught here even if each array's own single-field test were satisfied by
    a different code path."""
    argv = _write_manifest_argv(tmp_path, duel="1", duel_id="A+B-cyc", class_id="vlp16")
    assert _flag_value(argv, "--duel-id") == "A+B-cyc", argv
    assert _flag_value(argv, "--class-id") == "vlp16", argv


def test_write_manifest_argv_has_no_stray_empty_argument(tmp_path):
    """The property the `"${arr[@]+"${arr[@]}"}"` expansion exists for: with
    no duel and no class, NEITHER flag appears and -- the part a presence
    check would miss -- no empty-string argument is passed either. An empty
    argv element would shift write_manifest's own parsing."""
    argv = _write_manifest_argv(tmp_path)
    assert "--class-id" not in argv, argv
    assert "--duel" not in argv and "--duel-id" not in argv, argv
    assert "" not in argv, argv
    # The invocation itself is intact, so an empty argv is not what made the
    # three assertions above pass.
    assert argv[:2] == ["-m", "benchmarks.scripts.write_manifest"], argv


# --- Task C2 fix round 1 (finding I1): a sweep arm may not be filed with ----
# --- no class, or it pools into vlp16 while booting the 128ch rig ----------
#
# `_class_admits("", "vlp16")` is a statement about the PAST -- every filed
# sweep-arm run predating `RunManifest.class_id` is vlp16, verified -- and it
# must not become a way to mint NEW unlabelled sweep runs. Before this guard,
# run.sh's `allowed` gate opened the sweep arms on `--unpaced` OR a non-empty
# class, so `run.sh A --arm static --unpaced` was accepted with no class at
# all (verified: rc=0, `arm=unpaced`, `class_id=` empty) -- and with
# BENCH_CLASS_ID empty the launchers derive no sensor args, so the runner
# takes its default 128 channels (runner/__main__.py) and the run would have
# been scored as a vlp16 point.


def _check_args(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(RUN_SH), *args, "--check-args"],
        capture_output=True,
        text=True,
        cwd=REPO,
        timeout=60,
    )


def test_run_sh_refuses_a_sweep_arm_with_no_class():
    """The refusal itself, on the exact invocation that was accepted before:
    `--unpaced` promotes the arm to `unpaced`, a registered sweep arm, so it
    must now die rather than resolve. Loud and named, per the harness's
    preflight idiom -- and at step 1, before preflight touches the host."""
    proc = _check_args("A", "--arm", "static", "--unpaced")
    assert proc.returncode == 2, (proc.stdout, proc.stderr)
    assert "is a sweep arm" in proc.stderr, proc.stderr
    assert "requires --class" in proc.stderr, proc.stderr
    # The reason, not just the refusal: an operator must learn WHY without
    # reading run.sh.
    assert "128-channel" in proc.stderr, proc.stderr


def test_run_sh_refuses_every_sweep_arm_with_no_class():
    """Checked against `sweep_arms` itself rather than against `--unpaced`,
    so it holds for every path that can reach a sweep arm -- not only for the
    one flag that opened the gate today. `--arm ablation` with no class is
    refused too (by the arm gate before this guard, which is fine: the point
    is that no route to a sweep arm survives without a class)."""
    for extra in (("--arm", "ablation"), ("--arm", "paced")):
        proc = _check_args("A", *extra)
        assert proc.returncode == 2, (extra, proc.stdout, proc.stderr)


@pytest.mark.parametrize("cell", ["A", "B-cyc"])
@pytest.mark.parametrize("class_id", ["vlp16", "32ch"])
@pytest.mark.parametrize(
    "form", [("--arm", "paced"), ("--arm", "paced", "--unpaced"), ("--arm", "ablation")]
)
def test_every_registered_sweep_form_still_resolves(cell, class_id, form):
    """The other side of the guard: all three registered sweep forms, on both
    sweep cells, for both live classes, must still resolve. These are the
    forms `evidence/p4-task14-vlp16-sweep/sweep_driver.sh` ran and that
    directory's `step1-form-verification.log` recorded twelve invocations of
    -- every one of them carrying `--class`, which is why the guard costs
    nothing -- plus their 32ch equivalents, which the next task collects."""
    proc = _check_args(cell, *form, "--class", class_id)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert f"class_id={class_id}" in proc.stdout, proc.stdout


@pytest.mark.parametrize("arm", ["static", "closed-loop"])
def test_duel_arms_still_resolve_without_a_class(arm):
    """The guard must be scoped to SWEEP arms only: a duel/bring-up/gate run
    legitimately carries no class, files `class_id=""`, and is dropped by
    sweep_verdict's arm filter long before the class filter sees it."""
    proc = _check_args("A", "--arm", arm)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert "class_id=\n" in proc.stdout + "\n", proc.stdout


# --- Task 2 (Amendment 2026-08-03): duel.sh must stamp --duel-id on every --
# --- run.sh invocation it orders, derived from its OWN two cell args -------


def test_run_sh_invocation_carries_duel_id(tmp_path, fake_repo):
    """Real-code-path pin for the duel_id pool rule's stamping half: unlike
    the source text-scan a reader could satisfy by hardcoding a literal
    string anywhere in duel.sh, this reads the ACTUAL argv each run.sh
    invocation received (FAKE_RUN_SH logs `"$*"` verbatim), for BOTH
    invocations in the pair -- so a bug that stamps only the first, or
    that derives the id from the wrong cell order, shows up here. --check-
    args keeps this instant, per test_check_args_skips_pacing_entirely
    just above."""
    loadavg_file = tmp_path / "loadavg"
    loadavg_file.write_text("1.0 1.0 1.0 1/200 12345\n")
    run_log = tmp_path / "fake-run.log"

    result = _run_duel(
        tmp_path,
        fake_repo,
        extra_args=("--check-args",),
        proc_timeout=8,
        FAKE_RUN_LOG=str(run_log),
        DUEL_PACE_LOG=str(tmp_path / "pacing.log"),
        DUEL_LOADAVG_SRC=str(loadavg_file),
        DUEL_PACE_FLOOR_S="0",
        DUEL_PACE_CEILING_S="0",
        DUEL_PACE_POLL_S="1",
        DUEL_PACE_TARGET_LOADAVG="6",
    )
    assert result.returncode == 0, result.stderr

    lines = [ln for ln in run_log.read_text().splitlines() if ln.strip()]
    assert len(lines) == 2, f"expected 2 run.sh invocations, got {lines}"
    for line in lines:
        assert "--duel-id cellA+cellB" in line, line


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
