#!/usr/bin/env python3
"""The M4 sweep's ABLATION arm: the identical LiDAR rig, publishing disabled.

    PYTHONPATH=. python3 benchmarks/scripts/raycast_baseline.py \
        --rig extension --tick-hz 20.0 --out-dir <run-dir> \
        --lidar-channels 16 --lidar-pps 288000

The transport sweep decomposes where sensor-pipeline time goes. This is the
decomposition's BASELINE: a plain CARLA client that spawns the same ego + top
LiDAR the cell's normal path spawns, with every native-ROS 2 attribute removed
and no ``enable_for_ros()`` call, listens with a do-nothing sink, and
sync-ticks the world at the cell's REGISTERED tick for the run's window. No
ROS, no DDS, no Autoware -- so

    transport cost = total - baseline

DISCLOSED LIMITATION (mandatory; the wrap doc depends on it). A CARLA sensor
only produces data while a client is subscribed to its stream, so the baseline
has to ``sensor.listen(...)`` to make the raycast happen at all -- and that
listen ships every cloud over the client stream, which is an RPC hop the
native cells' in-process publisher does NOT pay. The "baseline" therefore
includes work the native path does not do, so ``transport cost = total -
baseline`` is a **LOWER BOUND** for the native cells (A, B), not an equality.
It is not softened anywhere downstream and must not be quoted as one.

WHAT THIS WRITES, AND WHY IT IS THIS FILE
`sweep_verdict.py` scores an ablation run from `manifest.json` (arm
"ablation"), `resources.csv`'s `rtf` series, `observer.csv` (existence),
NO `publisher_counts.json` (publishing is disabled by design, and a
file-backed `0` would FIRE the ceiling's publisher disjunct on a run that
never intended to publish) and NO `quality.json` (the ablation arm defaults
`quality_ok=True` with a note, because no closed loop runs). Every one of
those is written -- or deliberately not written -- by the harness around this
client, with one exception:

`clock.csv`. The `rtf` column is NOT produced by the sampler (which writes the
`-1` "not measured" sentinel in every row) but by `sampler/finalize_rtf.py`,
which derives it from `clock.csv`; and `clock.csv` is normally written by
`bench_observer` from `/clock`, which nothing publishes on this arm. So this
client writes `clock.csv` itself, one row per tick, `clock_ns` from the world
snapshot and `arrival_system_ns` from `time.time_ns()` -- the same
`CLOCK_REALTIME` domain `sample_resources.py` stamps its `sample_system_ns`
with, which is what makes finalize_rtf's [t-1s, t] window join valid. That
file is also what keeps `run.sh` step 7's clock watchdog from excluding every
ablation run as `stall:clock`, and what gives step 15's smoke the >= 2 rows
`fit_sim_wall_affine` needs.

`bench_observer` still runs (run.sh step 6 starts it unconditionally, and its
constructor is what creates the `observer.csv` `sweep_verdict.py` requires to
EXIST), and it TRUNCATES `clock.csv` when it opens it -- after the launcher
started this client at step 5. `ClockCsvWriter` therefore appends
(`O_APPEND` places every write at the file's current end, atomically) and
writes the header only when the file is absent or empty: the observer's
truncation discards this client's bring-up rows and the file continues,
cleanly, as "the observer's identical header + this client's rows from step 6
on". Losing the pre-step-6 rows costs nothing -- they are bring-up, outside
every scoring window.

IMPORT DISCIPLINE. ``carla`` is imported lazily inside ``main()``, after
argument parsing, so this module -- and the rig builders the unit tests
exercise -- import cleanly under bare pytest with no CARLA egg, which is how
CI runs it. Same rule, same reason, as ``runner/spawn.py`` and
``runner/__main__.py``.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

from runner.kit import TOP_LIDAR_FRAME, carla_attach_location, carla_attach_rotation, load_kit
from runner.loop import run_sync_loop
from runner.spawn import EGO_BLUEPRINT, TOP_LIDAR_BLUEPRINT, top_lidar_attributes

EXTENSION_RIG = "extension"
TIER4_RIG = "tier4"
RIGS = (EXTENSION_RIG, TIER4_RIG)

# The tier4-native (cell B) rig: the LITERAL defaults of
# benchmarks/patches/tier4-native/0003-autoware-demo-params.patch's
# generate_vlp16_blueprint, as recorded in that patch set's README ("It is PURE
# parameterization, and that was verified rather than asserted" -- the
# original-vs-patched attribute dump), MINUS its two `ros_*` keys
# (`ros_name: velodyne_top`, `ros_topic_name:
# /sensing/lidar/top/pointcloud_raw_ex`), which are exactly what this arm
# ablates. Transcribed rather than imported because the patched module lives in
# the fork tree, not in this repo -- so it is pinned by a unit test against the
# README's certified dump, and the two files must be changed together.
#
# `sensor_tick` is the demo's PUBLISH PERIOD (patch flag --lidar-rotation-hz ->
# 1/HZ), not the blueprint's `rotation_frequency`, which this demo has never
# set -- the identically-named extension-runner flag drives a different
# attribute. A sweep class pins channels + points_per_second only
# (cells.yaml `sweep_classes`), so neither is a class knob.
TIER4_LIDAR_ATTRIBUTES: dict[str, str] = {
    "channels": "16",
    "range": "100.0",
    "upper_fov": "10.0",
    "lower_fov": "-20.0",
    "points_per_second": "288000",
    "sensor_tick": "0.1",
}

CLOCK_HEADER = "clock_ns,arrival_system_ns\n"

# A hard cap on the tick loop, not the scoring window. The window is whatever
# run.sh sleeps (step 10) and whatever the sampler + finalize_rtf then cover;
# this only bounds how long an ORPHANED client (its launcher gone, its teardown
# missed) can keep ticking a server nobody is watching. Overridden per run by
# the launcher's BENCH_ABLATION_DURATION_S.
DEFAULT_DURATION_S = 600.0


def _ros_free(attrs: dict[str, str]) -> dict[str, str]:
    """`attrs` without any `ros*` attribute.

    Dropping them IS the ablation: `ros_topic_name` / `ros2_extended_lidar` /
    `ros_name` / `ros2_qos_*` are what make the fork's native publisher emit,
    and a rig that kept even one of them would be measuring the transport this
    arm exists to subtract. Matched on the `ros` prefix rather than by an
    explicit key list so a new native-publisher attribute added to
    `runner/spawn.py` is ablated by default instead of silently publishing
    from the baseline.
    """
    return {k: v for k, v in attrs.items() if not k.startswith("ros")}


def _class_overrides(channels: int | None, points_per_second: int | None) -> dict[str, str]:
    """The sweep class's two attribute overrides, as CARLA's string values.

    Only a key whose flag was actually given appears, so an omitted flag is a
    true no-op and each rig's own default stands (the same rule
    `runner/__main__.py::build_lidar_overrides` follows for the live rig).
    """
    overrides: dict[str, str] = {}
    if channels is not None:
        overrides["channels"] = str(channels)
    if points_per_second is not None:
        overrides["points_per_second"] = str(points_per_second)
    return overrides


def extension_rig_attributes(
    channels: int | None = None, points_per_second: int | None = None
) -> dict[str, str]:
    """Cell A's top-LiDAR rig with publishing disabled.

    DERIVED from `runner.spawn.top_lidar_attributes` -- the committed rig
    itself -- rather than transcribed, so a change to the measured rig follows
    into its own baseline automatically instead of the two drifting apart
    silently.
    """
    return _ros_free(top_lidar_attributes(_class_overrides(channels, points_per_second)))


def tier4_rig_attributes(
    channels: int | None = None, points_per_second: int | None = None
) -> dict[str, str]:
    """Cell B's top-LiDAR rig with publishing disabled (see
    TIER4_LIDAR_ATTRIBUTES for why this one is transcribed, not imported)."""
    return {**TIER4_LIDAR_ATTRIBUTES, **_class_overrides(channels, points_per_second)}


def rig_attributes(
    rig: str, channels: int | None = None, points_per_second: int | None = None
) -> dict[str, str]:
    if rig == EXTENSION_RIG:
        return extension_rig_attributes(channels, points_per_second)
    if rig == TIER4_RIG:
        return tier4_rig_attributes(channels, points_per_second)
    raise ValueError(f"unknown rig {rig!r}; registered rigs: {', '.join(RIGS)}")


def default_mount() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """(location_m, rotation_deg) for the top LiDAR, from the committed kit.

    `runner/kit.py` composes base_link -> sensor_kit_base_link -> velodyne_top
    out of `runner/config/*.yaml` (the `awsim_labs_sensor_kit` calibration),
    which is the extension family's real mount and is therefore exact for
    `--rig extension`.

    For `--rig tier4` it is an APPROXIMATION, and a disclosed one: that
    family's mount lives in the fork's own `autoware_demo.py` transform chain
    (ego -> base_link -> sensor_kit -> lidar), which is not committed to this
    repo, so there is nothing here to derive it from. Both stacks model the
    same AWSIM sensor kit, so the difference is centimetre-scale and changes
    scene occlusion, not the ray budget (channels x points_per_second x range)
    the sweep classes move. `--mount` overrides it for an operator who has the
    fork's real numbers to hand; it is not silently assumed away.
    """
    kit = load_kit()
    return carla_attach_location(kit, TOP_LIDAR_FRAME), carla_attach_rotation(kit, TOP_LIDAR_FRAME)


class ClockCsvWriter:
    """Appender for the run directory's `clock.csv`.

    APPEND, not truncate, and the header only when the file is empty: this
    client and `bench_observer` both open the same file, the observer second
    and with `O_TRUNC` (see the module docstring). `O_APPEND` makes every write
    land at the file's current end atomically, so the observer's truncation
    costs this writer its earlier rows and nothing else -- no interleaving, no
    NUL padding, no second header. Flushed per row because the clock watchdog
    (run.sh step 7) reads this file to decide whether the run stalled: a
    buffered writer would look exactly like a frozen sim.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.rows = 0
        self._f = None

    def __enter__(self) -> ClockCsvWriter:
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not self.path.exists() or self.path.stat().st_size == 0
        self._f = open(self.path, "a", newline="")
        if needs_header:
            self._f.write(CLOCK_HEADER)
            self._f.flush()

    def write(self, clock_ns: int, arrival_system_ns: int) -> None:
        self._f.write(f"{int(clock_ns)},{int(arrival_system_ns)}\n")
        self._f.flush()
        self.rows += 1

    def close(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None


class NullSink:
    """The `sensor.listen` callback: counts and drops.

    The brief's shape is `lambda d: None`; the only addition is the counter,
    and it is deliberate. Publishing is disabled and the GT collector's
    `--count-lidar` is off, so `publisher_counts.json` and `observer.csv` are
    both (correctly) empty -- which leaves NO record anywhere that the rig
    raycast anything at all. One integer increment per cloud is the cheapest
    possible evidence that this run measured a live sensor rather than an idle
    one, and it is reported in `raycast_baseline.json`. It does not touch the
    point data.
    """

    def __init__(self):
        self.count = 0

    def __call__(self, data) -> None:
        self.count += 1


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Publish-disabled LiDAR raycast baseline (M4 sweep, ablation arm)."
    )
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2000)
    p.add_argument(
        "--rig",
        required=True,
        choices=RIGS,
        help="which family's rig to reproduce: extension (cell A) or tier4 (cell B)",
    )
    p.add_argument(
        "--class-id",
        default="",
        help="sweep class id, recorded in raycast_baseline.json for provenance; the "
        "class's ACTUAL effect comes from --channels/--pps, which the cell launcher "
        "derives (cells/extension.sh, cells/tier4-native.sh)",
    )
    # The launchers' Task-6 class mapping emits `--lidar-channels N --lidar-pps
    # N` (the runner's / the tier4 demo's own flag names). Accepting those
    # spellings as aliases is what lets each ablation branch pass
    # $BENCH_RUNNER_SWEEP_ARGS / $BENCH_TIER4_SWEEP_ARGS through VERBATIM,
    # instead of re-deriving the class mapping a third time.
    p.add_argument("--channels", "--lidar-channels", dest="channels", type=int, default=None)
    p.add_argument("--pps", "--lidar-pps", dest="pps", type=int, default=None)
    p.add_argument(
        "--tick-hz",
        type=float,
        required=True,
        help="sync fixed-delta target = 1/HZ. The cell's REGISTERED metrics.tick_hz "
        "(cells.yaml, via cell_info.metrics_for): sweep_verdict.py scores paced and "
        "ablation at the same paced target, so this must not be a literal",
    )
    p.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S)
    p.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="the run directory: clock.csv and raycast_baseline.json are written here",
    )
    p.add_argument(
        "--ego-blueprint",
        default=EGO_BLUEPRINT,
        help=f"the LiDAR's carrier vehicle (default: {EGO_BLUEPRINT})",
    )
    # Same two spellings the two families' launchers already produce for their
    # own clients: cells/extension.sh derives `--initial-pose x y z 0 0 yaw`
    # (run_e2e.sh -> runner) and cells/tier4_autoware.sh derives `--spawn-pose
    # x y z 0 0 yaw` (the patched demo). Accepting both means each ablation
    # branch reuses its family's existing derivation verbatim.
    p.add_argument(
        "--initial-pose",
        "--spawn-pose",
        dest="initial_pose",
        nargs=6,
        type=float,
        default=None,
        metavar=("X_M", "Y_M", "Z_M", "ROLL_DEG", "PITCH_DEG", "YAW_DEG"),
        help="ego spawn pose in CARLA world coordinates (metres, degrees)",
    )
    p.add_argument(
        "--spawn-index",
        type=int,
        default=0,
        help="index into world.get_map().get_spawn_points(); ignored when a pose is given",
    )
    p.add_argument(
        "--mount",
        nargs=6,
        type=float,
        default=None,
        metavar=("X_M", "Y_M", "Z_M", "ROLL_DEG", "PITCH_DEG", "YAW_DEG"),
        help="override the LiDAR's attach pose on the ego (default: the committed "
        "sensor-kit pose; see default_mount() for why that is exact for --rig "
        "extension and an approximation for --rig tier4)",
    )
    return p


def _summary_path(out_dir: Path) -> Path:
    return Path(out_dir) / "raycast_baseline.json"


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    # Everything above is argument resolution and must stay CARLA-free: the
    # `--help` path is exercised offline by the unit tests and by the operator
    # on a machine with no wheel installed.
    import carla

    attrs = rig_attributes(args.rig, args.channels, args.pps)
    if args.mount:
        location = tuple(args.mount[:3])
        rotation = tuple(args.mount[3:])
    else:
        location, rotation = default_mount()

    fixed_delta = 1.0 / args.tick_hz
    print(f"raycast_baseline: rig={args.rig} class={args.class_id or '-'} attrs={attrs}")
    print(f"raycast_baseline: tick {args.tick_hz} Hz (fixed_delta {fixed_delta:.6f} s), "
          f"duration cap {args.duration_s} s, mount {location} {rotation}")

    stop = {"stop": False}

    def _handle_signal(signum, frame):
        # Teardown SIGTERMs this client BEFORE it stops CARLA, so the loop must
        # exit through run_sync_loop's `finally` (which restores the world's
        # prior settings) and through this function's own actor destroy, while
        # the server is still alive. A client left ticking a dead server hangs
        # on actor destroy -- this repo's documented teardown gotcha.
        stop["stop"] = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    client = carla.Client(args.host, args.port)
    client.set_timeout(20.0)
    world = client.get_world()

    if args.initial_pose:
        x, y, z, roll, pitch, yaw = args.initial_pose
        spawn = carla.Transform(
            carla.Location(x=x, y=y, z=z), carla.Rotation(roll=roll, pitch=pitch, yaw=yaw)
        )
    else:
        spawn_points = world.get_map().get_spawn_points()
        if not 0 <= args.spawn_index < len(spawn_points):
            raise IndexError(
                f"--spawn-index {args.spawn_index} out of range; the map has "
                f"{len(spawn_points)} spawn points"
            )
        spawn = spawn_points[args.spawn_index]

    blueprints = world.get_blueprint_library()
    ego_bp = blueprints.find(args.ego_blueprint)
    # role_name only: NOT `ros2_ackermann_control` (the ego is a stationary
    # carrier here, and opting into a native control sink would be one more
    # ROS path in a run whose whole point is that none are active).
    ego_bp.set_attribute("role_name", "ego")
    ego = world.spawn_actor(ego_bp, spawn)

    lidar_bp = blueprints.find(TOP_LIDAR_BLUEPRINT)
    for key, value in attrs.items():
        # Unconditional, no has_attribute() skip: every attribute in both rigs
        # is stock LiDAR geometry (the native-ROS2 discriminators are exactly
        # what _ros_free removed), so a missing one is a real blueprint
        # mismatch and must surface as CARLA's own named set_attribute error
        # rather than being silently dropped from the workload.
        lidar_bp.set_attribute(key, value)
    lidar = world.spawn_actor(
        lidar_bp,
        carla.Transform(
            carla.Location(x=location[0], y=location[1], z=location[2]),
            carla.Rotation(roll=rotation[0], pitch=rotation[1], yaw=rotation[2]),
        ),
        attach_to=ego,
    )

    sink = NullSink()
    # THE RPC HOP (see the module docstring's disclosed limitation): a CARLA
    # sensor only raycasts while a client is subscribed to its stream, so this
    # subscription is what makes the baseline measure anything at all -- and it
    # ships every cloud to this process, which the native in-process publisher
    # does not do.
    lidar.listen(sink)

    clock = ClockCsvWriter(Path(args.out_dir) / "clock.csv")
    clock.open()
    started_ns = time.time_ns()
    deadline = time.monotonic() + args.duration_s
    ticks = 0
    sim_ns: list[int] = []

    def _on_tick() -> None:
        nonlocal ticks
        ticks += 1
        snapshot = world.get_snapshot()
        clock_ns = int(snapshot.timestamp.elapsed_seconds * 1e9)
        sim_ns.append(clock_ns)
        clock.write(clock_ns, time.time_ns())

    def _should_continue() -> bool:
        return not stop["stop"] and time.monotonic() < deadline

    try:
        run_sync_loop(
            world,
            fixed_delta=fixed_delta,
            on_tick=_on_tick,
            should_continue=_should_continue,
            paced=True,
        )
    finally:
        clock.close()
        # Best effort, in this order, and never allowed to mask the original
        # failure: stop the stream, destroy the sensor, destroy the ego.
        for label, fn in (
            ("lidar.stop", lidar.stop),
            ("lidar.destroy", lidar.destroy),
            ("ego.destroy", ego.destroy),
        ):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 - teardown must not raise
                print(f"raycast_baseline: {label} failed during teardown: {exc}", file=sys.stderr)
        summary = {
            "rig": args.rig,
            "class_id": args.class_id,
            "attributes": attrs,
            "ego_blueprint": args.ego_blueprint,
            "lidar_blueprint": TOP_LIDAR_BLUEPRINT,
            "mount_location_m": list(location),
            "mount_rotation_deg": list(rotation),
            "tick_hz": args.tick_hz,
            "fixed_delta_s": fixed_delta,
            "duration_cap_s": args.duration_s,
            "ticks": ticks,
            "clock_rows_written": clock.rows,
            "sensor_callbacks": sink.count,
            "started_system_ns": started_ns,
            "ended_system_ns": time.time_ns(),
            "sim_span_ns": (max(sim_ns) - min(sim_ns)) if sim_ns else 0,
            "stopped_by_signal": stop["stop"],
        }
        _summary_path(args.out_dir).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(
            f"raycast_baseline: {ticks} ticks, {sink.count} sensor callbacks, "
            f"{clock.rows} clock rows -> {_summary_path(args.out_dir)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
