"""Behavioural pins for scripts/e2e/stop_launch_tree.sh -- the teardown
launch_autoware.sh --stop delegates to.

These exist because the defect they cover was MEASURED, not imagined
(Task 15, 2026-07-30): --stop SIGTERMed the recorded `ros2 launch` pid and
printed "autoware launch + concat relay stopped" while 74 container processes
and 169 ROS nodes kept running, spinning hard because /clock no longer
advanced. The fix cannot be validated as a side effect of any cell that does
not launch Autoware, and validating it against the real 168-node stack costs a
full CARLA + Autoware bring-up, so the mechanism is pinned here instead,
against a synthetic supervisor that reproduces the same process shape.

WHAT IS FAITHFUL about the synthetic supervisor, and what is not:

* Faithful -- it starts its children with `start_new_session=True`, which is
  exactly what launch's ExecuteProcess does. The children get their own
  session (so a process-group signal aimed at the supervisor misses them)
  while remaining DIRECT children of the supervisor, which is what makes the
  parent/child snapshot in stop_launch_tree.sh the right handle.
* Faithful -- `orphan` mode leaves SIGTERM at its default disposition, so the
  supervisor dies without signalling its children. Measured 2026-07-31 to be
  exactly what a real `ros2 launch` does when started the way
  launch_autoware.sh starts it: SIGTERM killed it by default action, no launch
  code ran (its log gained nothing, not even launch_service.py's own "using
  SIGTERM ... can result in orphaned processes" warning), and both launched
  children kept running.
* Faithful -- `sigint_ignored` mode reproduces the disposition the real launch
  actually has. A shell without job control sets SIGHUP/SIGINT/SIGQUIT to
  SIG_IGN for a background job and SIG_IGN survives exec, so the measured
  launch had SigIgn 0x1001007 and SIGINT was a verified no-op on it. This is
  why the descendant sweep, not the signal ordering, is what makes --stop's
  contract true.
* NOT faithful -- the children are `time.sleep` loops, not composable-node
  containers, and there is no DDS, no /clock and no rclcpp shutdown path
  here. These tests pin the SIGNALLING and the reporting; they do not show
  that a real Autoware stack shuts down cleanly.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STOP_SCRIPT = REPO / "scripts" / "e2e" / "stop_launch_tree.sh"

# Stand-in for `ros2 launch`. argv: <pidfile> <n_children> <mode>.
#   orphan         no handlers -- SIGTERM kills it, its children survive
#   graceful       SIGINT shuts the children down, as a launch that CAN
#                  receive SIGINT does
#   sigint_ignored SIGINT ignored, SIGTERM default -- the disposition the real
#                  `nohup ros2 launch &` was measured to have
#   stubborn       SIGINT and SIGTERM both ignored, so only SIGKILL ends it
#   zombie_child   like `stubborn`, plus one extra child that exits at once and
#                  is never reaped, so the tree contains a live zombie
SUPERVISOR_SRC = """
import os
import signal
import subprocess
import sys
import time

pidfile, n, mode = sys.argv[1], int(sys.argv[2]), sys.argv[3]
kids = [
    subprocess.Popen(
        [sys.executable, "-c", "import time\\nwhile True: time.sleep(0.05)"],
        start_new_session=True,
    )
    for _ in range(n)
]

# One EXTRA child that exits at once and is never reaped -- this process holds
# its Popen and never calls wait(), so it stays a zombie for as long as this
# process lives. `kill -0` succeeds on it; only the /proc state field says it
# is gone. Its pid goes on the last line of the pid list.
if mode == "zombie_child":
    dead = subprocess.Popen([sys.executable, "-c", ""], start_new_session=True)
    kids.append(dead)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

if mode == "graceful":

    def shutdown(signum, frame):
        for kid in kids:
            kid.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
elif mode == "sigint_ignored":
    signal.signal(signal.SIGINT, signal.SIG_IGN)
elif mode == "stubborn":
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

# Written LAST: its presence is the test's readiness signal, so it must not
# appear before the children exist.
with open(pidfile, "w") as handle:
    handle.write(str(os.getpid()))
while True:
    time.sleep(0.05)
"""

# The script's own signal ladder, compressed so the escalating path runs in a
# couple of seconds instead of ~30. Only the waits are overridden; the order
# of the signals under test is the shipped one.
FAST_LADDER = {
    "STOP_INT_WAIT_S": "1",
    "STOP_REINT_WAIT_S": "1",
    "STOP_TERM_WAIT_S": "1",
    "STOP_KILL_WAIT_S": "2",
    "STOP_POLL_S": "0.05",
}


def _proc_state(pid: int) -> str | None:
    """The process state letter from /proc/<pid>/stat, or None if it is gone.

    Split on the LAST ") " because comm can contain spaces and parentheses --
    the same reason stop_launch_tree.sh strips the prefix rather than counting
    fields.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return stat.rsplit(") ", 1)[1].split()[0]


def _alive(pid: int) -> bool:
    """True only for a process that is running. A zombie is NOT alive: it has
    exited and is merely unreaped, and counting it would make every test that
    outlives its supervisor flaky."""
    state = _proc_state(pid)
    return state is not None and state != "Z"


def _cmdline_of(pid: int) -> str:
    """The pid's command line the way launch_autoware.sh records it -- NUL
    separators turned into spaces, trailing separator included, byte for byte
    what `tr "\\0" " " </proc/<pid>/cmdline` writes once its Task 18b polling
    loop settles (launch_autoware.sh:215-229; the read itself is at :217).
    The pid-reuse guard compares for exact equality, so an approximation here
    would test a different string than the script does."""
    return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()


def _children_of(pid: int) -> list[int]:
    kids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        if stat.rsplit(") ", 1)[1].split()[1] == str(pid):
            kids.append(int(entry.name))
    return kids


def _wait_until(predicate, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def supervisor(tmp_path):
    """Starts a synthetic supervisor tree and guarantees it is gone afterwards
    even when the assertion under test fails."""
    started: list[tuple[int, list[int]]] = []

    def _start(mode: str, n_children: int = 3, pidfile: Path | None = None):
        # `pidfile` defaults to a fresh path per start, which keeps unrelated
        # tests independent. Pass one to reuse a FIXED path across successive
        # launches -- what the real harness does, since AW_PIDFILE and
        # RELAY_PIDFILE are constants in a long-lived container.
        if pidfile is None:
            pidfile = tmp_path / f"{mode}-{len(started)}.pid"
        proc = subprocess.Popen(
            [sys.executable, "-c", SUPERVISOR_SRC, str(pidfile), str(n_children), mode]
        )
        assert _wait_until(pidfile.is_file), "supervisor never recorded its pid"
        assert int(pidfile.read_text()) == proc.pid
        # `zombie_child` starts one EXTRA, immediately-exiting child.
        expected = n_children + (1 if mode == "zombie_child" else 0)
        kids = _children_of(proc.pid)
        assert len(kids) == expected, f"expected {expected} children, got {kids}"
        started.append((proc.pid, kids))
        return pidfile, proc.pid, kids

    yield _start

    for root, kids in started:
        for pid in [root, *kids]:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        _wait_until(lambda root=root: not _alive(root), timeout_s=5)


def _run_stop(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(STOP_SCRIPT), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        env={**os.environ, **FAST_LADDER},
        timeout=120,
        check=False,
    )


def test_sigterm_alone_orphans_the_tree(supervisor):
    """The defect, reproduced: SIGTERM to the recorded pid alone kills the
    supervisor and leaves every child running. This is what --stop used to do,
    and why its success message was not evidence of anything."""
    _pidfile, root, kids = supervisor("orphan")

    os.kill(root, signal.SIGTERM)

    assert _wait_until(lambda: not _alive(root)), "supervisor survived SIGTERM"
    assert [pid for pid in kids if _alive(pid)] == kids, "children should have been orphaned"


def test_stop_clears_a_tree_whose_root_handles_sigint(supervisor):
    pidfile, root, kids = supervisor("graceful")

    result = _run_stop(pidfile)

    assert result.returncode == 0, result.stderr
    assert not _alive(root)
    assert [pid for pid in kids if _alive(pid)] == []
    # The root plus its three children, all four counted as recorded.
    assert "4 process(es) in the recorded trees" in result.stdout
    assert "0 survivor(s)" in result.stdout
    assert not pidfile.exists(), "a fully stopped tree's pid file must be removed"


def test_stop_clears_a_tree_whose_root_ignores_sigint(supervisor):
    """The configuration the REAL launch was measured to be in: SIGINT is
    ignored (inherited SIG_IGN from the `nohup ... &` launch), so the graceful
    rung cannot land and the descendant sweep is the only thing that stops the
    tree. This is the case the fix exists for."""
    pidfile, root, kids = supervisor("sigint_ignored")

    result = _run_stop(pidfile)

    assert result.returncode == 0, result.stderr
    assert not _alive(root)
    assert [pid for pid in kids if _alive(pid)] == []
    assert "0 survivor(s)" in result.stdout


def test_stop_clears_a_tree_whose_root_ignores_sigint_and_sigterm(supervisor):
    """The escalation ladder, end to end. A supervisor that ignores both
    SIGINT and SIGTERM still ends up stopped, and its children with it -- the
    backstop that makes the --stop contract true even when the graceful path
    does not work."""
    pidfile, root, kids = supervisor("stubborn")

    result = _run_stop(pidfile)

    assert result.returncode == 0, result.stderr
    assert not _alive(root)
    assert [pid for pid in kids if _alive(pid)] == []
    assert "0 survivor(s)" in result.stdout


def test_stop_kills_nothing_outside_the_recorded_tree(supervisor, tmp_path):
    """The bound the whole design rests on -- "kills only what it launched" --
    pinned by asserting the FORBIDDEN behaviour does not happen. An unrelated
    process runs alongside the recorded tree, is not a descendant of the
    recorded pid, and must be untouched."""
    pidfile, root, kids = supervisor("sigint_ignored")
    bystander = subprocess.Popen(
        [sys.executable, "-c", "import time\nwhile True: time.sleep(0.05)"],
        start_new_session=True,
    )
    try:
        assert _alive(bystander.pid)

        result = _run_stop(pidfile)

        assert result.returncode == 0, result.stderr
        assert not _alive(root)
        assert [pid for pid in kids if _alive(pid)] == []
        assert _alive(bystander.pid), "the sweep killed a process it never launched"
        assert str(bystander.pid) not in result.stdout
    finally:
        bystander.kill()
        bystander.wait(timeout=5)


def test_a_zombie_in_the_tree_is_not_counted_as_a_survivor(supervisor):
    """`alive()` reads /proc's state field instead of using `kill -0`, because
    `kill -0` succeeds on an unreaped child forever. That fix was made for a
    MEASURED false alarm (a fully dead 9-process tree reported as 8 survivors),
    and it needs a zombie to exercise -- which a host test can produce, since
    the zombie's parent here is the supervisor and not init.

    Discriminating on the rung line rather than the final count: the tree is a
    stubborn root plus one live child plus one zombie, so the survivor set is
    TWO. Under `kill -0` semantics it would be three, and the zombie would be
    signalled at every rung."""
    pidfile, root, kids = supervisor("zombie_child", n_children=1)
    # Identified by STATE, never by creation order: /proc iteration order is
    # not creation order, so indexing into `kids` would be a coin flip.
    assert _wait_until(lambda: any(_proc_state(k) == "Z" for k in kids)), "no zombie was produced"
    zombie = next(k for k in kids if _proc_state(k) == "Z")
    live_kid = next(k for k in kids if k != zombie)
    assert _alive(live_kid)
    # The premise: the zombie is indistinguishable from a live process to the
    # test the previous implementation used.
    os.kill(zombie, 0)

    result = _run_stop(pidfile)

    assert result.returncode == 0, result.stderr
    assert "2 of pid %d's tree still up" % root in result.stdout, result.stdout
    assert "3 of pid %d's tree still up" % root not in result.stdout
    assert "0 survivor(s)" in result.stdout
    assert not _alive(root)
    assert not _alive(live_kid)


def test_a_rung_one_success_does_not_leave_the_sidecar_behind(supervisor):
    """The pid-reuse guard's sidecar must never outlive the pid file it
    describes. The graceful rung was the path that broke the pairing: it
    removed the pid file and left `<pidfile>.cmd` on disk, so the next launch
    at the same fixed path could be judged against a PREVIOUS launch's command
    line. Asserted on the rung that actually succeeded, so this cannot pass by
    the tree merely having been cleared some other way."""
    pidfile, root, _kids = supervisor("graceful")
    sidecar = Path(f"{pidfile}.cmd")
    sidecar.write_text(_cmdline_of(root))

    result = _run_stop(pidfile)

    assert result.returncode == 0, result.stderr
    assert "gone after SIGINT to the root" in result.stdout, result.stdout
    assert not pidfile.exists(), "a fully stopped tree's pid file must be removed"
    assert not sidecar.exists(), "the sidecar outlived the pid file it describes"


def test_a_stale_sidecar_does_not_skip_the_next_launchs_teardown(supervisor, tmp_path):
    """The harm behind the previous test, end to end -- the FALSE POSITIVE the
    script header rules out, which a leaked sidecar made reachable.

    launch_autoware.sh writes the sidecar BEST EFFORT (its Task 18b polling
    loop only ever writes via a plain redirect with no `set -e` in effect,
    launch_autoware.sh:215-229), so a launch legitimately produces a pid file
    with no `.cmd` beside it. If a previous teardown leaked its sidecar at that same
    fixed path, the guard compares the OLD command line against the NEW pid,
    sees a mismatch, and SKIPS a teardown that was entirely legitimate -- a
    silent no-op teardown, which is the harmful direction for a campaign that
    has already recorded a Task 15 stack surviving --stop.

    The second launch runs `sigint_ignored`, the disposition the real launch
    was measured to have, so the teardown under test is the descendant sweep
    rather than the graceful rung."""
    pidfile = tmp_path / "e2e-autoware.pid"

    # Launch 1, torn down on the graceful rung, with a sidecar recorded as
    # launch_autoware.sh records one.
    _pf, root1, _kids1 = supervisor("graceful", pidfile=pidfile)
    sidecar = Path(f"{pidfile}.cmd")
    sidecar.write_text(_cmdline_of(root1))
    first = _run_stop(pidfile)
    assert first.returncode == 0, first.stderr
    assert not pidfile.exists()
    assert not sidecar.exists(), "launch 1's sidecar outlived its pid file"

    # Launch 2 at the SAME path, with no sidecar of its own.
    _pf2, root2, kids2 = supervisor("sigint_ignored", pidfile=pidfile)

    second = _run_stop(pidfile)

    assert second.returncode == 0, second.stderr
    assert "SKIPPING" not in second.stdout, second.stdout
    assert not _alive(root2), "the teardown skipped a legitimate root"
    assert [pid for pid in kids2 if _alive(pid)] == []
    assert "0 survivor(s)" in second.stdout


def test_stop_reports_an_absent_pidfile_without_refusing(tmp_path):
    """A teardown must never block on a missing pid file: nothing was
    recorded, so there is nothing to stop, and exiting non-zero here would
    make run_e2e.sh's cleanup path look like a failure."""
    result = _run_stop(tmp_path / "never-written.pid")

    assert result.returncode == 0, result.stderr
    assert "absent" in result.stdout
    assert "0 survivor(s)" in result.stdout


# --- D2 (Task 18b): a skip must not be reported as a success ---------------


def test_summary_reports_a_skip_instead_of_claiming_stopped(supervisor):
    """D2's real-code-path pin. Before this, stop_one's pid-reuse-guard skip
    returned BEFORE TOTAL_TREE was ever touched, so the FINAL summary always
    printed the unconditional "autoware launch + concat relay stopped ...
    0 survivor(s)" heading even when a recorded, presumably-still-running
    tree was left completely untouched -- the exact silent-no-op-teardown
    shape this script exists to end, MEASURED live on 5/10 cell-B static
    runs (results/B/run-017,019,020,021,022) where that heading printed
    while 56 processes stayed up in the container. The skip's own
    "SKIPPING" line was never the problem; the trusted summary line was.

    Forces the real skip path -- a live root with a `.cmd` sidecar that
    cannot possibly match its real /proc cmdline -- and checks the summary
    both says so AND stops claiming the unconditional "stopped" heading,
    while everything non-fatal about the script is unchanged: exit 0, the
    tree genuinely left alone (still alive), and both files kept for a
    retry."""
    pidfile, root, kids = supervisor("sigint_ignored")
    sidecar = Path(f"{pidfile}.cmd")
    sidecar.write_text("nothing that ever ran as this pid")

    result = _run_stop(pidfile)

    assert result.returncode == 0, result.stderr
    assert "SKIPPING" in result.stdout, result.stdout
    assert "autoware launch + concat relay NOT fully stopped:" in result.stdout, result.stdout
    assert "1 of 1 recorded tree(s) SKIPPED" in result.stdout, result.stdout
    assert "presumed STILL RUNNING" in result.stdout, result.stdout
    # The claim a bare-text scan could not tell apart from the real fix: the
    # OLD unconditional heading must not appear anywhere in this output.
    assert "relay stopped (" not in result.stdout, result.stdout
    # Still never a refusal: the guard declined to touch a live tree, so it
    # really is still alive, and both files are kept for a retry.
    assert _alive(root), "the guard should not have touched this tree"
    assert [pid for pid in kids if _alive(pid)] == kids
    assert pidfile.exists(), "a skipped pid file must be kept for a retry"
    assert sidecar.exists(), "a skipped sidecar must be kept for a retry"


def test_summary_still_claims_stopped_when_nothing_was_skipped(supervisor):
    """The inverse of the previous test, so D2 cannot be satisfied by simply
    always printing the "NOT fully stopped" heading: a normal teardown with
    no pid-reuse mismatch must still get the original, unconditional
    "stopped" claim -- the wording this whole file's other tests already
    depend on."""
    pidfile, root, kids = supervisor("graceful")

    result = _run_stop(pidfile)

    assert result.returncode == 0, result.stderr
    assert "SKIPPING" not in result.stdout, result.stdout
    assert "autoware launch + concat relay stopped (" in result.stdout, result.stdout
    assert "NOT fully stopped" not in result.stdout, result.stdout
    assert not _alive(root)
    assert [pid for pid in kids if _alive(pid)] == []
