"""Phase B live runner CLI: connect to CARLA, load the map, spawn the ego + sensor rig, run
the tick loop, and clean up on exit.

Import discipline: ``carla`` is imported lazily INSIDE ``main()``, after both the
``--extension-check`` early return and the kit-yaml existence preflight, so this module stays
importable -- and its argument parsing / preflight paths stay testable -- under bare pytest
with no CARLA egg installed (the M0 CI lesson; see ``runner/spawn.py`` for the same rule on
the spawn side).
"""

from __future__ import annotations

import argparse
import os
import signal
import sys

from runner.kit import DEFAULT_SENSOR_KIT_CALIBRATION, DEFAULT_SENSORS_CALIBRATION, load_kit
from runner.loop import extension_exports_init, run_async_loop, run_sync_loop
from runner.spawn import spawn_ego, spawn_sensors


def _brake_to_stop(ego) -> None:
    """Best-effort full-brake before teardown.

    CARLA control latches in async mode (CLAUDE.md operational gotcha): without this the ego
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


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runner", description="Phase B CARLA spawn + tick runner")
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
        "default = map spawn point 0",
    )
    p.add_argument(
        "--async",
        dest="async_mode",
        action="store_true",
        help="run the async tick loop (validated fallback: CARLA 0.10/Chaos vehicles do not "
        "propel in synchronous mode in this build)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.extension_check:
        # Standalone preflight mode: scripts/phase_b/run_phase_b.sh runs this BEFORE booting
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

    # carla is imported here, lazily -- everything above this line (arg parsing, the
    # --extension-check path, the kit-yaml preflight + parse) must stay importable and
    # runnable with no CARLA egg installed (bare `pytest tests/`, the M0 CI lesson).
    import carla

    client = carla.Client(args.host, args.port)
    client.set_timeout(30.0)
    world = client.get_world()
    if args.map not in world.get_map().name:  # the harness may already have loaded it
        world = client.load_world(args.map)

    # Autoware owns the localization TF tree: suppress ALL CARLA-side ROS 2 TF (Task 8) BEFORE
    # spawning any actor, so map->odom->base_link is never double-published on /tf alongside
    # the Autoware-side TF that Autoware itself generates from these same kit yamls.
    world.set_publish_tf(False)

    bpl = world.get_blueprint_library()
    if args.initial_pose:
        x, y, z, roll, pitch, yaw = args.initial_pose
        pose = carla.Transform(
            carla.Location(x=x, y=y, z=z), carla.Rotation(roll=roll, pitch=pitch, yaw=yaw)
        )
    else:
        pose = world.get_map().get_spawn_points()[0]

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
        sensors = spawn_sensors(world, bpl, ego, kit)

        loop = run_async_loop if args.async_mode else run_sync_loop
        loop(world, should_continue=lambda: stop["go"])
        return 0
    finally:
        # Teardown order is load-bearing (CLAUDE.md operational gotcha): brake to a stop
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
