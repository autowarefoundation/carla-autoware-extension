#!/usr/bin/env python3
"""Re-publish `/map/vector_map` once the stack has settled, then gate on it
having been delivered -- a harness-injected WORKAROUND for a MEASURED transport
defect, not a gate adjustment and not a threshold change.

Runs INSIDE the cell's Autoware container (docker exec), using only rclpy and
message packages the container already provides, exactly like
`seed_localization.py` and `arm_and_goal.py`.

WHAT DEFECT, AND HOW IT WAS MEASURED (Task 4b, 2026-08-01; full evidence and
every raw capture in benchmarks/evidence/b-vector-map-delivery/):

`/map/lanelet2_map_loader` publishes ONE 1 305 281-byte `LaneletMapBin` from
its constructor, `RELIABLE / KEEP_LAST(1) / TRANSIENT_LOCAL`. Every subscriber
in the stack -- `behavior_path_planner` included, read off the live graph --
requests that exact QoS, so there is NO durability mismatch, and a
late-joining subscriber with that QoS received the sample 9 times out of 9
(0.028-2.643 s). What is unreliable is delivery to the subscribers that
ALREADY EXIST when that single publication happens. On the in-stack
`/system/topic_state_monitor_vector_map`, same QoS, over six Fast-DDS
`udp_only` bring-ups, first receipt relative to `Map is published.` was:

    +20.2 s | NEVER (+98.2 s) | +11.5 s | NEVER (+113.35 s) | +0.97 s | +0.05 s

-- TWO OUTRIGHT FAILURES IN SIX. Reproduced standalone with the same image,
bundle and launch line, with no CARLA and no harness at all (replica V1 vs
V1b: consecutive runs of the same script, two minutes apart, "never in 113 s"
against "0.97 s"), which localises it to the `rmw_fastrtps_cpp` +
`benchmarks/observer/config/udp_only.xml` transport that the tier4-native
family alone runs. Cells A/C/E run `rmw_cyclonedds_cpp`; a cyclonedds control
bring-up delivered at +0.24 s, n = 1, which is NOT a claim of immunity.

WHY A RE-PUBLISH AND NOT A DDS PROFILE CHANGE. The only path measured failing
is Fast-DDS's TRANSIENT_LOCAL historical delivery on match. Re-publishing after
the readers are already matched turns the map into ORDINARY LIVE DATA -- the
path the rest of the stack uses successfully at 20 Hz -- and sidesteps the
historical path entirely. Editing `observer/config/udp_only.xml` was the
obvious alternative and was REJECTED: that file's sha256 is recorded in every
filed B manifest as `transport.dds_profile_sha256`, so changing it would make
cell B's already-filed runs non-comparable on transport, and it is shared with
the observer container. A 16 MiB socket-buffer variant was tried once and
proves nothing (one passing run against a 2-in-6 failure has no power); the
buffer hypothesis is neither supported nor refuted.

THE HONEST LIMIT OF THIS WORKAROUND, stated because the record must carry it:
the re-publish creates a NEW writer, and an already-running reader must still
match it -- which is the same event ordering that fails for `map_loader`. What
is different, and what the design rests on, is that this script WAITS for its
own subscriber matching to settle BEFORE publishing, so the sample goes out as
live data to readers that are already matched rather than as history served on
match. That is a reasoned mitigation, NOT a demonstrated cure. It was once the
reason the verification below was mandatory; it is not any more -- see the next
paragraph, which supersedes that reading.

ADVISORY, NOT FATAL -- and WHY IT CHANGED. This step was originally a gate
that aborted the bring-up. `benchmarks/results/B/run-031` refuted that design
in the most direct way available: the gate failed (3 attempts, 60 s each, its
verification endpoint never OK) and the SAME run's launch log showed the
re-published map being delivered on ALL THREE attempts to
`lanelet2_map_visualization` (`:1123`, `:2149`, `:3147`) and
`vector_map_tf_generator` (`:1128`, `:2155`, `:3152`) -- both in a different
process from this script, so each is a real inter-process receipt. The gate
therefore converted a possibly-armable run into a `crash:cell-launch`, and
because it fires BEFORE any route exists it left the actual question untested:
`behavior_path_planner` logged `waiting for scenario_topic` 38 times and never
evaluated its map check at all.

The campaign's pass criteria are the arm succeeding and `control_cmd` flowing.
This step is an ADDED precondition and is not one of them, so it records its
outcome and continues. If the map genuinely never reaches the planner the run
still fails -- at the arm, loudly, and more informatively than here.

TWO ORACLES, AND WHICH ONE PROVED REPRESENTATIVE. Both are recorded on every
attempt; the refuted one stays in the record with what refuted it.

  * `topic_state_monitor_vector_map` (`verified`) -- the ORIGINAL oracle, now
    known to be a poor one. It is an in-stack subscriber of the same class as
    `behavior_path_planner`, but the two are INDEPENDENT DRAWS, not proxies:
    `run-028` has the monitor OK at +23.2 s while the planner stayed blocked
    for 53.3 s more, and `run-031` is the mirror image -- monitor NotReceived
    for ~220 s while two other in-stack subscribers received every
    re-publication. Kept because it is the series whose six-bring-up history
    is quoted above, and dropping it would break that comparability.
  * the RE-LOG delta (`verified_relog`) -- the oracle `run-031` established.
    `lanelet2_map_visualization` and `vector_map_tf_generator` each print a
    line every time they receive a vector map, in a different process from
    this one, so a FRESH line after a publication is direct evidence that the
    publication crossed a process boundary. This is the better delivery
    oracle. It is still not the planner: neither oracle observes
    `behavior_path_planner`, whose only self-report is its `waiting for map`
    line, which exists only once a route has been set -- i.e. after this
    script, during the arm.

SCOPE: the closed-loop arm ONLY. `cells/tier4_autoware.sh` gates the call, and
cell B's static bring-up must not acquire a step -- B's static runs are already
filed as the static verdict pool.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

import rclpy
from autoware_map_msgs.msg import LaneletMapBin
from diagnostic_msgs.msg import DiagnosticArray
from rclpy.node import Node
from rclpy.qos import (
    QoSDurabilityPolicy,
    QoSHistoryPolicy,
    QoSProfile,
    QoSReliabilityPolicy,
)

# Exit codes, distinct so a bring-up failure names WHICH half did not happen.
# The launcher's message keys off these, and a reader of a failed run should
# never have to guess whether the map was missing or merely undelivered.
EXIT_OK = 0
EXIT_NO_CAPTURE = 3  # the retained sample never reached THIS process either
EXIT_NO_MATCH = 4  # our publisher never matched any subscriber
EXIT_NOT_VERIFIED = 5  # published, but the in-stack monitor never went OK
EXIT_CRASHED = 6  # an exception escaped before a normal report could be written

# The monitor node whose receipt is the gate. Named once, here, because the
# same string is what `--report` records and what the launcher's failure text
# tells the operator to grep for.
MONITOR_SUBSTRING = "topic_state_monitor_vector_map"

# `DiagnosticStatus.level` is a byte field; rclpy hands it back as `bytes` on
# this image and as `int` on others. Both were seen live while building this
# (`level=b'\x00'` from a python subscriber, `level=0` from the C++ side), so
# normalising is not defensive coding -- it is the difference between the gate
# working and the gate always failing.
DIAG_OK = 0

# The two nodes that re-log on every vector-map receipt. Both live in the map
# container -- a DIFFERENT process from this script -- so a fresh line after a
# publication is inter-process receipt, which is exactly what run-031 showed
# happening three times while `topic_state_monitor_vector_map` reported none of
# it. Substrings rather than full lines because the log carries a launch-prefix
# and a timestamp that vary per run.
RELOG_MARKERS = (
    "lanelet2_map_visualization]: Map is loaded",
    "vector_map_tf_generator]: broadcast static tf",
)


def count_relog_markers(text: str) -> dict:
    """Occurrences of each re-log marker in a launch log."""
    return {marker: text.count(marker) for marker in RELOG_MARKERS}


def relog_shows_delivery(before: dict, after: dict) -> bool:
    """True when at least one re-log marker gained a line.

    The DELTA, never the absolute count: `map_loader`'s own original
    publication always logs one of each, so an absolute test would report
    delivery on every run including the ones that delivered nothing. Empty
    dicts -- an unreadable launch log -- yield False, because in this campaign
    an absence of evidence never reads as a pass.
    """
    return any(after.get(m, 0) > before.get(m, 0) for m in RELOG_MARKERS)


def read_launch_log(path: str) -> str:
    """Best-effort read; an unreadable log costs the second oracle, never the
    run (this step is advisory, and it must not become a new way to fail)."""
    try:
        with open(path, errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def diag_level(level) -> int:
    """`DiagnosticStatus.level` as an int, whatever rclpy handed us."""
    if isinstance(level, (bytes, bytearray)):
        return int.from_bytes(bytes(level), "big") if level else DIAG_OK
    return int(level)


def status_reports_delivered(level, values: dict) -> bool:
    """True when a topic_state_monitor status says the map ARRIVED.

    Both conditions are required and neither is redundant. `level == OK` alone
    is not enough: the monitor publishes one initial status with level OK and
    NO key/value pairs at all, before its first check runs -- measured twice
    live (`level=OK status=None last_message_time=None`, immediately followed
    by `level=ERROR status=NotReceived`). Gating on level alone would therefore
    pass ~0.2 s into every bring-up, including the two that never delivered the
    map at all. The `status` key is what the monitor sets from its own receipt
    bookkeeping, so it is the field that means what this gate needs.
    """
    return diag_level(level) == DIAG_OK and values.get("status") == "OK"


def matching_settled(history: list[tuple[float, int]], settle_s: float) -> bool:
    """True when the subscriber count has been non-zero and UNCHANGED for
    `settle_s` seconds of samples.

    Non-zero is required because publishing into a matched set of zero readers
    is exactly the failure this script exists to avoid -- it would emit the
    sample into nothing and then gate on a monitor that never got it, turning a
    transport defect into a confusing bring-up failure. "Unchanged" rather than
    "at least N" because the stack's subscriber count is not knowable ahead of
    time: 16 endpoints were enumerated on one bring-up and 3 on another, both
    healthy, because discovery is still converging. A count that has stopped
    moving is the only signal available that does not hard-code a number the
    stack is free to change.
    """
    if not history:
        return False
    latest_t, latest_n = history[-1]
    if latest_n <= 0:
        return False
    for t, n in reversed(history):
        if n != latest_n:
            return False
        if latest_t - t >= settle_s:
            return True
    return False


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--topic", default="/map/vector_map")
    p.add_argument(
        "--capture-timeout-s",
        type=float,
        default=90.0,
        help="budget for OUR OWN transient_local subscription to receive the "
        "retained sample. Measured 9/9 in 0.028-2.643 s, so a timeout here "
        "means something far more wrong than the defect this works around.",
    )
    p.add_argument(
        "--settle-s",
        type=float,
        default=5.0,
        help="how long the subscriber count must hold steady before publishing",
    )
    p.add_argument("--match-timeout-s", type=float, default=60.0)
    p.add_argument(
        "--verify-timeout-s",
        type=float,
        default=60.0,
        help="budget for the in-stack monitor to report the map delivered after a re-publish",
    )
    p.add_argument(
        "--attempts",
        type=int,
        default=3,
        help="re-publish attempts before giving up. Bounded and recorded in "
        "--report; a retry is not a second mechanism, it is the same live "
        "publication tried again against a defect measured to be "
        "nondeterministic at ~2-in-6.",
    )
    p.add_argument(
        "--launch-log",
        default="/tmp/tier4-autoware.log",
        help="container-side launch log, read for the re-log delivery oracle",
    )
    p.add_argument(
        "--advisory",
        action="store_true",
        help="always exit 0. The real verdict still lands in --report as "
        "verdict_code; this only decides whether it reaches the caller as an "
        "exit status. cells/tier4_autoware.sh passes it: see this file's "
        "header for why run-031 made the fatal form untenable.",
    )
    p.add_argument("--report", default="", help="write a JSON report here")
    return p


class VectorMapRepublisher(Node):
    def __init__(self, topic: str) -> None:
        super().__init__("bench_vector_map_republisher")
        self._topic = topic
        self._captured: LaneletMapBin | None = None
        self._diag: dict[str, tuple] = {}
        self._qos = QoSProfile(
            depth=1,
            history=QoSHistoryPolicy.KEEP_LAST,
            reliability=QoSReliabilityPolicy.RELIABLE,
            durability=QoSDurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(LaneletMapBin, topic, self._on_map, self._qos)
        self.create_subscription(
            DiagnosticArray,
            "/diagnostics",
            self._on_diag,
            QoSProfile(depth=100, reliability=QoSReliabilityPolicy.RELIABLE),
        )
        self._pub = None

    def _on_map(self, msg: LaneletMapBin) -> None:
        if self._captured is None:
            self._captured = msg

    def _on_diag(self, msg: DiagnosticArray) -> None:
        for st in msg.status:
            if MONITOR_SUBSTRING in st.name:
                values = {kv.key: kv.value for kv in st.values}
                self._diag[st.name] = (st.level, values)

    def spin_for(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            rclpy.spin_once(self, timeout_sec=0.1)

    def spin_until(self, predicate, timeout_s: float) -> bool:
        end = time.time() + timeout_s
        while time.time() < end:
            if predicate():
                return True
            rclpy.spin_once(self, timeout_sec=0.1)
        return predicate()

    @property
    def captured(self):
        return self._captured

    def monitor_delivered(self) -> bool:
        return any(status_reports_delivered(level, values) for level, values in self._diag.values())

    def monitor_snapshot(self) -> dict:
        return {
            name: {
                "level": diag_level(level),
                "status": values.get("status"),
                "last_message_time": values.get("last_message_time"),
            }
            for name, (level, values) in self._diag.items()
        }

    def create_publisher_for_topic(self):
        self._pub = self.create_publisher(LaneletMapBin, self._topic, self._qos)
        return self._pub

    def subscriber_count(self) -> int:
        return self._pub.get_subscription_count() if self._pub else 0

    def publish_captured(self) -> None:
        self._pub.publish(self._captured)


def main(argv: list[str] | None = None) -> int:
    return main_with_args(build_arg_parser().parse_args(argv))


def main_with_args(args) -> int:
    report: dict = {"topic": args.topic, "attempts": []}

    # Seeded so EVERY exit path carries them, including the no-capture and
    # no-match returns. A key that is present on some outcomes and absent on
    # others makes `verified is not True` and `"verified" not in report` mean
    # different things to a reader, which is exactly the ambiguity this campaign
    # keeps paying for.
    report["verified"] = False
    report["verified_relog"] = False

    rclpy.init()
    node = VectorMapRepublisher(args.topic)
    t0 = time.time()

    # 1. PRE-STATE, recorded before anything is changed. This is the per-run
    #    observation of the STOCK delivery path -- the series whose first six
    #    entries are quoted in this file's header -- and it is the only chance
    #    to take it, because everything below deliberately perturbs it.
    node.spin_for(6.0)
    report["pre_republish_monitor"] = node.monitor_snapshot()
    report["pre_republish_delivered"] = node.monitor_delivered()

    # 2. Capture the retained sample. Measured 9/9; a failure here is not the
    #    defect this script works around.
    got = node.spin_until(lambda: node.captured is not None, args.capture_timeout_s)
    report["captured"] = bool(got)
    report["capture_wait_s"] = round(time.time() - t0, 3)
    if not got:
        return _finish(node, report, EXIT_NO_CAPTURE, args)
    report["data_bytes"] = len(node.captured.data)

    # 3. Publish only once our own writer has matched a settled set of readers
    #    (see matching_settled for why "settled" and not "at least N").
    node.create_publisher_for_topic()
    history: list[tuple[float, int]] = []

    def settled() -> bool:
        history.append((time.time(), node.subscriber_count()))
        return matching_settled(history, args.settle_s)

    matched = node.spin_until(settled, args.match_timeout_s)
    report["subscriber_count"] = node.subscriber_count()
    report["matching_settled"] = bool(matched)
    if not matched:
        return _finish(node, report, EXIT_NO_MATCH, args)

    # 4. Publish, then verify against BOTH oracles. Retry bounded by
    #    --attempts, which run-031 and the replica smoke both showed is
    #    load-bearing rather than decoration: on the replica the monitor only
    #    flipped on the THIRD publication.
    #
    #    The loop still exits early only on the MONITOR, deliberately. The
    #    re-log oracle is the better evidence of delivery, but stopping on it
    #    would shorten the monitor series whose six-bring-up history this
    #    file's header quotes, and that series is the campaign's only record of
    #    the underlying defect's rate. Advisory mode makes the extra attempts
    #    cost bring-up seconds, never a run.
    any_relog = False
    for attempt in range(1, args.attempts + 1):
        relog_before = count_relog_markers(read_launch_log(args.launch_log))
        published_at = time.time()
        node.publish_captured()
        ok = node.spin_until(node.monitor_delivered, args.verify_timeout_s)
        relog_after = count_relog_markers(read_launch_log(args.launch_log))
        relogged = relog_shows_delivery(relog_before, relog_after)
        any_relog = any_relog or relogged
        report["attempts"].append(
            {
                "attempt": attempt,
                "verified": bool(ok),
                "verified_relog": bool(relogged),
                "verify_wait_s": round(time.time() - published_at, 3),
                "monitor": node.monitor_snapshot(),
                "relog_before": relog_before,
                "relog_after": relog_after,
            }
        )
        if ok:
            report["verified"] = True
            report["verified_relog"] = any_relog
            return _finish(node, report, EXIT_OK, args)
    report["verified"] = False
    report["verified_relog"] = any_relog
    return _finish(node, report, EXIT_NOT_VERIFIED, args)


def _finish(node, report: dict, code: int, args) -> int:
    # THREE keys, because one was ambiguous. `verdict_code` is the real
    # outcome. `exit_code` KEEPS ITS HISTORICAL MEANING -- the verdict, not the
    # process status -- because results/B/run-031's filed report already uses it
    # that way and renaming it would break comparison with the one run that
    # matters most here; it is retained for that reason alone and a reader
    # should prefer `verdict_code`. `process_exit_code` is what this process
    # actually returns to the shell, which under --advisory is always 0 because
    # the step is an added precondition and not one of the campaign's pass
    # criteria.
    report["verdict_code"] = code
    report["exit_code"] = code
    report["process_exit_code"] = EXIT_OK if args.advisory else code
    report["advisory"] = bool(args.advisory)
    report["monitor_final"] = node.monitor_snapshot()
    report["relog_final"] = count_relog_markers(read_launch_log(args.launch_log))
    if args.report:
        with open(args.report, "w") as fh:
            json.dump(report, fh, indent=2, sort_keys=True)
    print(json.dumps(report, sort_keys=True))
    node.destroy_node()
    rclpy.shutdown()
    return EXIT_OK if args.advisory else code


def _write_crash_report(args, exc: BaseException) -> None:
    """A crash before `_finish` used to leave NO report at all, and the advisory
    call site prints only that the step "did not complete cleanly" -- so the one
    artifact a reader would go looking for would not exist. Best-effort, and
    never allowed to mask the original exception."""
    if not getattr(args, "report", ""):
        return
    try:
        with open(args.report, "w") as fh:
            json.dump(
                {
                    "topic": getattr(args, "topic", ""),
                    "crashed": True,
                    "error": "%s: %s" % (type(exc).__name__, exc),
                    "traceback": traceback.format_exc(),
                    "verified": False,
                    "verified_relog": False,
                    "verdict_code": EXIT_CRASHED,
                    "exit_code": EXIT_CRASHED,
                    "process_exit_code": EXIT_OK if args.advisory else EXIT_CRASHED,
                    "advisory": bool(getattr(args, "advisory", False)),
                },
                fh,
                indent=2,
                sort_keys=True,
            )
    except OSError:
        pass


def _cli() -> int:
    args = build_arg_parser().parse_args()
    try:
        return main_with_args(args)
    except BaseException as exc:  # noqa: BLE001 -- recorded, then re-raised
        _write_crash_report(args, exc)
        print("CRASHED before writing a report: %r" % (exc,), file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(_cli())
