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

    def _start(mode: str, n_children: int = 3):
        pidfile = tmp_path / f"{mode}-{len(started)}.pid"
        proc = subprocess.Popen(
            [sys.executable, "-c", SUPERVISOR_SRC, str(pidfile), str(n_children), mode]
        )
        assert _wait_until(pidfile.is_file), "supervisor never recorded its pid"
        assert int(pidfile.read_text()) == proc.pid
        kids = _children_of(proc.pid)
        assert len(kids) == n_children, f"expected {n_children} children, got {kids}"
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


def test_stop_reports_an_absent_pidfile_without_refusing(tmp_path):
    """A teardown must never block on a missing pid file: nothing was
    recorded, so there is nothing to stop, and exiting non-zero here would
    make run_e2e.sh's cleanup path look like a failure."""
    result = _run_stop(tmp_path / "never-written.pid")

    assert result.returncode == 0, result.stderr
    assert "absent" in result.stdout
    assert "0 survivor(s)" in result.stdout
