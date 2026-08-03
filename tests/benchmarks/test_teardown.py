"""Behavioural pins for benchmarks/scripts/teardown.sh's tier4-native wiring
into scripts/e2e/stop_launch_tree.sh (Task 17c, D1-D3).

Task 16 built scripts/e2e/stop_launch_tree.sh -- a pidfile-driven,
signal-ladder recorded-tree teardown -- for the extension family only, and
tests/e2e/test_stop_launch_tree.py pins that script itself. What was UNPINNED
was the wiring: benchmarks/scripts/teardown.sh's tier4-native case branch
never called it and never touched either of cells/tier4_autoware.sh's
container-side pid files, so an interrupted cell-B run left its whole
`ros2 launch` tree behind with nothing holding a pid for it and nothing
reporting that it did -- the same defect Task 15 measured on the extension
family (169 nodes, 74 processes, loadavg 42, ten minutes after a "successful"
teardown).

This campaign has a binding rule that a substring/text-scan assertion is NOT
a pin (six prior violations, most recently Task 17b finding F5: two wiring
assertions that both still passed with the call site commented out). Every
test below that certifies a safety property therefore runs the REAL
benchmarks/scripts/teardown.sh as a subprocess, with a stand-in `docker`
placed on PATH ahead of any real one, and checks an effect that can only
happen if the wiring actually fired -- a real background process dying, a
real file appearing with real content, a real ordering between two real
events -- not a string appearing in source text.

WHAT IS FAITHFUL about the `docker` stand-in below, and what is not:

* Faithful -- for the exact `docker exec -i <container> bash -s --
  <pidfiles>` shape stop_tier4_launch_tree uses, it genuinely execs a REAL
  `bash -s --`, fed the REAL piped-in script content, against the REAL
  pidfile paths teardown.sh passes (remapped from their hardcoded
  /tmp/tier4-*.pid form into a per-test sandbox directory so no test ever
  touches those literal host paths). scripts/e2e/stop_launch_tree.sh's own
  signal ladder therefore runs for real here, against a real background
  process standing in for the container-side `ros2 launch` tree root.
* Faithful -- every OTHER docker subcommand teardown.sh can reach on this
  path (the bare `docker exec ... pkill ...` GT-collector kill, the
  `bash -lc` injector kill, `docker inspect`, `docker cp`, `docker rm`) is
  logged but never actually run, so a test can assert on call order and
  arguments without those unrelated steps touching the host.
* NOT faithful -- there is no real container, no real `ros2 launch` tree,
  and the stand-in process is a bare Python loop, not a composable-node
  container with DDS and /clock. These tests pin the WIRING (arguments,
  ordering, non-fatality, report retention); they do not show a real
  Autoware stack tears down cleanly under this path -- that is
  scripts/e2e/test_stop_launch_tree.py's honest limit too, and Task 18 is
  the first task allowed to check it live.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TEARDOWN = REPO / "benchmarks" / "scripts" / "teardown.sh"
STOP_SCRIPT = REPO / "scripts" / "e2e" / "stop_launch_tree.sh"
TIER4_CELL = REPO / "benchmarks" / "cells" / "tier4_autoware.sh"
LAUNCH_AUTOWARE = REPO / "scripts" / "e2e" / "launch_autoware.sh"

# Ladder waits compressed the same way tests/e2e/test_stop_launch_tree.py
# does, so a rung that is not skipped still costs a couple of seconds, not
# tens. The stand-in "tree" below dies on the first SIGINT regardless (a bare
# `python -c` loop has no handler installed, so the default action applies),
# but this bounds worst case if that ever stops being true.
FAST_LADDER = {
    "STOP_INT_WAIT_S": "1",
    "STOP_REINT_WAIT_S": "1",
    "STOP_TERM_WAIT_S": "1",
    "STOP_KILL_WAIT_S": "2",
    "STOP_POLL_S": "0.05",
}

# Stand-in for the container-side `ros2 launch` tree root / concat relay:
# no signal handler installed, so SIGINT ends it immediately -- this pins the
# WIRING, not the ladder (which already has its own pins).
STUB_SRC = "import time\nwhile True: time.sleep(0.05)\n"

# Stand-in for the fork/exec Task 18b's D1 closes: starts with ONE cmdline,
# then (after a real delay) execs into a DIFFERENT one, exactly like
# `nohup ros2 launch ...` starting as "nohup ros2 launch ..." and becoming
# "/usr/bin/python3 .../ros2 launch ..." once nohup's own exec lands. A
# single unassisted /proc read right after Popen() returns -- what the
# pre-fix line did -- lands on the PRE-exec argv every time for any delay
# that comfortably exceeds process-dispatch overhead; `delay_s` is the
# caller's knob for how long that PRE-exec window lasts.
DELAYED_EXEC_SRC = """
import os, sys, time
time.sleep({delay_s})
os.execv(sys.executable, [sys.executable, "-c", "import time\\nwhile True: time.sleep(0.05)"])
"""

# The `docker` stand-in placed on PATH ahead of any real `docker` binary.
# See the module docstring's "WHAT IS FAITHFUL" section for what it does and
# does not actually execute.
FAKE_DOCKER = """#!/usr/bin/env bash
set -u

log_call() {
  # NUL-separated, not newline-separated: the injector-kill exec (teardown.sh)
  # passes a multi-line `bash -lc SCRIPT` argument, so a newline cannot be the
  # record framing without corrupting it. NUL cannot appear inside an argv
  # element (argv is NUL-terminated C strings), so it is the only safe
  # delimiter here.
  {
    printf '%s\\0' "$@"
    printf '===END===\\0'
  } >>"${FAKE_DOCKER_LOG:?FAKE_DOCKER_LOG not set}"
}
log_call "$@"

sub="${1:-}"
case "$sub" in
  inspect)
    name="${*: -1}"
    if [ -n "${FAKE_DOCKER_EXISTS:-}" ] && [ -f "${FAKE_DOCKER_EXISTS}" ] &&
      grep -qxF "$name" "${FAKE_DOCKER_EXISTS}"; then
      exit 0
    fi
    exit 1
    ;;
  exec)
    shift
    [ "${1:-}" = "-i" ] && shift
    shift # drop the container name -- this stand-in only ever serves one
    if [ "${1:-}" = "bash" ] && [ "${2:-}" = "-s" ] && [ "${3:-}" = "--" ]; then
      shift 3
      cmd=(bash -s --)
      for a in "$@"; do
        case "$a" in
          /tmp/tier4-*) cmd+=("${FAKE_DOCKER_SANDBOX:?FAKE_DOCKER_SANDBOX unset}$a") ;;
          *) cmd+=("$a") ;;
        esac
      done
      # Records whether FAKE_DEMO_PID was still alive the instant this exec
      # fired -- the empirical check behind the D1 ordering-decision-1 test.
      if [ -n "${FAKE_ORDER_MARKER:-}" ]; then
        if [ -n "${FAKE_DEMO_PID:-}" ] && kill -0 "${FAKE_DEMO_PID}" 2>/dev/null; then
          echo alive >"${FAKE_ORDER_MARKER}"
        else
          echo dead >"${FAKE_ORDER_MARKER}"
        fi
      fi
      if [ -n "${FAKE_DOCKER_EXEC_RC:-}" ] && [ "${FAKE_DOCKER_EXEC_RC}" != "0" ]; then
        exit "${FAKE_DOCKER_EXEC_RC}"
      fi
      if [ -n "${FAKE_DOCKER_STDIN_CAPTURE:-}" ]; then
        cat >"${FAKE_DOCKER_STDIN_CAPTURE}"
        exec "${cmd[@]}" <"${FAKE_DOCKER_STDIN_CAPTURE}"
      else
        exec "${cmd[@]}"
      fi
    else
      # Any OTHER exec shape (the GT-collector `pkill`, the injector's
      # `bash -lc`) does not need to actually run for these tests, and must
      # not touch the real host's /tmp.
      exit 0
    fi
    ;;
  cp)
    exit "${FAKE_DOCKER_CP_RC:-0}"
    ;;
  rm)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
"""


def _wait_until(predicate, timeout_s: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _alive(pid: int) -> bool:
    try:
        stat_line = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    state = stat_line.rsplit(") ", 1)[1].split()[0]
    return state != "Z"


def _start_stub(tmp_path: Path, name: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", STUB_SRC])


def _start_delayed_exec_stub(delay_s: float) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", DELAYED_EXEC_SRC.format(delay_s=delay_s)])


def parse_calls(log_path: Path) -> list[list[str]]:
    """Every `docker` invocation the stand-in received, in call order, as its
    raw argv list. NUL-separated, with a NUL-terminated `===END===` sentinel
    closing each call: the injector-kill exec teardown.sh issues passes a
    multi-line `bash -lc SCRIPT` argument, so newlines cannot be the framing,
    and NUL cannot occur inside an argv element (argv is NUL-terminated C
    strings), which is what makes it safe against any argument's own
    content."""
    if not log_path.exists():
        return []
    tokens = [t for t in log_path.read_bytes().split(b"\0") if t != b""]
    calls: list[list[str]] = []
    current: list[str] = []
    for raw in tokens:
        tok = raw.decode()
        if tok == "===END===":
            calls.append(current)
            current = []
        else:
            current.append(tok)
    assert not current, f"log ended mid-call (no closing ===END===): {current}"
    return calls


@pytest.fixture
def fake_docker(tmp_path):
    """Installs the `docker` stand-in on PATH and returns a dict of the
    control knobs (env var names) and a `calls()` accessor. Every test opts
    into the specific behaviour it needs by setting env vars in the dict it
    passes to `run_teardown`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker_path = bindir / "docker"
    docker_path.write_text(FAKE_DOCKER)
    docker_path.chmod(docker_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "tmp").mkdir()
    log_path = tmp_path / "docker-calls.log"
    exists_path = tmp_path / "docker-exists.txt"

    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "FAKE_DOCKER_LOG": str(log_path),
        "FAKE_DOCKER_SANDBOX": str(sandbox),
        "FAKE_DOCKER_EXISTS": str(exists_path),
    }

    class Handle:
        def __init__(self):
            self.env = env
            self.sandbox = sandbox
            self.log_path = log_path

        def set_existing(self, *names: str) -> None:
            exists_path.write_text("\n".join(names) + "\n")

        def calls(self) -> list[list[str]]:
            return parse_calls(self.log_path)

        def sandboxed(self, tmp_pidfile: str) -> Path:
            """Where a literal /tmp/tier4-*.pid argument lands once the
            stand-in remaps it -- Path(sandbox + tmp_pidfile)."""
            return Path(str(self.sandbox) + tmp_pidfile)

    return Handle()


def _write_launch_env(run_dir: Path, **kv) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [f'{key}="{value}"' for key, value in kv.items()]
    (run_dir / "launch.env").write_text("\n".join(lines) + "\n")


def run_teardown(run_dir: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(TEARDOWN), str(run_dir)],
        capture_output=True,
        text=True,
        env={**env, **FAST_LADDER},
        timeout=60,
        check=False,
    )


CONTAINER = "fake-aw-container"


def _base_env(run_dir: Path, demo_pid_file: Path | None = None) -> dict:
    kv = {"APPROACH": "tier4-native", "AW_CONTAINER": CONTAINER, "AW_COMPOSE": ""}
    if demo_pid_file is not None:
        kv["TIER4_DEMO_PID_FILE"] = str(demo_pid_file)
    _write_launch_env(run_dir, **kv)
    return kv


# --- D1: the happy path really runs stop_launch_tree.sh -------------------


def test_tier4_native_teardown_really_stops_the_recorded_tree(tmp_path, fake_docker):
    """The real-code-path pin for D1's delivery mechanism: teardown.sh's
    tier4-native branch invokes `docker exec -i <container> bash -s --
    <relay-pidfile> <autoware-pidfile>`, piping in a script that -- once
    run for real, here, against real stand-in processes -- actually stops
    them. A text-scan could pass with the call site commented out (Task 17b
    finding F5); this cannot, because nothing would die."""
    run_dir = tmp_path / "run"
    fake_docker.set_existing(CONTAINER)

    relay_pidfile = "/tmp/tier4-concat-relay.pid"
    aw_pidfile = "/tmp/tier4-autoware.pid"
    relay_proc = _start_stub(tmp_path, "relay")
    aw_proc = _start_stub(tmp_path, "autoware")
    try:
        sandboxed_relay = fake_docker.sandboxed(relay_pidfile)
        sandboxed_aw = fake_docker.sandboxed(aw_pidfile)
        sandboxed_relay.write_text(str(relay_proc.pid))
        sandboxed_aw.write_text(str(aw_proc.pid))
        stdin_capture = tmp_path / "stdin-capture.sh"
        fake_docker.env["FAKE_DOCKER_STDIN_CAPTURE"] = str(stdin_capture)

        _base_env(run_dir)
        result = run_teardown(run_dir, fake_docker.env)

        assert result.returncode == 0, result.stderr
        # The exact argv teardown.sh must pass -- the literal container-side
        # paths D2/the brief require, not whatever this test finds convenient.
        calls = fake_docker.calls()
        exec_calls = [c for c in calls if c[:1] == ["exec"]]
        tree_calls = [c for c in exec_calls if "bash" in c and "-s" in c]
        assert len(tree_calls) == 1, calls
        assert tree_calls[0] == [
            "exec",
            "-i",
            CONTAINER,
            "bash",
            "-s",
            "--",
            relay_pidfile,
            aw_pidfile,
        ]
        # The piped script is byte-for-byte the REAL stop_launch_tree.sh --
        # not a copy, not a paraphrase.
        assert stdin_capture.read_bytes() == STOP_SCRIPT.read_bytes()
        # And it really ran: both stand-in processes are gone.
        assert _wait_until(lambda: not _alive(relay_proc.pid))
        assert _wait_until(lambda: not _alive(aw_proc.pid))
        assert "2 pid file(s) checked" in result.stdout, result.stdout
        assert "0 survivor(s)" in result.stdout, result.stdout
    finally:
        for p in (relay_proc, aw_proc):
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)


# --- D1 ordering decision 1: tree stop before the demo ---------------------


def test_tree_stop_runs_before_the_demo_is_stopped(tmp_path, fake_docker):
    """D1 ordering decision 1's real-code-path pin: at the moment the
    recorded-tree stop fires, the demo pid recorded in TIER4_DEMO_PID_FILE
    must still be alive. If the case branch is reordered so the demo is
    stopped first, this fails because the demo is verifiably dead by then --
    not because a comment says so."""
    run_dir = tmp_path / "run"
    fake_docker.set_existing(CONTAINER)
    demo_proc = _start_stub(tmp_path, "demo")
    aw_proc = _start_stub(tmp_path, "autoware")
    try:
        demo_pidfile = tmp_path / "demo.pid"
        demo_pidfile.write_text(str(demo_proc.pid))
        fake_docker.sandboxed("/tmp/tier4-autoware.pid").write_text(str(aw_proc.pid))
        marker = tmp_path / "order-marker.txt"
        fake_docker.env["FAKE_ORDER_MARKER"] = str(marker)
        fake_docker.env["FAKE_DEMO_PID"] = str(demo_proc.pid)

        _base_env(run_dir, demo_pid_file=demo_pidfile)
        result = run_teardown(run_dir, fake_docker.env)

        assert result.returncode == 0, result.stderr
        assert marker.exists(), "the tree-stop exec never fired"
        assert marker.read_text().strip() == "alive", (
            "the demo was already stopped by the time the tree stop ran "
            "-- D1 ordering decision 1 is violated"
        )
        # stop_pidfile still ran afterwards -- teardown is otherwise unchanged.
        assert _wait_until(lambda: not _alive(demo_proc.pid))
        assert not demo_pidfile.exists()
    finally:
        for p in (demo_proc, aw_proc):
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)


# --- D1 ordering decision 2: tree stop before the log copy -----------------


def test_tree_stop_runs_before_the_log_copy(tmp_path, fake_docker):
    """D1 ordering decision 2's pin: the `docker exec ... bash -s --` call
    must precede any `docker cp` call in teardown's own real execution
    order, not just in source order -- read off the stand-in's call log,
    which only gains an entry when teardown.sh actually reaches that
    statement."""
    run_dir = tmp_path / "run"
    fake_docker.set_existing(CONTAINER)
    aw_proc = _start_stub(tmp_path, "autoware")
    try:
        fake_docker.sandboxed("/tmp/tier4-autoware.pid").write_text(str(aw_proc.pid))
        fake_docker.sandboxed("/tmp/tier4-concat-relay.pid").write_text(str(aw_proc.pid))

        _base_env(run_dir)
        result = run_teardown(run_dir, fake_docker.env)

        assert result.returncode == 0, result.stderr
        calls = fake_docker.calls()
        tree_idx = next(
            i for i, c in enumerate(calls) if c[:1] == ["exec"] and "bash" in c and "-s" in c
        )
        cp_indices = [i for i, c in enumerate(calls) if c[:1] == ["cp"]]
        assert cp_indices, "docker cp was never called -- nothing to order against"
        assert tree_idx < min(cp_indices), calls
    finally:
        if aw_proc.poll() is None:
            aw_proc.kill()
        aw_proc.wait(timeout=5)


# --- D3: the survivor report reaches the run directory ---------------------


def test_survivor_report_is_retained_in_the_run_directory(tmp_path, fake_docker):
    """D3's real-code-path pin: stop_launch_tree.sh's own summary line --
    the whole point of D1 on an interrupted run -- must land in a file
    under $RUN_DIR, not just in this process's own stdout. Read off the
    REAL report the real script printed, not a hardcoded string."""
    run_dir = tmp_path / "run"
    fake_docker.set_existing(CONTAINER)
    aw_proc = _start_stub(tmp_path, "autoware")
    try:
        fake_docker.sandboxed("/tmp/tier4-autoware.pid").write_text(str(aw_proc.pid))
        fake_docker.sandboxed("/tmp/tier4-concat-relay.pid").write_text(str(aw_proc.pid))

        _base_env(run_dir)
        result = run_teardown(run_dir, fake_docker.env)

        assert result.returncode == 0, result.stderr
        log_file = run_dir / "tier4-stop-launch-tree.log"
        assert log_file.exists(), "no per-run retention of the tree-stop report"
        report = log_file.read_text()
        assert "autoware launch + concat relay stopped" in report
        assert "survivor(s)" in report
        # Teed, not redirected only into the file: this process's own stdout
        # (what an interactive run.sh invocation shows) still carries it too.
        assert "autoware launch + concat relay stopped" in result.stdout
    finally:
        if aw_proc.poll() is None:
            aw_proc.kill()
        aw_proc.wait(timeout=5)


# --- F3 (fix round 1): append, not truncate, across a repeated invocation --


def test_repeated_teardown_with_container_still_present_appends_the_report(tmp_path, fake_docker):
    """F3's real-code-path pin: teardown.sh runs TWICE per real run (:27-29
    below) -- once on the success path, once from run.sh's EXIT trap -- and
    the second call normally returns early because `docker inspect` fails
    once the container is gone (:361's `docker rm -f`). But if THAT
    removal itself failed -- the wedged state this whole task exists to
    report on -- the container is still there, `stop_tier4_launch_tree`
    re-enters, and a TRUNCATING `tee` would silently replace the first,
    informative report with the second. This never removes the container
    from the stand-in's "existing" list across two REAL, separate
    teardown.sh subprocess invocations against the SAME run_dir, so the
    second exec genuinely re-fires against a second real stand-in tree --
    then checks the retained log carries BOTH reports. A truncating `tee`
    (reverting fix round 1's `-a`) leaves only the second, failing this."""
    run_dir = tmp_path / "run"
    fake_docker.set_existing(CONTAINER)
    _base_env(run_dir)

    relay1, aw1 = _start_stub(tmp_path, "relay1"), _start_stub(tmp_path, "aw1")
    try:
        fake_docker.sandboxed("/tmp/tier4-concat-relay.pid").write_text(str(relay1.pid))
        fake_docker.sandboxed("/tmp/tier4-autoware.pid").write_text(str(aw1.pid))
        result1 = run_teardown(run_dir, fake_docker.env)
        assert result1.returncode == 0, result1.stderr
        assert _wait_until(lambda: not _alive(relay1.pid))
        assert _wait_until(lambda: not _alive(aw1.pid))
    finally:
        for p in (relay1, aw1):
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)

    # Second invocation, same run_dir, same container name still reported as
    # existing (the stand-in's `rm` subcommand never edits the exists file --
    # modelling a `docker rm -f` that did not actually take), against a
    # fresh pair of real stand-in processes.
    relay2, aw2 = _start_stub(tmp_path, "relay2"), _start_stub(tmp_path, "aw2")
    try:
        fake_docker.sandboxed("/tmp/tier4-concat-relay.pid").write_text(str(relay2.pid))
        fake_docker.sandboxed("/tmp/tier4-autoware.pid").write_text(str(aw2.pid))
        result2 = run_teardown(run_dir, fake_docker.env)
        assert result2.returncode == 0, result2.stderr
        assert _wait_until(lambda: not _alive(relay2.pid))
        assert _wait_until(lambda: not _alive(aw2.pid))
    finally:
        for p in (relay2, aw2):
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)

    log_file = run_dir / "tier4-stop-launch-tree.log"
    assert log_file.exists()
    report = log_file.read_text()
    # Each real invocation prints this exactly once (stop_launch_tree.sh's
    # own final summary line); two occurrences means both were retained.
    assert report.count("autoware launch + concat relay stopped") == 2, report


def _extract_log_target_guard() -> str:
    """Pulls the REAL log_target fallback guard (fix round 1, F3) straight
    out of benchmarks/scripts/teardown.sh by regex, the same
    regex-extraction technique the D2 sidecar tests below use, so a change
    to the real guard is what this test runs -- not this test's own memory
    of it."""
    import re

    text = TEARDOWN.read_text()
    pattern = re.compile(
        r'(local log_target="\$RUN_DIR/tier4-stop-launch-tree\.log"\n'
        r'  \[ -n "\$\{RUN_DIR:-\}" \] && \[ -d "\$RUN_DIR" \] \|\| '
        r"log_target=/dev/null)"
    )
    m = pattern.search(text)
    assert m, "log_target fallback guard not found in teardown.sh"
    return m.group(1)


def test_log_target_falls_back_to_devnull_when_run_dir_is_missing(tmp_path):
    """F3's second real-code-path pin (fix round 1): a `tee` pointed at a
    path under a $RUN_DIR that does not exist fails to open its target and
    exits immediately, SIGPIPE-ing whatever is still writing to the far end
    of the pipe -- surfacing as the tree-stop exec exiting 141 mid-ladder
    instead of completing it. Runs the REAL guard line (extracted above) as
    real bash, under `set -u` to match teardown.sh's own flags, against a
    RUN_DIR that is set (as it always is in the real script, from its own
    `${1:?...}`) but points at a directory that does not exist, and against
    one that does -- checking log_target resolves to /dev/null only in the
    first case."""
    guard = _extract_log_target_guard()

    def resolve(run_dir_value: str) -> str:
        # Wrapped in a function, not run at top level: the real guard's
        # `local` only works inside a function (it lives inside
        # stop_tier4_launch_tree() in teardown.sh), and `local` outside one
        # is a non-fatal bash error that would silently leave $log_target
        # unset instead of reproducing the real scoping.
        script = (
            "set -u\n"
            "probe() {\n"
            f'  local RUN_DIR="{run_dir_value}"\n'
            f"  {guard}\n"
            '  echo "$log_target"\n'
            "}\n"
            "probe\n"
        )
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=10, check=False
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    missing_dir = tmp_path / "does-not-exist"
    assert resolve(str(missing_dir)) == "/dev/null"

    real_dir = tmp_path / "real"
    real_dir.mkdir()
    assert resolve(str(real_dir)) == f"{real_dir}/tier4-stop-launch-tree.log"


# --- non-fatal on a missing container, missing script, failed exec --------


def test_missing_container_leaves_teardown_otherwise_unchanged(tmp_path, fake_docker):
    """No container registered as existing -- `docker inspect` reports it
    absent, exactly as it would for a run whose launcher died before the
    container was even created. The tree-stop exec must never fire, and
    everything else in teardown must still run."""
    run_dir = tmp_path / "run"
    # Deliberately do not call fake_docker.set_existing(): inspect -> 1.
    demo_proc = _start_stub(tmp_path, "demo")
    try:
        demo_pidfile = tmp_path / "demo.pid"
        demo_pidfile.write_text(str(demo_proc.pid))

        _base_env(run_dir, demo_pid_file=demo_pidfile)
        result = run_teardown(run_dir, fake_docker.env)

        assert result.returncode == 0, result.stderr
        calls = fake_docker.calls()
        assert not [c for c in calls if c[:1] == ["exec"] and "bash" in c and "-s" in c]
        assert _wait_until(lambda: not _alive(demo_proc.pid)), (
            "a missing container blocked the rest of teardown"
        )
    finally:
        if demo_proc.poll() is None:
            demo_proc.kill()
        demo_proc.wait(timeout=5)


def test_missing_stop_script_leaves_teardown_otherwise_unchanged(tmp_path, fake_docker):
    """A real missing-file condition (not simulated): a from-scratch repo
    copy that has benchmarks/scripts/teardown.sh but genuinely lacks
    scripts/e2e/stop_launch_tree.sh at the path $REPO/scripts/e2e/ resolves
    to for that copy. Exercises teardown's own `$REPO` derivation, which is
    relative to teardown.sh's OWN location (Task 17c, D1)."""
    repo_copy = tmp_path / "repo_copy"
    (repo_copy / "benchmarks" / "scripts").mkdir(parents=True)
    teardown_copy = repo_copy / "benchmarks" / "scripts" / "teardown.sh"
    teardown_copy.write_text(TEARDOWN.read_text())
    teardown_copy.chmod(teardown_copy.stat().st_mode | stat.S_IEXEC)
    # scripts/e2e/stop_launch_tree.sh is deliberately NOT created here.

    run_dir = tmp_path / "run"
    fake_docker.set_existing(CONTAINER)
    demo_proc = _start_stub(tmp_path, "demo")
    try:
        demo_pidfile = tmp_path / "demo.pid"
        demo_pidfile.write_text(str(demo_proc.pid))
        _base_env(run_dir, demo_pid_file=demo_pidfile)

        result = subprocess.run(
            ["bash", str(teardown_copy), str(run_dir)],
            capture_output=True,
            text=True,
            env={**fake_docker.env, **FAST_LADDER},
            timeout=60,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert "missing" in result.stdout, result.stdout
        calls = fake_docker.calls()
        assert not [c for c in calls if c[:1] == ["exec"] and "bash" in c and "-s" in c]
        assert _wait_until(lambda: not _alive(demo_proc.pid)), (
            "a missing stop_launch_tree.sh blocked the rest of teardown"
        )
    finally:
        if demo_proc.poll() is None:
            demo_proc.kill()
        demo_proc.wait(timeout=5)


def test_failed_docker_exec_leaves_teardown_otherwise_unchanged(tmp_path, fake_docker):
    """`docker exec` itself failing (a daemon hiccup, a container that died
    between the inspect and the exec) must not block the rest of teardown,
    and must say so rather than pretend nothing happened."""
    run_dir = tmp_path / "run"
    fake_docker.set_existing(CONTAINER)
    fake_docker.env["FAKE_DOCKER_EXEC_RC"] = "17"
    demo_proc = _start_stub(tmp_path, "demo")
    try:
        demo_pidfile = tmp_path / "demo.pid"
        demo_pidfile.write_text(str(demo_proc.pid))
        _base_env(run_dir, demo_pid_file=demo_pidfile)

        result = run_teardown(run_dir, fake_docker.env)

        assert result.returncode == 0, result.stderr
        assert "exited 17" in result.stdout, result.stdout
        assert _wait_until(lambda: not _alive(demo_proc.pid)), (
            "a failed docker exec blocked the rest of teardown"
        )
    finally:
        if demo_proc.poll() is None:
            demo_proc.kill()
        demo_proc.wait(timeout=5)


# --- D2/D1: the .cmd sidecars cells/tier4_autoware.sh writes ---------------
#
# AW_PIDFILE and RELAY_PIDFILE wrote DIFFERENT shapes between Task 18b and
# fix round 1: only AW_PIDFILE got the fork/exec-race-closing polling loop
# at first (D1 was scoped to the AUTOWARE launch pid only, per the brief),
# while RELAY_PIDFILE kept the original single-line best-effort `tr`. Fix
# round 1, F3 closed that gap -- the controller's own scope correction, not
# a new defect -- so both pidfiles now run the identical loop shape and are
# extracted/tested the identical way below; the RELAY_PIDFILE-specific
# heredoc-based extraction this section used to hold is gone with it (the
# heredoc trick was already known to be unsound for the `\"`-heavy loop
# shape -- see _run_aw_sidecar_snippet's own docstring below -- so keeping
# it only for a RELAY_PIDFILE line that no longer has that simple shape
# would have pinned a snippet this file cannot reach in production).


# --- D1: the AW_PIDFILE polling loop that closes the fork/exec race --------


def _extract_aw_sidecar_snippet() -> str:
    """Pulls the ACTUAL AW_PIDFILE polling loop (Task 18b, D1) straight out
    of benchmarks/cells/tier4_autoware.sh by REGEX, from right after the
    `echo \\$! >$AW_PIDFILE` line through its closing `done` and, if present,
    the trailing `|| true` (fix round 1, F1 added it). The `|| true` is
    OPTIONAL in the pattern -- not because production ever omits it, but so
    that F1's own regression test (which reverts just that token to pin the
    fix) still gets a clean, runnable extraction ending in bare `done`
    instead of the pattern skipping past the missing anchor and running on
    into the NEXT `echo \\$! >$...` block (RELAY_PIDFILE's own, which also
    ends `done || true`): a non-greedy `.*?` with no such stop is happy to
    cross an intervening block boundary to find a LATER `done || true`,
    which happened during finalisation -- confirmed by extracting a ~6000-char
    snippet spanning both loops and failing with a bash syntax error
    (returncode 2, `unexpected EOF`) instead of the intended clean exit-status
    assertion. The `(?!echo \\\\\\$! >\\$)` negative lookahead below is the
    actual fix: it forbids the lazy `.*?` from stepping over another
    `echo \\$! >$...` line at all, so a missing `|| true` here can only ever
    be satisfied by THIS block's own `done`, never a neighbour's."""
    import re

    text = TIER4_CELL.read_text()
    pattern = re.compile(
        r"echo \\\$! >\$AW_PIDFILE\n"
        r"(  aw_cmd=(?:(?!echo \\\$! >\$).)*?\n  done(?: \|\| true)?)",
        re.DOTALL,
    )
    m = pattern.search(text)
    assert m, f"AW_PIDFILE sidecar polling loop not found in {TIER4_CELL}"
    return m.group(1)


def _run_aw_sidecar_snippet(
    snippet: str, pidfile: Path, env: dict | None = None, pidfile_var: str = "AW_PIDFILE"
) -> subprocess.CompletedProcess:
    """Runs the REAL AW_PIDFILE (or, with `pidfile_var="RELAY_PIDFILE"`, the
    real relay) polling loop through the same two bash parses it gets in
    production -- NOT via an UNQUOTED-heredoc trick (an earlier version of
    this helper set, removed once RELAY_PIDFILE stopped needing it
    separately), which is unsound for this loop shape.

    That trick relies on an unquoted heredoc reproducing real double-quote
    expansion, and it would for a snippet that never contains `\\"`, but an
    unquoted heredoc body only treats backslash as special before $, `` ` ``,
    \\ or a line-continuing newline -- `"` is NOT on that list, so `\\"`
    survives a heredoc UNCOLLAPSED (still `\\"`, two chars), whereas a REAL
    double-quoted argument (what `cx "$AW_ENV ..."` actually is) DOES
    collapse `\\"` to `"` (one char, the backslash consumed). Both loops are
    full of `\\"` (their own `\"$aw_cmd\"` / `\"$rel_cmd\"` guards), so the
    heredoc route would silently test different text than production runs --
    measured directly while building this fix (`\\"` came out as literal
    backslash-quote, not quote).

    So pass 1 here embeds the snippet as an ACTUAL double-quoted argument to
    a stub `cx()`, in a real script, executed by a real `bash -c` -- the same
    single parse the real `cx "$AW_ENV ..."` call gets in
    benchmarks/cells/tier4_autoware.sh. Pass 2 re-parses pass 1's output as a
    fresh `bash -c`, exactly the container-side parse `cx` triggers.

    `env`, when given, replaces pass 2's environment (e.g. to shadow `sleep`
    on PATH -- see the F1 regression test below). Pass 1 never needs it: it
    only expands host-side variables, it does not run any of the loop's own
    commands.
    """
    host_script = f'{pidfile_var}="{pidfile}"\ncx() {{ printf "%s" "$1"; }}\ncx "{snippet}"\n'
    host_pass = subprocess.run(
        ["bash", "-c", host_script], capture_output=True, text=True, timeout=10, check=False
    )
    assert host_pass.returncode == 0, host_pass.stderr
    return subprocess.run(
        ["bash", "-c", host_pass.stdout],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=env,
    )


def test_tier4_autoware_sh_aw_sidecar_settles_on_the_post_exec_cmdline(tmp_path):
    """D1's real-code-path pin, and the property the brief asks for: "a
    sidecar written by the real launcher line must equal what a later
    /proc/<pid>/cmdline read returns for a process that has exec'd." Runs
    the REAL AW_PIDFILE polling loop against a process that starts with one
    cmdline and execs into a different one 1.0s later -- comfortably inside
    the loop's 2s-steady/5s-bound design (verified separately up to ~2.9s of
    real delay) -- and checks the sidecar it writes is the process's TRUE
    final cmdline, not the transient one that existed when the loop started.

    Mutation-verified against the PRE-fix single-`tr`-read line (see the
    task report): that line reliably records the transient PRE-exec argv
    against this exact stand-in, which is the defect Task 18b measured live
    on 5/10 cell-B runs (results/B/run-017,019,020,021,022).

    Fix round 1, F2: the exec-really-happened guard used to be
    `assert "delayed_exec" not in expected` -- but "delayed_exec" never
    appears in ANY of this stub's cmdlines (it names the Python
    identifiers that build the source text, not text the source itself
    contains), so that assertion could not fail even if the stub silently
    stopped exec-ing, at which point the loop would settle on the STILL-
    pre-exec cmdline and `sidecar.read_text() == expected` would pass
    anyway -- the exact defect this test exists to catch, reproduced
    inside the test's own setup. Replaced with a check tied to content
    that is present before the exec and verifiably absent after it: the
    pre-exec argv is `[python3, "-c", <the stub's OWN source text>]`,
    which contains the literal string "os.execv" (the call the source
    makes); the post-exec argv is the FINAL stub's `import time; while
    True: ...` and cannot contain it. Captured before the loop even
    starts, independent of timing, so this cannot degrade into a
    tautology the way the string check did."""
    snippet = _extract_aw_sidecar_snippet()

    proc = _start_delayed_exec_stub(delay_s=1.0)
    try:
        pidfile = tmp_path / "AW_PIDFILE.pid"
        pre_exec = Path(f"/proc/{proc.pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        assert "os.execv" in pre_exec, "stub setup is broken -- this should be the PRE-exec argv"
        pidfile.write_text(str(proc.pid))
        result = _run_aw_sidecar_snippet(snippet, pidfile)
        assert result.returncode == 0, result.stderr

        # The loop itself already ran past the 1.0s delay (its own bound is
        # 5s), so the exec has already happened; this re-read is simply the
        # ground truth to compare the sidecar against.
        expected = Path(f"/proc/{proc.pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        assert "os.execv" not in expected, "the stub never exec'd -- test setup is broken"
        assert expected != pre_exec, "the stub never exec'd -- test setup is broken"

        sidecar = Path(f"{pidfile}.cmd")
        assert sidecar.exists(), "the loop never wrote the sidecar at all"
        assert sidecar.read_text() == expected
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


def test_tier4_autoware_sh_aw_sidecar_write_is_best_effort(tmp_path):
    """The sidecar write must never be allowed to fail the launch (brief D2,
    which D1's polling loop must still honour: "never allowed to fail the
    launch"). Run the REAL AW_PIDFILE loop against a pid whose
    /proc/<pid>/cmdline can never be read (the process is already gone), and
    check the loop's own exit status is still 0 and it leaves no sidecar --
    the safe "stays unwritten" outcome the brief requires at the bound, not
    a copy of the claim."""
    snippet = _extract_aw_sidecar_snippet()
    gone_pid = subprocess.Popen([sys.executable, "-c", "pass"])
    gone_pid.wait(timeout=5)
    assert not Path(f"/proc/{gone_pid.pid}").exists()

    pidfile = tmp_path / "gone.pid"
    pidfile.write_text(str(gone_pid.pid))
    result = _run_aw_sidecar_snippet(snippet, pidfile)

    assert result.returncode == 0, result.stderr
    assert not Path(f"{pidfile}.cmd").exists() or Path(f"{pidfile}.cmd").read_text() == ""


def test_tier4_autoware_sh_aw_sidecar_loop_status_never_leaks(tmp_path):
    """Fix round 1, F1's regression pin. `while ...; done` takes the exit
    status of the last BODY command it ran, and that command is `sleep 0.1`
    -- so before this fix, one failed fork on the loop's own last iteration
    (measured plausible: ~200 forks during the launch's own fork storm, on a
    host this campaign has recorded at loadavg 40-70) would have made the
    whole `cx "$AW_ENV ..."` call return non-zero and
    `fail_with_log "the Autoware launch could not be started"` fire -- on a
    launch that had actually succeeded. `done || true` is what prevents that.

    Shadows `sleep` on PATH with one that ALWAYS exits 1 (and does not
    actually sleep, so this test stays fast) and runs the REAL loop against
    an already-settled process. The write logic is unaffected -- a `while`
    loop's own exit status is only its LAST executed command's, so the
    fake failures do not stop the loop from reading, comparing or writing on
    any earlier iteration -- but without `done || true` the loop's own status
    (and therefore the whole snippet's) would be 1. Mutation-verified in the
    task report: reverting `done || true` to `done` makes this fail with
    `result.returncode == 1`."""
    snippet = _extract_aw_sidecar_snippet()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake_sleep = bindir / "sleep"
    fake_sleep.write_text("#!/usr/bin/env bash\nexit 1\n")
    fake_sleep.chmod(fake_sleep.stat().st_mode | 0o111)

    proc = _start_stub(tmp_path, "settled")
    try:
        pidfile = tmp_path / "AW_PIDFILE.pid"
        pidfile.write_text(str(proc.pid))
        env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
        result = _run_aw_sidecar_snippet(snippet, pidfile, env=env)

        assert result.returncode == 0, (
            "the loop's own exit status leaked through -- 'done || true' "
            f"is missing or broken: {result.stderr}"
        )
        # The fake `sleep` failing on every iteration must not have stopped
        # the loop from doing its actual job.
        expected = Path(f"/proc/{proc.pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        assert Path(f"{pidfile}.cmd").read_text() == expected
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


# --- F3 (fix round 1): the relay sidecar gets the same D1 mechanism --------


def _extract_relay_sidecar_snippet() -> str:
    """Pulls the ACTUAL RELAY_PIDFILE polling loop (fix round 1, F3) out of
    benchmarks/cells/tier4_autoware.sh by REGEX -- the same treatment
    _extract_aw_sidecar_snippet gives the AW_PIDFILE loop above, since F3
    applied that exact mechanism here too."""
    import re

    text = TIER4_CELL.read_text()
    pattern = re.compile(
        r"echo \\\$! >\$RELAY_PIDFILE\n(  rel_cmd=.*?\n  done \|\| true)", re.DOTALL
    )
    m = pattern.search(text)
    assert m, f"RELAY_PIDFILE sidecar polling loop not found in {TIER4_CELL}"
    return m.group(1)


def test_tier4_autoware_sh_relay_sidecar_settles_on_the_post_exec_cmdline(tmp_path):
    """F3's real-code-path pin, the RELAY_PIDFILE twin of
    test_tier4_autoware_sh_aw_sidecar_settles_on_the_post_exec_cmdline
    above: extracts the REAL relay polling loop and runs it against a
    process that execs into a different cmdline 1.0s later, checking the
    sidecar settles on the TRUE post-exec cmdline rather than the
    transient one -- the same property D1 established for AW_PIDFILE, now
    established for the sidecar F3 found still racing."""
    snippet = _extract_relay_sidecar_snippet()

    proc = _start_delayed_exec_stub(delay_s=1.0)
    try:
        pidfile = tmp_path / "RELAY_PIDFILE.pid"
        pidfile.write_text(str(proc.pid))
        result = _run_aw_sidecar_snippet(snippet, pidfile, pidfile_var="RELAY_PIDFILE")
        assert result.returncode == 0, result.stderr

        expected = Path(f"/proc/{proc.pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        assert "os.execv" not in expected, "the stub never exec'd -- test setup is broken"

        sidecar = Path(f"{pidfile}.cmd")
        assert sidecar.exists(), "the loop never wrote the sidecar at all"
        assert sidecar.read_text() == expected
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


# --- F5 (fix round 1): the extension-path AW_PIDFILE loop has no test ------


def _extract_launch_autoware_snippet(pidfile_var: str) -> str:
    """Pulls the ACTUAL polling loop for `pidfile_var` (AW_PIDFILE or
    RELAY_PIDFILE) out of scripts/e2e/launch_autoware.sh by REGEX. Fix
    round 1, F5: every prior D1 pin extracted from tier4_autoware.sh only;
    this covers the extension path's own copy of the same mechanism."""
    import re

    text = LAUNCH_AUTOWARE.read_text()
    if pidfile_var == "AW_PIDFILE":
        pattern = re.compile(r'(  aw_cmd="".*?\n  done)', re.DOTALL)
    elif pidfile_var == "RELAY_PIDFILE":
        pattern = re.compile(r'(        rel_cmd="".*?\n        done)', re.DOTALL)
    else:
        raise ValueError(pidfile_var)
    m = pattern.search(text)
    assert m, f"{pidfile_var} sidecar polling loop not found in {LAUNCH_AUTOWARE}"
    return m.group(1)


def _run_launch_autoware_snippet(
    snippet: str, pidfile_var: str, pidfile: Path
) -> subprocess.CompletedProcess:
    """Runs the REAL launch_autoware.sh polling loop as REAL bash -- a
    SINGLE parse, not tier4's two-pass. compose_exec's argument is
    SINGLE-quoted at the host level (`compose_exec '...'`), so unlike
    tier4's `cx "$AW_ENV ..."` (a HOST-side double-quoted string that the
    host itself partially expands before the container ever sees it),
    nothing here is expanded until the container's own `bash -lc` runs it
    -- $AW_PIDFILE / $RELAY_PIDFILE are supplied via `-e` (an environment
    variable), never a host-string substitution. So the faithful
    reproduction is exactly that: run the extracted text as-is, with
    `pidfile_var` set as a real environment variable, in ONE real bash
    parse -- no heredoc trick, no escaping pitfall, confirming F5's own
    claim that the single-quoted context makes this EASIER than tier4's."""
    env = {**os.environ, pidfile_var: str(pidfile)}
    return subprocess.run(
        ["bash", "-c", snippet], capture_output=True, text=True, timeout=15, env=env, check=False
    )


@pytest.mark.parametrize("pidfile_var", ["AW_PIDFILE", "RELAY_PIDFILE"])
def test_launch_autoware_sh_sidecar_settles_on_the_post_exec_cmdline(tmp_path, pidfile_var):
    """F5's real-code-path pin (and F3's completion for the relay half):
    extracts the REAL scripts/e2e/launch_autoware.sh polling loop for
    `pidfile_var` and runs it against a process that execs into a
    different cmdline 1.0s later, checking the sidecar settles on the TRUE
    post-exec cmdline. Before fix round 1 this extension-path loop was
    pinned only by a reviewer's one-off manual run; this makes it a real,
    repeatable, mutation-verifiable pin like tier4's."""
    snippet = _extract_launch_autoware_snippet(pidfile_var)

    proc = _start_delayed_exec_stub(delay_s=1.0)
    try:
        pidfile = tmp_path / f"{pidfile_var}.pid"
        pidfile.write_text(str(proc.pid))
        result = _run_launch_autoware_snippet(snippet, pidfile_var, pidfile)
        assert result.returncode == 0, result.stderr

        expected = Path(f"/proc/{proc.pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
        assert "os.execv" not in expected, "the stub never exec'd -- test setup is broken"

        sidecar = Path(f"{pidfile}.cmd")
        assert sidecar.exists(), "the loop never wrote the sidecar at all"
        assert sidecar.read_text() == expected
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


# --- Task 3 (P4 spec 1f): GT collector stops AFTER the observer -----------


def test_gt_collector_stops_after_the_observer():
    """README finding ("The static arm's windowed M2 reconciliation charges
    a teardown-ordering gap to the publisher", benchmarks/README.md :3793):
    `window.static_window` sets the window's upper bound to
    `clock_wall.max()` (the observer's LAST /clock sample, written by
    bench_observer, which flushes only once teardown SIGINTs it -- run.sh
    step 6's own comment: "teardown sends SIGINT, and only rclcpp's own
    handler makes spin() return so the CSV buffers flush"). The OLD order
    stopped the GT collector (writes publisher_counts.json) BEFORE that
    SIGINT, so the publisher series ended ~1.051 s before the window's top
    on `results/A/run-001`, fabricating `publisher_drop_rate = 0.0213` on a
    publisher that dropped nothing (984 expected, 963 published, 21-tick
    deficit; the predicted 21 equals the observed 21). Inherited by all ten
    P3 static pairs, cell A and cell B alike. The frozen analysis/window.py
    fix variant (clamp the window to `min(clock_wall.max(), publisher_end)`)
    is not available (analysis/** is frozen); reversing the two teardown
    stops is the registered smaller fix, and it does not re-break the flush
    ordering run.sh step 6 already paid for: `stop_container` still SIGINTs
    the observer and blocks (up to 15 s) until it exits before this test's
    GT-collector anchors may run, so nothing here skips the wait the README
    itself credits.

    The clock watchdog still stops FIRST -- its stall detection reads
    clock.csv growth (unaffected: growth already stopped once the run's own
    scoring window closed, well before teardown runs) -- and the resource
    sampler still stops LAST, so its own container cost is sampled right up
    to its shutdown.

    Anchor note: the originally-proposed pin compared
    `text.index("SIGINT") < text.index("benchmarks.scripts.collect_gt")`,
    but "SIGINT" is NOT unique in this file -- it also names the header's
    rationale prose (:11), `stop_container`'s own "SIGINT container" log
    line (:73), and the tier4-native case's ordering comments (:264, :267)
    -- and its FIRST occurrence is the :11 header comment, which sits above
    every stop call regardless of the real order below. That comparison
    would pass identically whether or not this fix was ever made -- a pin
    that passes for the wrong reason. Anchored instead on the literal,
    single-occurrence STATEMENTS themselves, with `.count(...) == 1`
    asserted for each so a future duplicate cannot silently defeat this pin.
    Source order is execution order for this stretch of teardown.sh: it is
    flat, unconditional bash (module load only sources launch.env/host_pids,
    no loop or function indirection reorders these calls at runtime)."""
    text = TEARDOWN.read_text()
    watchdog_stop = 'stop_pid "${WATCHDOG_PID:-}" "clock watchdog"'
    observer_stop = 'stop_container "$OBSERVER_CONTAINER"'
    gt_pid_stop = 'stop_pid "${GT_PID:-}" "gt collector"'
    gt_container_stop = "benchmarks.scripts.collect_gt"
    sampler_stop = 'stop_pid "${SAMPLER_PID:-}" "resource sampler"'
    for anchor in (watchdog_stop, observer_stop, gt_pid_stop, gt_container_stop, sampler_stop):
        assert text.count(anchor) == 1, f"anchor no longer unique, pin is unsound: {anchor!r}"

    assert text.index(watchdog_stop) < text.index(observer_stop), (
        "the clock watchdog must still stop FIRST -- its stall detection "
        "reads clock.csv growth, which only stops once the observer does"
    )
    # The property this task exists to establish: BOTH halves of "stop the
    # GT collector" (the host-side stop_pid that is the real kill for cells
    # A/B/B-cyc, where GT_OUT_DIR != "/out" so the pkill fallback below never
    # fires; and the container-side pkill fallback that is the real kill for
    # bridge cells, where GT_OUT_DIR == "/out") now sit AFTER the observer's
    # SIGINT+flush wait, not before it.
    assert text.index(observer_stop) < text.index(gt_pid_stop), (
        "GT_PID must stop AFTER the observer -- moving it back before the "
        "observer reintroduces the README's fabricated publisher_drop_rate"
    )
    assert text.index(observer_stop) < text.index(gt_container_stop), (
        "the container-side collect_gt pkill fallback must also stop AFTER "
        "the observer, for the same reason"
    )
    assert text.index(gt_pid_stop) < text.index(sampler_stop), (
        "the resource sampler must still stop LAST"
    )
    assert text.index(gt_container_stop) < text.index(sampler_stop), (
        "the resource sampler must still stop LAST"
    )


def test_launch_autoware_sh_sidecar_write_is_best_effort(tmp_path):
    """launch_autoware.sh's own best-effort pin, matching D2's requirement
    ("never allowed to fail the launch") the way
    test_tier4_autoware_sh_aw_sidecar_write_is_best_effort already does for
    the tier4 side. Runs the REAL AW_PIDFILE loop against a pid that is
    already gone: exit 0, no (or empty) sidecar."""
    snippet = _extract_launch_autoware_snippet("AW_PIDFILE")
    gone_pid = subprocess.Popen([sys.executable, "-c", "pass"])
    gone_pid.wait(timeout=5)
    assert not Path(f"/proc/{gone_pid.pid}").exists()

    pidfile = tmp_path / "gone.pid"
    pidfile.write_text(str(gone_pid.pid))
    result = _run_launch_autoware_snippet(snippet, "AW_PIDFILE", pidfile)

    assert result.returncode == 0, result.stderr
    assert not Path(f"{pidfile}.cmd").exists() or Path(f"{pidfile}.cmd").read_text() == ""
