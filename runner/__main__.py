"""Live runner CLI: connect to CARLA, load the map, spawn the ego + sensor rig, run
the tick loop, and clean up on exit.

Import discipline: ``carla`` is imported lazily INSIDE ``main()``, after both the
``--extension-check`` early return and the kit-yaml existence preflight, so this module stays
importable -- and its argument parsing / preflight paths stay testable -- under bare pytest
with no CARLA egg installed, which is how CI runs it (see ``runner/spawn.py`` for the same
rule on the spawn side).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

from runner.kit import DEFAULT_SENSOR_KIT_CALIBRATION, DEFAULT_SENSORS_CALIBRATION, load_kit
from runner.loop import (
    DEFAULT_FIXED_DELTA,
    apply_substep_config,
    extension_exports_init,
    load_physics_config,
    run_async_loop,
    run_sync_loop,
)
from runner.spawn import (
    CAMERA_DEFAULT_HEIGHT,
    CAMERA_DEFAULT_SENSOR_TICK,
    CAMERA_DEFAULT_WIDTH,
    spawn_cameras,
    spawn_ego,
    spawn_sensors,
)


def _brake_to_stop(ego) -> None:
    """Best-effort full-brake before teardown.

    CARLA control latches in async mode: without this the ego
    would coast away on the LAST applied control after the runner process exits. This runs
    from a ``finally`` during a SIGINT/exception unwind, so it swallows every exception itself
    -- a secondary failure here (e.g. the actor already invalid) must never mask the original
    error or skip the sensor/ego destroy calls that follow it.
    """
    try:
        import carla

        ego.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0))
    except Exception:
        pass


def select_spawn_point(spawn_points, index: int):
    """Pick a recommended spawn point by index, or raise with the valid range.

    Split out of ``main()`` so the range check is unit-testable with a plain list
    and no CARLA egg. It fails with the map's actual spawn-point count because by
    the time ``main()`` gets here the map is already loaded -- an opaque
    ``IndexError`` would have cost a full editor boot and still not say what to
    pick instead.
    """
    if not 0 <= index < len(spawn_points):
        raise IndexError(
            f"--spawn-index {index} out of range; the map has {len(spawn_points)} spawn points"
        )
    return spawn_points[index]


def build_lidar_overrides(args: argparse.Namespace) -> dict[str, str]:
    """Build the top-LiDAR attribute-overrides dict from the ``--lidar-*`` CLI flags.

    Split out of ``main()`` so the flag -> override-key mapping is unit-testable without a
    CARLA connection (same rationale as ``select_spawn_point``). Only a flag the caller
    actually passed (non-None) becomes a key -- an omitted flag must NOT appear in the
    dict, so ``top_lidar_attributes(overrides=build_lidar_overrides(args))`` reproduces
    today's exact dict when no ``--lidar-*`` flag is given (the regression pin).
    """
    overrides: dict[str, str] = {}
    if args.lidar_channels is not None:
        overrides["channels"] = str(args.lidar_channels)
    if args.lidar_pps is not None:
        overrides["points_per_second"] = str(args.lidar_pps)
    if args.lidar_rotation_hz is not None:
        overrides["rotation_frequency"] = str(args.lidar_rotation_hz)
    if args.lidar_range is not None:
        overrides["range"] = str(args.lidar_range)
    return overrides


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runner", description="CARLA ego/sensor spawn + tick runner")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2000)
    p.add_argument("--map", default="NishishinjukuMap")
    p.add_argument(
        "--sensor-kit-calibration",
        default=DEFAULT_SENSOR_KIT_CALIBRATION,
        help="sensor_kit_calibration.yaml (sensor_kit_base_link -> each sensor); "
        "defaults to the committed copy under runner/config/",
    )
    p.add_argument(
        "--sensors-calibration",
        default=DEFAULT_SENSORS_CALIBRATION,
        help="sensors_calibration.yaml (base_link -> sensor_kit_base_link); "
        "defaults to the committed copy under runner/config/",
    )
    p.add_argument(
        "--extension-so", default="", help="path to the built libcarla-autoware-extension.so"
    )
    p.add_argument(
        "--extension-check",
        action="store_true",
        help="preflight only: verify --extension-so exports carla_ros2_extension_init, "
        "print the result, and exit without connecting to CARLA",
    )
    p.add_argument(
        "--initial-pose",
        nargs=6,
        type=float,
        default=None,
        metavar=("X_M", "Y_M", "Z_M", "ROLL_DEG", "PITCH_DEG", "YAW_DEG"),
        # CARLA PythonAPI carla.Location/Rotation are METRES/degrees, NOT the UE-native
        # centimetres the extension .so sees at the C++ boundary (docs/mgrs-handedness.md
        # "Units caveat") -- this flag feeds carla.Transform directly, so it takes metres.
        help="ego spawn pose in CARLA world coordinates (metres, degrees); "
        "default = the spawn point selected by --spawn-index",
    )
    p.add_argument(
        "--spawn-index",
        type=int,
        default=0,
        # Nishi-Shinjuku exposes exactly ONE spawn point, so this stayed implicit;
        # the CARLA town maps expose dozens, and picking one by index keeps the
        # ego ON a recommended spawn (hence on the road network and clear of
        # geometry), which a hand-typed --initial-pose does not guarantee.
        # --initial-pose, when given, wins: it is the more specific request.
        help="index into world.get_map().get_spawn_points(); ignored when "
        "--initial-pose is given (default: 0)",
    )
    p.add_argument(
        "--async",
        dest="async_mode",
        action="store_true",
        help="run the async tick loop. NOT the G2 path: the sync ego does propel given a "
        "valid drive command (445 m closed-loop drive, 2026-07-23), while async breaks NDT "
        "(0/34 samples within 1.0 m under a ~140 Hz free-running /clock)",
    )

    # --- M4 knobs: sweep-class, camera, pacing, substepping (spec: M4 load sweep) ---
    # Every default below preserves today's exact rig/loop/physics behaviour: an omitted
    # flag must leave the Nishi/Town10 gates byte-identical (see
    # runner/spawn.py::top_lidar_attributes / runner/loop.py::run_sync_loop for the pins).
    p.add_argument(
        "--lidar-channels",
        type=int,
        default=None,
        help="override the top LiDAR's channels attribute (unset: today's 128); "
        "benchmarks/config/cells.yaml sweep_classes: vlp16=16, 32ch=32, 128ch=128",
    )
    p.add_argument(
        "--lidar-pps",
        type=int,
        default=None,
        help="override the top LiDAR's points_per_second attribute (unset: the "
        "sensor.lidar.ray_cast blueprint default, 600000); sweep_classes: vlp16=288000, "
        "32ch=1200000, 128ch=4600000",
    )
    p.add_argument(
        "--lidar-rotation-hz",
        type=float,
        default=None,
        help="override the top LiDAR's rotation_frequency attribute, Hz (unset: today's 10)",
    )
    p.add_argument(
        "--lidar-range",
        type=float,
        default=None,
        help="override the top LiDAR's range attribute, metres (unset: today's 120.0)",
    )
    p.add_argument(
        "--cameras",
        type=int,
        default=0,
        help="number of native ROS 2 cameras to spawn, indexed "
        "/sensing/camera/camera<N>/image_raw (default: 0, no cameras -- today's exact rig)",
    )
    p.add_argument(
        "--camera-width",
        type=int,
        default=CAMERA_DEFAULT_WIDTH,
        help=f"camera image_size_x, pixels (default: {CAMERA_DEFAULT_WIDTH}, matches "
        "cam1/cam3/cam6)",
    )
    p.add_argument(
        "--camera-height",
        type=int,
        default=CAMERA_DEFAULT_HEIGHT,
        help=f"camera image_size_y, pixels (default: {CAMERA_DEFAULT_HEIGHT}, matches "
        "cam1/cam3/cam6)",
    )
    p.add_argument(
        "--camera-tick",
        type=float,
        default=CAMERA_DEFAULT_SENSOR_TICK,
        help=f"camera sensor_tick, seconds (default: {CAMERA_DEFAULT_SENSOR_TICK} = 20 fps, "
        "the tick ceiling -- a higher request is silently clamped, P1 Verdict 4)",
    )
    p.add_argument(
        "--fixed-delta",
        type=float,
        default=DEFAULT_FIXED_DELTA,
        help=f"world fixed_delta_seconds, seconds (default: {DEFAULT_FIXED_DELTA}, today's "
        "exact cadence); for A-hf, pass 0.01",
    )
    p.add_argument(
        "--unpaced",
        action="store_true",
        help="tick as fast as possible: skip the tick loop's real-time pacing sleep. Sync "
        "mode itself is unchanged -- only the wall-clock throttle is skipped",
    )
    p.add_argument(
        "--substep-config",
        default=None,
        help="path to a physics.yaml (benchmarks/config/physics.yaml schema: "
        "max_substep_delta_time, max_substeps); applied to world settings before the run "
        "when given (default: unset, today's CARLA physics-substep defaults)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.extension_check:
        # Standalone preflight mode: scripts/e2e/run_e2e.sh runs this BEFORE booting
        # CARLA, so a missing/stale extension .so fails here in ~0s with a named, actionable
        # message instead of ~20s into an editor boot with only a buried --ros2-extension= log
        # line to go on.
        if not args.extension_so or not extension_exports_init(args.extension_so):
            print(
                f"PREFLIGHT FAIL: extension .so {args.extension_so!r} missing or does not "
                "export carla_ros2_extension_init",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {args.extension_so} exports carla_ros2_extension_init")
        return 0

    for flag, path in (
        ("--sensor-kit-calibration", args.sensor_kit_calibration),
        ("--sensors-calibration", args.sensors_calibration),
    ):
        if not os.path.isfile(path):
            print(f"PREFLIGHT FAIL: {flag} {path!r} does not exist", file=sys.stderr)
            return 1

    # Parse the kit yamls before touching CARLA at all: a malformed calibration file should
    # fail fast here, not after a 20s+ connect/map-load round trip.
    kit = load_kit(
        sensor_kit_calibration=args.sensor_kit_calibration,
        sensors_calibration=args.sensors_calibration,
    )
    lidar_overrides = build_lidar_overrides(args)

    # carla is imported here, lazily -- everything above this line (arg parsing, the
    # --extension-check path, the kit-yaml preflight + parse) must stay importable and
    # runnable with no CARLA egg installed (bare `pytest tests/`, as CI runs it).
    import carla

    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    world = client.get_world()
    if args.map not in world.get_map().name:  # the harness may already have loaded it
        world = client.load_world(args.map)

    # Autoware owns the localization TF tree: suppress ALL CARLA-side ROS 2 TF BEFORE
    # spawning any actor, so map->odom->base_link is never double-published on /tf alongside
    # the Autoware-side TF that Autoware itself generates from these same kit yamls.
    world.set_publish_tf(False)

    # --substep-config: physics substepping parity (A-hf/tier4 comparison), applied to world
    # settings before any actor spawns or the tick loop starts. Unset (the default) leaves
    # CARLA's own physics-substep defaults untouched -- today's exact behaviour.
    if args.substep_config:
        apply_substep_config(world, load_physics_config(args.substep_config))

    bpl = world.get_blueprint_library()
    if args.initial_pose:
        x, y, z, roll, pitch, yaw = args.initial_pose
        pose = carla.Transform(
            carla.Location(x=x, y=y, z=z), carla.Rotation(roll=roll, pitch=pitch, yaw=yaw)
        )
    else:
        try:
            pose = select_spawn_point(world.get_map().get_spawn_points(), args.spawn_index)
        except IndexError as exc:
            print(f"PREFLIGHT FAIL: {exc} ({args.map})", file=sys.stderr)
            return 1

    stop = {"go": True}
    signal.signal(signal.SIGINT, lambda *_: stop.update(go=False))  # Ctrl-C -> graceful stop

    # ego/sensors start as "nothing spawned yet" and are spawned INSIDE the try below (not
    # before it): division of labor against a mid-spawn failure is split across two layers.
    # This try/finally guards the EGO leak -- if spawn_sensors raises, the ego is ALREADY
    # spawned by the time we get here, and this finally is the only place that destroys it
    # (spawn_sensors never receives the ego pointer to destroy). spawn_sensors itself is
    # partial-spawn-safe (runner/spawn.py): on its OWN internal exception it destroys any
    # sensor actor(s) it had already spawned in that call before re-raising, so by the time
    # the exception reaches here ``sensors`` is guaranteed to still be ``[]`` -- the loop below
    # finding nothing to destroy in that case is therefore correct, not a coverage gap.
    ego = None
    sensors = []
    try:
        ego = spawn_ego(world, bpl, pose)
        sensors = spawn_sensors(world, bpl, ego, kit, lidar_overrides=lidar_overrides)
        # --cameras (default 0): a SEPARATE fan-out from the LiDAR/IMU rig above, appended to
        # the SAME teardown list -- spawn_cameras is its own partial-spawn-safe call (see its
        # docstring), so if it raises after spawn_sensors already succeeded, `sensors` still
        # holds exactly the LiDAR/IMU actors and this `+=` never executes.
        sensors += spawn_cameras(
            world,
            bpl,
            ego,
            args.cameras,
            args.camera_width,
            args.camera_height,
            args.camera_tick,
        )

        loop = run_async_loop if args.async_mode else run_sync_loop
        loop(
            world,
            fixed_delta=args.fixed_delta,
            should_continue=lambda: stop["go"],
            paced=not args.unpaced,
        )
        return 0
    finally:
        # Teardown order is load-bearing: brake to a stop
        # FIRST -- control latches in async mode, so an un-braked ego coasts away once this
        # process exits -- THEN destroy sensors, THEN the ego, all inside this finally so a
        # SIGINT or an exception anywhere above (spawn OR the tick loop) never leaks actors or
        # leaves duplicate ROS 2 publishers behind for the next run. Each step is guarded so a
        # not-yet-spawned ego (None) or a partially-populated sensors list is handled safely.
        if ego is not None:
            _brake_to_stop(ego)
        for sensor in sensors:
            try:
                sensor.destroy()
            except Exception:
                pass
        if ego is not None:
            try:
                ego.destroy()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
