#!/usr/bin/env python3
"""M5 ground truth: one `gt.csv` row per CARLA world tick, in the MAP frame.

    python3 -m benchmarks.scripts.collect_gt --host localhost --port 2000 \
        --role-name ego --map Town10HD_Opt --out <run-dir>/gt.csv [--count-lidar]

Contract (benchmarks/README.md): ``arrival_system_ns, sim_ns, x_m, y_m, z_m,
yaw_rad``.

WHY THE MAP FRAME, NOT CARLA'S
------------------------------
`benchmarks/analysis/quality.evaluate_quality` computes `pose_error` as
``||ndt_xy - gt_xy||`` after joining the two series on sim time, and the NDT
pose it joins against is in the Autoware `map` frame. Writing raw CARLA
coordinates here would make every `pose_error` in the campaign wrong by the
map offset -- and wrong SILENTLY: on Town10 the registered offset is
(0, 0, 0), so only the Y flip would show (a plausible-looking few-metre error
that reads like a localization problem), while on Nishi-Shinjuku the MGRS
offset is ~81 km and the metric would be nonsense that nobody could mistake
for data. The map frame is therefore resolved ONCE, before the client
connects, so an unknown map name fails in milliseconds rather than after a
full collection window has been recorded in the wrong frame.

The conversion is IMPORTED, never re-derived. `scripts/e2e/verify_mgrs_
handedness.py` is the pinned Python mirror of the extension's C++ source of
truth `extension/include/carla/autoware/geo/MgrsOffset.h`, and
`scripts/e2e/collect_gt.py` (the gates' own collector, a different output
contract that this file deliberately does not disturb) wraps it as
`ego_map_xy`. This module calls the same primitive `ego_map_xy` wraps --
`world_m_to_mgrs_local` -- because it needs z as well as x/y, and
`ego_map_xy` drops z. `test_bench_collect_gt.py` asserts the two agree on
x/y, so "same pinned table" is checked rather than asserted. A third copy of
the MGRS constants is the failure mode all of this exists to avoid.

Yaw follows the same single-Y-flip rule via
`benchmarks.scripts.pick_route.carla_to_map_yaw` (``yaw_map = -yaw_carla``),
the same rule `scripts/e2e/arm_closed_loop.sh` seeds `/initialpose` with.

PUBLISHER-SIDE COUNTS (`--count-lidar`)
---------------------------------------
M2 reconciles three counts: expected, publisher-side, observer-side.
`--count-lidar` attaches a client-side `sensor.listen` callback to the ego
LiDAR and writes `publisher_counts.json` next to gt.csv; it is a valid
publisher-side proxy for approaches A and B by the P1 gate-(c) precedent
(`sensor.listen()` rides the same dispatch path that feeds the ROS 2
publisher).

The callback records each message's SIM-TIME stamp, not just a running
total: `duel_verdict.py` reconciles this term against an expected and an
observed count that are both windowed to the run's registered scoring
window, and a whole-run total cannot be windowed after the fact. The
schema, the stamp domain and the reasons are owned by
`benchmarks.analysis.publisher_counts`, which both this writer and the
two readers go through.

DO NOT use it on the python-bridge cells. There, the bridge's own
`sensor.listen()` callback IS the publish path, and CARLA keeps ONE callback
per sensor -- attaching ours would REPLACE the bridge's and stop the run's
pointcloud entirely. Those cells report expected-vs-observed only, with the
publisher column marked not measurable (a disclosed limitation, not a silent
gap). This is enforced below, not just documented.

The interpreter is chosen by the cell launcher (`~/carla-venv` for the
extension cells, the tier4 client venv for B-cells, and for E-cells the
bridge container's own python, which has the pinned 0.9.15 wheel), so the
client always matches its server. `Client.get_client_version()` and
`get_server_version()` are recorded to `carla_versions.json` in the run
directory -- `carla.__version__` does not exist.
"""

from __future__ import annotations

import argparse
import csv
import json
import signal
import sys
import time
from pathlib import Path

from benchmarks.analysis.publisher_counts import publisher_counts_doc
from benchmarks.scripts.pick_route import carla_to_map_yaw
from scripts.e2e.collect_gt import find_ego
from scripts.e2e.verify_mgrs_handedness import offset_for_map, world_m_to_mgrs_local

GT_COLUMNS = ("arrival_system_ns", "sim_ns", "x_m", "y_m", "z_m", "yaw_rad")

# Default publisher-count key: the topic name the natives emit the ego LiDAR
# on, so publisher_counts.json joins to observer.csv on the same string.
DEFAULT_LIDAR_TOPIC = "/sensing/lidar/top/pointcloud_raw_ex"

# Approaches whose publish path IS a python-side sensor.listen callback;
# attaching a counter would displace it. See the module docstring.
LISTEN_OWNING_APPROACHES = ("python-bridge",)

EXIT_BAD_ARGS = 2


def map_pose(
    loc_x_m: float, loc_y_m: float, loc_z_m: float, yaw_deg: float, offset
) -> tuple[float, float, float, float]:
    """CARLA PythonAPI pose (metres, degrees) -> map-frame (x, y, z, yaw_rad).

    Pure, so the frame conversion is unit-tested without a live CARLA.
    """
    x, y, z = world_m_to_mgrs_local(loc_x_m, loc_y_m, loc_z_m, offset)
    return x, y, z, carla_to_map_yaw(yaw_deg)


def sim_ns_from_elapsed(elapsed_seconds: float) -> int:
    """Snapshot sim time (seconds, float) -> integer ns, the gt.csv contract.

    Rounded, not truncated: at 20 Hz the float seconds carry enough precision
    that truncation biases every stamp low by up to a nanosecond, and
    `evaluate_quality` joins gt to NDT on these stamps.
    """
    return int(round(elapsed_seconds * 1e9))


def version_mismatch(client_version: str, server_version: str) -> str | None:
    """Refusal message when the client does not match its server, else None.

    The campaign's rule is that each cell's GT client is built from the same
    CARLA as the server it talks to (the extension fork's wheel for A/C, the
    tier4 fork's for B/D, the pinned 0.9.15 wheel for the E family) -- the
    cell launcher picks the interpreter for exactly that reason. Nothing
    ENFORCED it: a `BENCH_GT_PYTHON` pointed at the wrong fork's venv produced
    a run that looked entirely valid, with gt.csv -- the M5 ground truth --
    written by a client whose tick and coordinate semantics were never
    verified against that server. CARLA itself only logs a version warning,
    which is invisible from a backgrounded collector.

    Pure, so the rule is unit-testable without a live CARLA.
    """
    if client_version == server_version:
        return None
    return (
        f"CARLA client/server version mismatch: client {client_version!r} vs "
        f"server {server_version!r}. This collector must run on the interpreter "
        f"whose carla wheel came from the SAME CARLA as the server (the cell "
        f"launcher picks it; BENCH_GT_PYTHON overrides it). Fix the "
        f"interpreter, not this check -- gt.csv is the M5 ground truth."
    )


def lidar_stamp_recorder(series: list[int]):
    """`sensor.listen` callback appending each message's SIM stamp to
    `series`, in `publisher_counts.json`'s registered domain.

    `carla.SensorData.timestamp` is the episode's `elapsed_seconds` at
    the measurement, so this is the same clock and the same rounding rule
    (`sim_ns_from_elapsed`) as gt.csv's `sim_ns` column -- and therefore
    the domain the duel's scoring-window bounds are in. A wall-clock
    stamp taken here would be a different clock from the one the window
    and the observed count are filtered on, and would need the run's
    clock fit to be comparable at all.

    Returned as a closure rather than written inline at the `listen`
    call so the recorded quantity is unit-testable without a live CARLA.
    """

    def _record(data) -> None:
        series.append(sim_ns_from_elapsed(data.timestamp))

    return _record


def ego_lidar_sensors(world, ego_id: int) -> list:
    """The ego's LiDAR sensors (`sensor.lidar.*`), by parent id."""
    return [
        a
        for a in world.get_actors().filter("sensor.lidar.*")
        if getattr(a, "parent", None) is not None and a.parent.id == ego_id
    ]


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2000)
    p.add_argument("--role-name", default="ego", help="ego actor's role_name attribute")
    p.add_argument("--out", required=True, help="gt.csv path")
    p.add_argument(
        "--map",
        default=None,
        help="map whose converter offset defines the map frame; defaults to "
        "$CARLA_AUTOWARE_MAP and then to the pinned default map",
    )
    p.add_argument(
        "--duration-s",
        type=float,
        default=0.0,
        help="stop after this many seconds; 0 (default) = until SIGTERM, which "
        "is how run.sh drives it (teardown owns the window)",
    )
    p.add_argument("--timeout-s", type=float, default=20.0, help="CARLA RPC timeout")
    p.add_argument(
        "--count-lidar",
        action="store_true",
        help="also attach a sensor.listen counter to the ego LiDAR and write "
        "publisher_counts.json (M2 publisher-side proxy; NOT for bridge cells)",
    )
    p.add_argument("--lidar-topic", default=DEFAULT_LIDAR_TOPIC, help="publisher_counts.json key")
    p.add_argument(
        "--approach",
        default=None,
        help="cells.yaml approach; used only to refuse --count-lidar where a "
        "listener would displace the approach's own publish callback",
    )
    return p


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - needs live CARLA
    args = build_arg_parser().parse_args(argv)

    if args.count_lidar and args.approach in LISTEN_OWNING_APPROACHES:
        print(
            f"GT FAIL: --count-lidar is not valid for approach {args.approach!r}: its "
            "publish path is a sensor.listen callback and CARLA keeps one callback "
            "per sensor, so counting would silence the run's pointcloud",
            file=sys.stderr,
        )
        return EXIT_BAD_ARGS

    # Resolved BEFORE connecting: an unknown map must fail here, not after a
    # window has been recorded in the wrong frame.
    try:
        offset = offset_for_map(args.map)
    except ValueError as exc:
        print(f"GT FAIL: {exc}", file=sys.stderr)
        return EXIT_BAD_ARGS

    import carla  # lazy: this module must import under bare pytest

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = carla.Client(args.host, args.port)
    client.set_timeout(args.timeout_s)
    versions = {
        "client": client.get_client_version(),
        "server": client.get_server_version(),
    }
    # Written BEFORE the check, so the evidence lands in the run directory on
    # the refusal path too -- that pair is what diagnoses the misconfiguration.
    (out_path.parent / "carla_versions.json").write_text(json.dumps(versions, indent=2))
    print(f"carla client={versions['client']} server={versions['server']}")
    mismatch = version_mismatch(versions["client"], versions["server"])
    if mismatch is not None:
        print(f"GT FAIL: {mismatch}", file=sys.stderr)
        return EXIT_BAD_ARGS

    world = client.get_world()
    world.wait_for_tick()  # sync mode: a cold client sees an empty snapshot
    ego = find_ego(world, role_name=args.role_name)

    stamps: dict[str, list[int]] = {}
    sensors = []
    if args.count_lidar:
        stamps[args.lidar_topic] = []
        sensors = ego_lidar_sensors(world, ego.id)
        if not sensors:
            print(
                f"GT FAIL: --count-lidar found no sensor.lidar.* parented to "
                f"{args.role_name!r}; publisher-side count would silently be 0",
                file=sys.stderr,
            )
            return EXIT_BAD_ARGS
        record = lidar_stamp_recorder(stamps[args.lidar_topic])
        for sensor in sensors:
            sensor.listen(record)
        print(f"counting {len(sensors)} LiDAR sensor(s) -> {args.lidar_topic}")

    stopping = {"stop": False}

    def _stop(_signum, _frame):
        stopping["stop"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    deadline = time.monotonic() + args.duration_s if args.duration_s > 0 else None
    rows = 0
    try:
        with open(out_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(GT_COLUMNS)
            f.flush()
            while not stopping["stop"] and (deadline is None or time.monotonic() < deadline):
                try:
                    snapshot = world.wait_for_tick(seconds=args.timeout_s)
                except RuntimeError as exc:
                    # A stalled sim is the clock watchdog's call to make, not
                    # this collector's: keep waiting so a recovered tick is
                    # still recorded, and let teardown stop us.
                    print(f"warning: wait_for_tick: {exc}", file=sys.stderr)
                    continue
                arrival_ns = time.time_ns()
                tf = ego.get_transform()
                x, y, z, yaw = map_pose(
                    tf.location.x, tf.location.y, tf.location.z, tf.rotation.yaw, offset
                )
                writer.writerow(
                    [
                        arrival_ns,
                        sim_ns_from_elapsed(snapshot.timestamp.elapsed_seconds),
                        f"{x:.4f}",
                        f"{y:.4f}",
                        f"{z:.4f}",
                        f"{yaw:.6f}",
                    ]
                )
                # Flushed per row: teardown SIGTERMs this process, and an
                # unflushed tail is exactly the window's end, where the M5
                # goal metrics live.
                f.flush()
                rows += 1
    finally:
        for sensor in sensors:
            try:
                sensor.stop()
            except RuntimeError:
                pass
        if args.count_lidar:
            (out_path.parent / "publisher_counts.json").write_text(
                json.dumps(publisher_counts_doc(stamps), indent=2)
            )
    counts = {topic: len(series) for topic, series in stamps.items()}
    print(f"gt_rows={rows}" + (f" publisher_counts={counts}" if args.count_lidar else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
