"""Pins for the `/map/vector_map` re-publish + delivery gate (Task 4b/5).

Two things need pinning and they need pinning DIFFERENTLY.

1. The decision logic in `benchmarks/injector/republish_vector_map.py` -- what
   counts as "the monitor says the map arrived" and what counts as "our
   publisher has matched a settled set of readers". Both are named predicates
   rather than inline conditions precisely so they can be tested without a live
   stack, the same reason `seed_localization.converged` exists. rclpy and the
   Autoware message packages are stubbed exactly as
   tests/benchmarks/test_seed_localization.py stubs them.

2. The WIRING in `benchmarks/cells/tier4_autoware.sh` -- that the step runs on
   the closed-loop arm and NOT on the static one. This campaign has a binding
   rule that a substring/text-scan assertion is not a pin (six prior
   violations), so the tests below extract the REAL gating block out of the
   REAL launcher and EXECUTE it in bash, with stand-in `cx` / `fail_with_log`
   shell functions that leave real files behind. What is asserted is an effect
   that can only happen if the wiring actually fired -- a recorder file that
   exists or does not exist, and its real contents -- never a string appearing
   in source text.

   WHY THE STATIC HALF IS A SAFETY PROPERTY AND NOT A PREFERENCE: cell B's
   fifteen filed static runs ARE the static verdict pool, and branch (c)
   forbids recollecting them. A step that leaked into the static bring-up would
   silently make every future static run non-comparable with them, and nothing
   else in the harness would notice.

   WHAT THESE TESTS DO NOT SHOW: that the re-publish actually fixes delivery to
   `behavior_path_planner`. There is no container, no DDS and no Autoware here.
   That question is answered only by live closed-loop runs, and the honest
   limit is recorded in the injector's own docstring and in
   benchmarks/evidence/b-vector-map-delivery/.
"""

from __future__ import annotations

import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TIER4_CELL = REPO / "benchmarks" / "cells" / "tier4_autoware.sh"


class _StubModule(types.ModuleType):
    """Yields a fresh empty class for any attribute, so `from x import Y`
    works without the real package (matches test_seed_localization.py)."""

    def __getattr__(self, name: str):
        return type(name, (), {})


for _name in (
    "rclpy",
    "rclpy.node",
    "rclpy.qos",
    "autoware_map_msgs",
    "autoware_map_msgs.msg",
    "diagnostic_msgs",
    "diagnostic_msgs.msg",
):
    sys.modules.setdefault(_name, _StubModule(_name))

from benchmarks.injector.republish_vector_map import (  # noqa: E402
    EXIT_NOT_VERIFIED,
    EXIT_NO_CAPTURE,
    EXIT_NO_MATCH,
    EXIT_OK,
    build_arg_parser,
    diag_level,
    matching_settled,
    status_reports_delivered,
)

# ---------------------------------------------------------------------------
# 1. the decision logic
# ---------------------------------------------------------------------------


def test_level_ok_without_a_status_key_is_not_delivered():
    """THE measured trap. `topic_state_monitor_vector_map` publishes one
    initial status with level OK and NO key/value pairs, ~0.2 s into bring-up,
    immediately before its first real check reports ERROR/NotReceived -- seen
    on both replica bring-ups (`level=OK status=None`, then `level=ERROR
    status=NotReceived` 0.18 s and 0.61 s later). A gate keyed on level alone
    would pass instantly on EVERY run, including the two of six that never
    delivered the map at all, and would have certified exactly the failure it
    exists to catch."""
    assert status_reports_delivered(0, {}) is False


def test_level_ok_with_status_ok_is_delivered():
    assert status_reports_delivered(0, {"status": "OK"}) is True


def test_error_with_not_received_is_not_delivered():
    assert status_reports_delivered(2, {"status": "NotReceived"}) is False


def test_level_accepts_the_bytes_form_rclpy_actually_hands_back():
    """`DiagnosticStatus.level` came back as `bytes` from a live rclpy
    subscriber on this image (`level=b'\\x02'`) and as `int` elsewhere. A gate
    that only understood one form would either never pass or always pass."""
    assert diag_level(b"\x00") == 0
    assert diag_level(b"\x02") == 2
    assert diag_level(0) == 0
    assert status_reports_delivered(b"\x00", {"status": "OK"}) is True
    assert status_reports_delivered(b"\x02", {"status": "NotReceived"}) is False


def test_zero_subscribers_is_never_settled():
    """Publishing into an empty matched set would emit the sample into nothing
    and then gate on a monitor that never received it -- turning a transport
    defect into a bring-up failure that names the wrong thing."""
    assert matching_settled([(0.0, 0), (5.0, 0), (10.0, 0)], settle_s=5.0) is False


def test_count_must_hold_steady_for_the_whole_settle_window():
    assert matching_settled([(0.0, 3), (4.9, 3)], settle_s=5.0) is False
    assert matching_settled([(0.0, 3), (5.0, 3)], settle_s=5.0) is True


def test_a_count_still_climbing_is_not_settled():
    """Discovery converges at wildly different speeds here -- 16 subscription
    endpoints were enumerated on one bring-up and 3 on another, both healthy --
    so "still moving" is the only usable signal that matching is incomplete."""
    assert matching_settled([(0.0, 1), (3.0, 2), (7.0, 3)], settle_s=5.0) is False


def test_exit_codes_are_distinct_so_a_failure_names_which_half_broke():
    codes = [EXIT_OK, EXIT_NO_CAPTURE, EXIT_NO_MATCH, EXIT_NOT_VERIFIED]
    assert len(set(codes)) == len(codes)


def test_cli_defaults_are_the_ones_the_launcher_relies_on():
    args = build_arg_parser().parse_args([])
    assert args.topic == "/map/vector_map"
    assert args.attempts >= 1
    assert args.settle_s > 0
    assert args.verify_timeout_s > 0


# ---------------------------------------------------------------------------
# 2. the wiring, executed for real
# ---------------------------------------------------------------------------


def _gating_block() -> str:
    """Extract the REAL closed-loop gating block from the REAL launcher.

    Anchored on the `if` condition itself and closed on a column-0 `fi`, so it
    cannot silently pick up a neighbouring block. Exactly one match is required
    -- a second `BENCH_ARM` gate appearing later would make "the" block
    ambiguous and these tests would then be pinning an arbitrary one of them.
    """
    text = TIER4_CELL.read_text()
    pattern = re.compile(
        r'^(if \[ "\$\{BENCH_ARM:-\}" = "closed-loop" \]; then\n.*?^fi$)',
        re.DOTALL | re.MULTILINE,
    )
    matches = pattern.findall(text)
    assert len(matches) == 1, (
        f"expected exactly one BENCH_ARM closed-loop gate in {TIER4_CELL}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _run_gate(tmp_path: Path, arm: str, cx_exit: int = 0) -> subprocess.CompletedProcess:
    """Run the real gating block with recorder stand-ins for `cx` and
    `fail_with_log`. Both leave real files behind, so every assertion below is
    about something that happened, not something that was written."""
    script = tmp_path / "gate.sh"
    block = _gating_block()
    script.write_text(
        "set -euo pipefail\n"
        f'BENCH_ARM="{arm}"\n'
        'AW_ENV="source /opt/ros/humble/setup.bash"\n'
        f'CX_LOG="{tmp_path}/cx.log"\n'
        f'FAIL_LOG="{tmp_path}/fail.log"\n'
        'cx() { printf "%s\\n" "$1" >>"$CX_LOG"; return ' + str(cx_exit) + "; }\n"
        'fail_with_log() { printf "%s\\n" "$*" >>"$FAIL_LOG"; exit 2; }\n'
        + block
        + "\n"
    )
    return subprocess.run(
        ["bash", str(script)], capture_output=True, text=True, timeout=30
    )


def test_static_arm_runs_no_extra_step_at_all(tmp_path: Path):
    """The safety property. Cell B's static bring-up must stay behaviourally
    byte-identical, because its fifteen filed runs are the static verdict pool
    and branch (c) forbids recollecting them. Asserted by the recorder file
    NOT EXISTING -- i.e. the block genuinely never reached a `cx` call, rather
    than reaching one that happened to be harmless."""
    proc = _run_gate(tmp_path, arm="static")
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "cx.log").exists(), (
        "the static arm executed a container command: " + proc.stdout
    )
    assert not (tmp_path / "fail.log").exists()


def test_closed_loop_arm_invokes_the_republisher_once(tmp_path: Path):
    proc = _run_gate(tmp_path, arm="closed-loop")
    assert proc.returncode == 0, proc.stderr
    cx_log = (tmp_path / "cx.log").read_text()
    assert cx_log.count("republish_vector_map.py") == 1, cx_log
    assert "/work/benchmarks/injector/republish_vector_map.py" in cx_log
    assert not (tmp_path / "fail.log").exists()


def test_the_report_lands_in_the_run_directory(tmp_path: Path):
    """`/out` is the run directory bind-mount, so the per-run pre-state and
    verification record become filed evidence rather than terminal output --
    the exact gap 7.6 recorded for the python-bridge GT anchor, which produced
    a real observation that no filed artifact could back."""
    _run_gate(tmp_path, arm="closed-loop")
    assert "--report /out/" in (tmp_path / "cx.log").read_text()


def test_a_failing_gate_fails_the_bring_up_loudly(tmp_path: Path):
    """A silent pass here would put the campaign straight back where it started
    -- thirteen closed-loop attempts with no named failing link."""
    proc = _run_gate(tmp_path, arm="closed-loop", cx_exit=1)
    assert proc.returncode != 0
    fail_text = (tmp_path / "fail.log").read_text()
    assert "vector_map" in fail_text
    assert "republish_vector_map" in fail_text or "delivery" in fail_text


@pytest.mark.parametrize("arm", ["static", "closed-loop"])
def test_the_block_is_syntactically_whole(tmp_path: Path, arm: str):
    """Guards the extraction itself: a regex that clipped the block short would
    otherwise surface as a confusing assertion failure elsewhere. A bash syntax
    error returns 2 with `unexpected EOF`, which is exactly how the analogous
    pin in test_teardown.py was found to be extracting a truncated snippet."""
    proc = _run_gate(tmp_path, arm=arm)
    assert "syntax error" not in proc.stderr, proc.stderr
    assert "unexpected EOF" not in proc.stderr, proc.stderr
