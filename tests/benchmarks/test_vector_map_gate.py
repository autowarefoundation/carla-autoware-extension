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

   WHY THE STATIC HALF IS A SAFETY PROPERTY AND NOT A PREFERENCE: cell B has
   17 non-excluded static runs, of which 10 (`run-013`..`run-022`) are the
   DUEL-ADMISSIBLE pool the A-vs-B static verdict is computed from; 0 statics
   are excluded. All 17 were measured WITHOUT this step, and branch (c) forbids
   recollecting them. A step that leaked into the static bring-up would silently
   make every future static run non-comparable with them, and nothing else in
   the harness would notice. (Counts recomputed from every manifest,
   2026-08-01; an earlier revision said "fifteen", which is none of the three.)

   WHAT THESE TESTS DO NOT SHOW: that the re-publish actually fixes delivery to
   `behavior_path_planner`. There is no container, no DDS and no Autoware here.
   That question is answered only by live closed-loop runs, and the honest
   limit is recorded in the injector's own docstring and in
   benchmarks/evidence/b-vector-map-delivery/.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TIER4_CELL = REPO / "benchmarks" / "cells" / "tier4_autoware.sh"

# Text unique to ONE branch of the launcher's advisory if/else. Named
# constants rather than inline literals because four tests below depend on
# their branch-uniqueness, and a literal repeated four times is exactly how
# that property gets broken silently.
#
# Each must be contiguous on a SINGLE source line as well as present in
# stdout, because the assertions run against both: the launcher's echoes are
# split across continuation lines, so a phrase that spans two of them (e.g.
# "did not complete cleanly", which the shell joins but the file does not
# contain) matches the run and silently never matches the source.
RAN_BRANCH_MARKER = "RAN AND RECORDED A VERDICT"
FAILED_BRANCH_MARKER = "step did not complete"


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

from benchmarks.injector import republish_vector_map as rvm  # noqa: E402
from benchmarks.injector.republish_vector_map import (  # noqa: E402
    EXIT_CRASHED,
    EXIT_NOT_VERIFIED,
    EXIT_NO_CAPTURE,
    EXIT_NO_MATCH,
    EXIT_OK,
    RELOG_MARKERS,
    build_arg_parser,
    count_relog_markers,
    diag_level,
    matching_settled,
    relog_shows_delivery,
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


# --- the second delivery oracle, added after run-031 refuted the first ------


def test_relog_markers_are_the_two_nodes_that_re_log_on_receipt():
    """`lanelet2_map_visualization` and `vector_map_tf_generator` each print a
    line every time they receive a vector map. They live in a DIFFERENT process
    from the re-publisher, so a fresh line is proof of INTER-PROCESS receipt --
    which is exactly what `topic_state_monitor_vector_map` failed to give on
    B/run-031 while these two logged all three re-publications."""
    assert any("lanelet2_map_visualization" in m for m in RELOG_MARKERS)
    assert any("vector_map_tf_generator" in m for m in RELOG_MARKERS)


def test_counting_relog_markers_is_per_marker():
    text = (
        "[component_container_mt-15] [map.lanelet2_map_visualization]: Map is loaded\n"
        "[component_container_mt-15] [map.vector_map_tf_generator]: broadcast static tf. x:1\n"
        "[component_container_mt-15] [map.lanelet2_map_visualization]: Map is loaded\n"
        "unrelated line\n"
    )
    counts = count_relog_markers(text)
    assert counts["lanelet2_map_visualization]: Map is loaded"] == 2
    assert counts["vector_map_tf_generator]: broadcast static tf"] == 1


def test_a_fresh_relog_line_on_either_node_is_delivery():
    before = {m: 1 for m in RELOG_MARKERS}
    after = dict(before)
    after[RELOG_MARKERS[0]] = 2
    assert relog_shows_delivery(before, after) is True


def test_no_new_relog_line_is_not_delivery():
    """The measured shape of a re-publication that went nowhere. Counting
    ABSOLUTE occurrences instead of the delta would report delivery on every
    run, because map_loader's own original publication always logs once."""
    before = {m: 1 for m in RELOG_MARKERS}
    assert relog_shows_delivery(before, dict(before)) is False


def test_a_missing_launch_log_reads_as_no_evidence_not_as_delivery():
    """If the log cannot be read the counts come back empty. That must not
    silently satisfy the oracle -- an unreadable log is an absence of evidence,
    and this campaign's rule is that absence never reads as a pass."""
    assert relog_shows_delivery({}, {}) is False


def test_exit_codes_match_the_numbers_the_launcher_tells_the_operator():
    """`cells/tier4_autoware.sh`'s advisory message tells a reader to key off
    these numbers -- "exit 3 the capture, 4 the publisher matching, 5 the
    verification". Asserting only that four constants differ would pass while
    the code and that message drifted apart, which is the failure this pins.

    They live in the step-RAN branch, not the step-FAILED one: under
    `--advisory` every one of these verdicts exits 0, so the RAN branch is the
    only place a reader can ever meet them (see
    `test_the_failure_branch_does_not_claim_verdicts_that_cannot_reach_it`)."""
    assert (EXIT_OK, EXIT_NO_CAPTURE, EXIT_NO_MATCH, EXIT_NOT_VERIFIED) == (0, 3, 4, 5)
    launcher = TIER4_CELL.read_text()
    assert "exit 3 the" in launcher and "4 the publisher matching" in launcher
    assert "5 the" in launcher


def test_the_parser_accepts_the_launcher_s_real_flags_with_the_real_values():
    """Parsed out of the REAL call site rather than restated. `--attempts 3` in
    particular is load-bearing and measured: on the replica smoke the monitor
    only flipped on the THIRD publication, so a drift to 1 would silently make
    the step weaker than the evidence it rests on."""
    block = _gating_block()
    flags = re.search(r"republish_vector_map\.py(.*?)\"", block, re.DOTALL).group(1)
    argv = [w for w in flags.replace("\\\n", " ").split() if w != "\\"]
    argv = [w.replace("$AW_LOG", "/tmp/tier4-autoware.log") for w in argv]
    args = build_arg_parser().parse_args(argv)
    assert args.attempts == 3
    assert args.settle_s == 5
    assert args.verify_timeout_s == 60
    assert args.advisory is True
    assert args.topic == "/map/vector_map"
    assert args.launch_log == "/tmp/tier4-autoware.log"
    assert args.report.startswith("/out/")


def test_advisory_is_opt_in_on_the_cli_and_the_launcher_opts_in():
    """The node keeps its real verdict in the report either way; --advisory
    only decides whether that verdict reaches the caller as an exit status.
    Default off so the node stays usable as a gate if anyone ever wants one."""
    assert build_arg_parser().parse_args([]).advisory is False
    assert build_arg_parser().parse_args(["--advisory"]).advisory is True


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
        f"expected exactly one BENCH_ARM closed-loop gate in {TIER4_CELL}, found {len(matches)}"
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
        "AW_LOG=/tmp/tier4-autoware.log\n"
        f'BENCH_RUN_DIR="{tmp_path}"\n'
        f'CX_LOG="{tmp_path}/cx.log"\n'
        f'FAIL_LOG="{tmp_path}/fail.log"\n'
        'cx() { printf "%s\\n" "$1" >>"$CX_LOG"; return ' + str(cx_exit) + "; }\n"
        'fail_with_log() { printf "%s\\n" "$*" >>"$FAIL_LOG"; exit 2; }\n' + block + "\n"
    )
    return subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30)


def test_static_arm_runs_no_extra_step_at_all(tmp_path: Path):
    """The safety property. Cell B's static bring-up must stay behaviourally
    byte-identical, because its 17 non-excluded static runs -- 10 of them
    (`run-013`..`run-022`) the duel-admissible verdict pool -- were all measured
    without this step and branch (c) forbids recollecting them. Asserted by the
    recorder file
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


def test_the_step_is_advisory_and_never_aborts_the_run(tmp_path: Path):
    """THE property this test file exists to protect, after B/run-031.

    The step was originally fatal. run-031 aborted on it -- and its own launch
    log then showed the re-published map being delivered to
    lanelet2_map_visualization and vector_map_tf_generator on all three
    attempts, while the endpoint the gate read received none of them. A fatal
    gate keyed on that endpoint therefore converted a possibly-armable run into
    a crash:cell-launch and left the real question (does the PLANNER have the
    map) untested, because it fires before a route exists.

    The campaign's pass criteria are the arm succeeding and control_cmd
    flowing. This step is an added precondition that is not one of them, so it
    records and continues. If the map genuinely never reaches the planner the
    run still fails -- at the arm, loudly, and more informatively."""
    proc = _run_gate(tmp_path, arm="closed-loop", cx_exit=1)
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "fail.log").exists(), (
        "the delivery step aborted the bring-up: " + (tmp_path / "fail.log").read_text()
    )
    # Keyed on text unique to the ELSE branch. An earlier version asserted
    # `"ADVISORY" in proc.stdout`, which the UNCONDITIONAL pre-branch echo
    # ("... (ADVISORY -- never aborts)") already satisfies -- so deleting the
    # whole if/else body left it green. Same for the happy-path test below and
    # its `"/map/vector_map"`. Both now assert their own branch's marker AND
    # the ABSENCE of the other's, so one message that tries to serve both
    # cannot satisfy either test.
    assert FAILED_BRANCH_MARKER in proc.stdout, proc.stdout
    assert RAN_BRANCH_MARKER not in proc.stdout, proc.stdout


def test_the_advisory_outcome_is_still_announced_on_the_happy_path(tmp_path: Path):
    """And it announces RAN, not VERIFIED.

    Under `--advisory` the node returns EXIT_OK for verdicts 0, 3, 4 and 5
    alike, so reaching this branch says only that the process wrote a report --
    a run whose capture never happened (EXIT_NO_CAPTURE) lands here too. The
    message must send the reader to `verdict_code` rather than read as success,
    which is what these assertions pin."""
    proc = _run_gate(tmp_path, arm="closed-loop", cx_exit=0)
    assert proc.returncode == 0, proc.stderr
    assert RAN_BRANCH_MARKER in proc.stdout, proc.stdout
    assert FAILED_BRANCH_MARKER not in proc.stdout, proc.stdout
    assert "verdict_code" in proc.stdout, proc.stdout


def test_neither_branch_marker_is_printed_before_the_branch(tmp_path: Path):
    """The reason the two tests above can be trusted at all.

    Both markers must live INSIDE their branch. If either ever migrated into
    the unconditional echo that precedes the `if`, both tests above would pass
    on a launcher whose entire if/else body had been deleted -- which is
    exactly the hole this file used to have. Asserted against the launcher
    text, not a run, so it catches the migration at its source."""
    block = _gating_block()
    preamble = block.split("if cx ", 1)[0]
    assert RAN_BRANCH_MARKER not in preamble, preamble
    assert FAILED_BRANCH_MARKER not in preamble, preamble
    assert block.count(RAN_BRANCH_MARKER) == 1
    assert block.count(FAILED_BRANCH_MARKER) == 1


def test_the_failure_branch_does_not_claim_verdicts_that_cannot_reach_it(tmp_path: Path):
    """With `--advisory`, `_finish` returns EXIT_OK for EVERY verdict it can
    reach (0/3/4/5), so the shell's else branch is the PROCESS failing, not a
    non-verified verdict. An earlier revision of that message enumerated
    "exit 3 the capture, 4 the publisher matching, 5 the verification" as
    things a reader might see there; none of them can occur. The numbers now
    live in the branch that actually reports them."""
    block = _gating_block()
    ran_branch, failed_branch = block.split("  else\n", 1)
    assert "exit 3 the" in ran_branch and "4 the publisher matching" in ran_branch
    assert "exit 3 the" not in failed_branch
    assert "NOT verdict_code 3/4/5" in failed_branch


def test_the_launcher_asks_for_advisory_mode_explicitly(tmp_path: Path):
    """The shell DOES read the exit status -- `if cx ...; then ... else ... fi`
    -- it just branches on it instead of aborting. Passing --advisory as well
    means the node returns 0 on a failed verification, so neither half depends
    on the other being right."""
    _run_gate(tmp_path, arm="closed-loop")
    assert "--advisory" in (tmp_path / "cx.log").read_text()


@pytest.mark.parametrize("arm", ["static", "closed-loop"])
def test_the_block_is_syntactically_whole(tmp_path: Path, arm: str):
    """Guards the extraction itself: a regex that clipped the block short would
    otherwise surface as a confusing assertion failure elsewhere. A bash syntax
    error returns 2 with `unexpected EOF`, which is exactly how the analogous
    pin in test_teardown.py was found to be extracting a truncated snippet."""
    proc = _run_gate(tmp_path, arm=arm)
    assert "syntax error" not in proc.stderr, proc.stderr
    assert "unexpected EOF" not in proc.stderr, proc.stderr


# ---------------------------------------------------------------------------
# 3. the registered-transport refusal, and its deliberate-deviation opt-in
# ---------------------------------------------------------------------------
#
# cells/tier4_autoware.sh refuses any middleware but the pair Task 9 measured
# (`--rmw rmw_fastrtps_cpp` + `observer/config/udp_only.xml`), because with any
# other one the fork's topics are invisible to the stack and its control input
# is undeliverable -- matrix rows 5 and 10 in
# benchmarks/patches/tier4-native/README.md. That refusal is a safety backstop
# and must keep firing.
#
# Task 5's owner ruling needs ONE deliberate deviation run on cyclonedds to
# bound whether the latched-delivery defect is Fast-DDS-specific. The opt-in
# below exists for exactly that, and these tests pin both halves: the refusal
# still fires by default, and the opt-in is impossible to trip by accident.


def _refusal_block() -> str:
    text = TIER4_CELL.read_text()
    pattern = re.compile(
        r"^(# --- BEGIN registered-transport refusal.*?^# --- END registered-transport refusal[^\n]*$)",
        re.DOTALL | re.MULTILINE,
    )
    matches = pattern.findall(text)
    assert len(matches) == 1, (
        f"expected exactly one registered-transport refusal block in {TIER4_CELL}, "
        f"found {len(matches)}"
    )
    return matches[0]


def _run_refusal(tmp_path: Path, rmw: str, profile: str, deviation: str | None):
    script = tmp_path / "refusal.sh"
    dev = f'BENCH_TIER4_TRANSPORT_DEVIATION="{deviation}"\n' if deviation is not None else ""
    script.write_text(
        "set -euo pipefail\n"
        f'BENCH_CELL=B\nBENCH_RMW="{rmw}"\nBENCH_DDS_PROFILE="{profile}"\n'
        f'UDP_ONLY="/repo/benchmarks/observer/config/udp_only.xml"\n'
        + dev
        + f'fail() {{ printf "%s\\n" "$*" >>"{tmp_path}/fail.log"; exit 2; }}\n'
        + _refusal_block()
        + "\n"
    )
    return subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30)


REGISTERED = "/repo/benchmarks/observer/config/udp_only.xml"


def test_the_registered_pair_passes_the_refusal(tmp_path: Path):
    proc = _run_refusal(tmp_path, "rmw_fastrtps_cpp", REGISTERED, None)
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "fail.log").exists()


def test_a_wrong_middleware_still_fails_loudly(tmp_path: Path):
    """The backstop Task 9 put there. Without it a cyclonedds cell-B run comes
    up, localizes off nothing, and measures a vehicle under no command -- all
    silently, with every endpoint matched."""
    proc = _run_refusal(tmp_path, "rmw_cyclonedds_cpp", "none", None)
    assert proc.returncode != 0
    assert "rmw_fastrtps_cpp" in (tmp_path / "fail.log").read_text()


def test_a_wrong_profile_still_fails_loudly(tmp_path: Path):
    proc = _run_refusal(tmp_path, "rmw_fastrtps_cpp", "none", None)
    assert proc.returncode != 0
    assert "udp_only" in (tmp_path / "fail.log").read_text()


def test_the_deviation_opt_in_allows_it_and_says_so(tmp_path: Path):
    """One deliberate deviation run is what Task 5's ruling needs. It must be
    impossible to reach by accident, so it is keyed on an environment variable
    that carries its own REASON string -- not a flag, and not a default."""
    proc = _run_refusal(tmp_path, "rmw_cyclonedds_cpp", "none", "task5 cyclonedds bounding probe")
    assert proc.returncode == 0, proc.stderr
    assert not (tmp_path / "fail.log").exists()
    assert "DEVIATION" in proc.stdout, proc.stdout
    assert "task5 cyclonedds bounding probe" in proc.stdout, proc.stdout


def test_an_empty_deviation_reason_does_not_unlock_it(tmp_path: Path):
    """An empty string is what an unset-but-exported variable looks like. It
    must not count as a registered reason."""
    proc = _run_refusal(tmp_path, "rmw_cyclonedds_cpp", "none", "")
    assert proc.returncode != 0
    assert (tmp_path / "fail.log").exists()


# ---------------------------------------------------------------------------
# 4. TRANSPORT_ARGS -- the only new code on the REGISTERED path
# ---------------------------------------------------------------------------
#
# Byte-identity of the `docker run` transport expansion is the property the
# whole comparability argument rests on: every filed cell-B run was measured
# with `-e RMW_IMPLEMENTATION=rmw_fastrtps_cpp
# -e FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml
# -v <udp_only.xml>:/dds-profile.xml:ro`, and if a future edit to the
# rmw_fastrtps_cpp case arm changed that, every subsequent registered run would
# quietly stop being comparable with them and nothing would fail. The array was
# introduced so a registered DEVIATION probe gets the middleware it asked for
# instead of a manifest that claims one thing while the container runs another
# -- which means the registered path must be provably untouched by it.
#
# Executed for real, like the other blocks here: the array is extracted from the
# launcher and expanded by bash, and the assertion is on the resulting WORDS.


def _transport_block() -> str:
    text = TIER4_CELL.read_text()
    pattern = re.compile(
        r"^(TRANSPORT_ARGS=\(.*?^esac$)",
        re.DOTALL | re.MULTILINE,
    )
    matches = pattern.findall(text)
    assert len(matches) == 1, (
        f"expected exactly one TRANSPORT_ARGS block in {TIER4_CELL}, found {len(matches)}"
    )
    return matches[0]


def _expand_transport(tmp_path: Path, rmw: str | None, profile: str | None) -> list[str]:
    """Expand the REAL array under bash and return the words it produces."""
    script = tmp_path / "transport.sh"
    env = ""
    if rmw is not None:
        env += f'BENCH_RMW="{rmw}"\n'
    if profile is not None:
        env += f'BENCH_DDS_PROFILE="{profile}"\n'
    script.write_text(
        "set -euo pipefail\n"
        'UDP_ONLY="/repo/benchmarks/observer/config/udp_only.xml"\n'
        + env
        + _transport_block()
        + '\nprintf "%s\\n" "${TRANSPORT_ARGS[@]}"\n'
    )
    proc = subprocess.run(["bash", str(script)], capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.split("\n")[:-1]


REGISTERED_PROFILE = "/repo/benchmarks/observer/config/udp_only.xml"
REGISTERED_EXPANSION = [
    "-e",
    "RMW_IMPLEMENTATION=rmw_fastrtps_cpp",
    "-e",
    "FASTRTPS_DEFAULT_PROFILES_FILE=/dds-profile.xml",
    "-v",
    "/repo/benchmarks/observer/config/udp_only.xml:/dds-profile.xml:ro",
]


def test_the_registered_pair_expands_byte_identically(tmp_path: Path):
    """THE comparability pin. These exact words are what every filed cell-B run
    was measured under; if this list ever needs updating, every filed B run has
    stopped being comparable with every future one and that is a campaign-level
    decision, not a refactor."""
    assert _expand_transport(tmp_path, "rmw_fastrtps_cpp", REGISTERED_PROFILE) == (
        REGISTERED_EXPANSION
    )


def test_an_unset_transport_still_expands_to_the_registered_pair(tmp_path: Path):
    """The refusal block guarantees BENCH_RMW is set on every real run, but the
    array carries its own defaults and they must not disagree with it -- a
    disagreement would only ever surface as a silently mis-measured run."""
    assert _expand_transport(tmp_path, None, None) == REGISTERED_EXPANSION


def test_cyclonedds_with_no_profile_mounts_nothing(tmp_path: Path):
    """What B/run-033 actually ran. `udp_only.xml` is a FAST-DDS profile: under
    cyclonedds it must not be mounted and must not be referenced, or the record
    of what that probe measured would be wrong."""
    words = _expand_transport(tmp_path, "rmw_cyclonedds_cpp", "none")
    assert words == ["-e", "RMW_IMPLEMENTATION=rmw_cyclonedds_cpp"]
    assert not any("dds-profile" in w for w in words)
    assert not any("udp_only" in w for w in words)


def test_cyclonedds_with_a_profile_mounts_it_as_cyclonedds_uri(tmp_path: Path):
    words = _expand_transport(tmp_path, "rmw_cyclonedds_cpp", "/repo/docker/cyclonedds.xml")
    assert words == [
        "-e",
        "RMW_IMPLEMENTATION=rmw_cyclonedds_cpp",
        "-e",
        "CYCLONEDDS_URI=file:///dds-profile.xml",
        "-v",
        "/repo/docker/cyclonedds.xml:/dds-profile.xml:ro",
    ]
    assert not any("FASTRTPS" in w for w in words)


# ---------------------------------------------------------------------------
# 5. the crash report must never destroy a real one
#
# `_cli` wraps the WHOLE call in `except BaseException` and hands the exception
# to `_write_crash_report`. That helper's docstring assumed "a crash before
# `_finish`" -- but `_finish` does three more things AFTER its report reaches
# disk (a print, `destroy_node`, `rclpy.shutdown`), and a failure in any of
# them used to land in exactly the same handler and overwrite the finished
# report with `{"crashed": true, "verified": false, ...}`. That stub is
# indistinguishable from a step that never ran, on the one artifact the run
# exists to produce. These tests pin the guard and, equally, pin that the
# original behaviour survives everywhere it was right.
# ---------------------------------------------------------------------------


class _FakeNode:
    def __init__(self) -> None:
        self.destroyed = False

    def monitor_snapshot(self) -> dict:
        return {"level": "OK"}

    def destroy_node(self) -> None:
        self.destroyed = True


def _finish_args(tmp_path: Path, *, advisory: bool = True):
    args = build_arg_parser().parse_args(
        [
            "--advisory" if advisory else "--attempts",
            *([] if advisory else ["3"]),
            "--report",
            str(tmp_path / "vector-map-delivery.json"),
            "--launch-log",
            str(tmp_path / "launch.log"),
        ]
    )
    (tmp_path / "launch.log").write_text("")
    return args


def test_a_report_that_reached_disk_is_never_overwritten_by_the_crash_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """THE regression. `_finish` completes its write, then `rclpy.shutdown()`
    raises on the way out -- a real possibility on a stack being torn down.
    The verdict must survive."""
    args = _finish_args(tmp_path)
    boom = RuntimeError("shutdown raced teardown")

    def _raise() -> None:
        raise boom

    monkeypatch.setattr(rvm.rclpy, "shutdown", _raise)

    node = _FakeNode()
    with pytest.raises(RuntimeError):
        rvm._finish(node, {"topic": "/map/vector_map", "verified": True}, EXIT_OK, args)
    # This is precisely what `_cli`'s handler does next.
    rvm._write_crash_report(args, boom)

    filed = json.loads(Path(args.report).read_text())
    assert filed["verified"] is True, filed
    assert filed["verdict_code"] == EXIT_OK, filed
    assert "crashed" not in filed, filed


def test_a_crash_before_the_report_is_written_still_files_the_stub(tmp_path: Path):
    """The behaviour the guard must NOT take away: with no completed report,
    a crash still leaves the artifact a reader will go looking for."""
    args = _finish_args(tmp_path)
    rvm._write_crash_report(args, RuntimeError("died during capture"))

    filed = json.loads(Path(args.report).read_text())
    assert filed["crashed"] is True
    assert filed["verdict_code"] == EXIT_CRASHED
    assert filed["verified"] is False
    assert "died during capture" in filed["error"]


def test_a_crash_DURING_the_report_write_still_files_the_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The boundary case the flag is placed to get right. If `json.dump` itself
    fails, what is on disk is truncated and unparsable -- there is no complete
    report to protect -- so the stub is the correct outcome. The flag is set
    only AFTER the `with` block closes, which is what makes this work."""
    args = _finish_args(tmp_path)
    boom = RuntimeError("disk went away mid-dump")

    def _explode(*a, **kw):
        raise boom

    monkeypatch.setattr(rvm.json, "dump", _explode)

    node = _FakeNode()
    with pytest.raises(RuntimeError):
        rvm._finish(node, {"topic": "/map/vector_map", "verified": True}, EXIT_OK, args)
    assert getattr(args, "report_written", False) is False
    monkeypatch.undo()
    rvm._write_crash_report(args, boom)

    assert json.loads(Path(args.report).read_text())["crashed"] is True


def test_the_guard_keys_off_a_completed_write_not_off_the_file_existing(tmp_path: Path):
    """A stale report left at the same path by an earlier invocation must NOT
    be mistaken for this run's completed one. The flag lives on `args`, which
    is per-invocation, so a pre-existing file is still replaced."""
    args = _finish_args(tmp_path)
    Path(args.report).write_text(json.dumps({"verified": True, "stale": True}))
    rvm._write_crash_report(args, RuntimeError("died during capture"))

    filed = json.loads(Path(args.report).read_text())
    assert filed["crashed"] is True
    assert "stale" not in filed


def test_finish_records_the_write_and_still_returns_the_advisory_status(tmp_path: Path):
    """The flag is a side effect on `args`, so it must not disturb what
    `_finish` returns, nor what it files. Under --advisory the process status
    is 0 while `verdict_code` keeps the real outcome -- the three-key contract
    `_finish`'s own comment sets out."""
    args = _finish_args(tmp_path)
    node = _FakeNode()
    rc = rvm._finish(node, {"topic": "/map/vector_map"}, EXIT_NOT_VERIFIED, args)

    assert rc == EXIT_OK
    assert args.report_written is True
    assert node.destroyed is True
    filed = json.loads(Path(args.report).read_text())
    assert filed["verdict_code"] == EXIT_NOT_VERIFIED
    assert filed["process_exit_code"] == EXIT_OK
    assert filed["advisory"] is True


def test_the_crash_stub_defaults_every_args_attribute_it_reads(tmp_path: Path):
    """`_write_crash_report` runs after an ARBITRARY exception, so `args` may
    not carry what a normal run's does. Every read is defaulted -- including
    `advisory`, which one line used to read bare while the line beside it used
    `getattr`."""
    bare = types.SimpleNamespace(report=str(tmp_path / "r.json"))
    rvm._write_crash_report(bare, RuntimeError("very early"))

    filed = json.loads(Path(bare.report).read_text())
    assert filed["advisory"] is False
    assert filed["process_exit_code"] == EXIT_CRASHED
    assert filed["topic"] == ""


def test_no_report_path_means_no_crash_file_anywhere(tmp_path: Path):
    """`--report` is optional; without it the helper must be a no-op rather
    than inventing a path."""
    rvm._write_crash_report(build_arg_parser().parse_args([]), RuntimeError("x"))
    assert list(tmp_path.iterdir()) == []
