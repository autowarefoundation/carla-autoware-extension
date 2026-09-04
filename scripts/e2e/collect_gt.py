#!/usr/bin/env python3
"""Collect the host-side CARLA ground-truth series for the E2E gates.

`gate_g1_localization.sh` and `gate_g2_closed_loop.sh` used to inline this
logic as per-gate heredocs, each re-typing the map-frame constants by hand.
This module replaces them so that:

* the CARLA->map conversion is imported from ``map_frame`` -- the single
  pinned source, byte-identical to upstream's ``run_carla_autoware.sh``
  GATE1 constants -- instead of drifting as inline literals, and
* the ego discovery / mapping / distance logic is unit-testable
  (``tests/e2e/test_collect_gt.py``).

Output formats (kept identical to the old heredocs):

* default: one ``"<t> <map_x> <map_y>"`` row per sample (G1 ground truth),
  sampled every 0.05 s, ``gt_rows=N`` printed at the end.
* ``--goal X Y``: one ``"<distance_m>"`` row per sample (G2 ego-to-goal),
  sampled every 0.1 s, ``dist_rows=N`` printed at the end.

Rows are on the base_link (rear axle) basis, matching what upstream's GATE1
publishes as the NDT pose and expects as the goal -- not the CARLA actor
origin.

Import discipline: ``carla`` is imported lazily inside ``main()`` only, so
this module imports under bare pytest with no CARLA egg, which is how CI runs
it. The gate scripts invoke it as ``python3 -m scripts.e2e.collect_gt`` with
``PYTHONPATH`` including the repo root.
"""

from __future__ import annotations

import argparse
import math
import sys
import time

from scripts.e2e.map_frame import REAR_AXLE_OFFSET_M, carla_to_map, parse_origin, rear_axle


def ego_map_xy(
    x_m: float,
    y_m: float,
    yaw_deg: float,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rear_axle_offset: float = REAR_AXLE_OFFSET_M,
) -> tuple[float, float]:
    """CARLA PythonAPI ego pose (metres, degrees) -> map-frame base_link XY (metres).

    Shifts the CARLA actor origin back to the rear axle (Autoware's
    base_link) before applying the CARLA->map affine, so this matches what
    upstream's NDT pose estimator and goal both use.
    """
    bx, by = rear_axle(x_m, y_m, yaw_deg, rear_axle_offset)
    mx, my, _ = carla_to_map(bx, by, 0.0, origin)
    return (mx, my)


def goal_distance(
    x_m: float,
    y_m: float,
    yaw_deg: float,
    goal_x: float,
    goal_y: float,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    rear_axle_offset: float = REAR_AXLE_OFFSET_M,
) -> float:
    """XY distance (metres) from the ego's base_link to a map-frame goal.

    ``goal_x``/``goal_y`` are already in the map frame (the gate scripts pass
    the goal that way), so only the ego side is converted here -- the origin
    is applied exactly once.
    """
    mx, my = ego_map_xy(x_m, y_m, yaw_deg, origin, rear_axle_offset)
    return math.hypot(mx - goal_x, my - goal_y)


def find_ego(world, attempts: int = 100, delay_s: float = 0.1, sleep=time.sleep):
    """Return the ego actor (``role_name == "ego"``), retrying while it spawns.

    A cold client in sync mode can read an empty snapshot before the first
    tick (the ``StopIteration`` race fixed in the gate scripts), so the caller
    must ``world.wait_for_tick()`` once before calling this; the retry loop
    here then covers the runner still being mid-spawn.
    """
    for _ in range(attempts):
        try:
            return next(
                a
                for a in world.get_actors().filter("vehicle.*")
                if a.attributes.get("role_name") == "ego"
            )
        except StopIteration:
            sleep(delay_s)
    raise RuntimeError("no ego actor found after warm-up retries")


def main(argv: list[str] | None = None, world_factory=None) -> int:
    """Parse argv, collect a sample series, write it to ``--out``.

    ``world_factory`` is a test seam: a zero-arg callable returning a
    ``carla.World``-shaped object (must provide ``wait_for_tick`` and
    ``get_actors``). Left as ``None`` (the CLI default), it lazily imports
    ``carla`` and connects to ``--host``/``--port``, preserving the import
    discipline documented at module level. Tests inject a fake world here
    instead of needing a live simulator.
    """
    p = argparse.ArgumentParser(description="CARLA ground-truth series collector")
    p.add_argument("--window", type=float, required=True, help="collection window, seconds")
    p.add_argument("--out", required=True, help="output file (one row per sample)")
    p.add_argument(
        "--goal",
        nargs=2,
        type=float,
        default=None,
        metavar=("MAP_X", "MAP_Y"),
        help="emit ego-to-goal distances (map frame, metres) instead of t/x/y rows",
    )
    p.add_argument(
        "--map-origin",
        default="",
        help='"X,Y,Z" map origin in metres (Local projector: omit; '
        "Nishi-Shinjuku: 81655.73,50137.43,42.49998)",
    )
    p.add_argument("--rear-axle-offset", type=float, default=REAR_AXLE_OFFSET_M)
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2000)
    args = p.parse_args(argv)

    origin = parse_origin(args.map_origin)

    if world_factory is None:

        def world_factory():
            import carla

            return carla.Client(args.host, args.port).get_world()

    world = world_factory()
    try:
        world.wait_for_tick(10.0)  # sync mode: a cold client sees an empty snapshot until ticked
    except RuntimeError:
        pass  # upstream's autoware_demo.py drives the tick; a second client must not tick
    ego = find_ego(world)

    period = 0.1 if args.goal else 0.05
    end = time.time() + args.window
    rows: list[str] = []
    while time.time() < end:
        tf = ego.get_transform()
        x, y, yaw = tf.location.x, tf.location.y, tf.rotation.yaw
        if args.goal:
            d = goal_distance(x, y, yaw, args.goal[0], args.goal[1], origin, args.rear_axle_offset)
            rows.append(f"{d:.4f}")
        else:
            mx, my = ego_map_xy(x, y, yaw, origin, args.rear_axle_offset)
            rows.append(f"{time.time():.3f} {mx:.4f} {my:.4f}")
        time.sleep(period)

    with open(args.out, "w") as f:
        f.write("\n".join(rows) + "\n")
    print(f"{'dist_rows' if args.goal else 'gt_rows'}={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
