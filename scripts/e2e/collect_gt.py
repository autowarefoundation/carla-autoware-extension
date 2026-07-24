#!/usr/bin/env python3
"""Collect the host-side CARLA ground-truth series for the E2E gates.

`gate_g1_localization.sh` and `gate_g2_closed_loop.sh` used to inline this
logic as per-gate heredocs, each re-typing the MGRS affine constants by hand.
This module replaces them so that:

* the CARLA->MGRS mapping is imported from ``verify_mgrs_handedness`` -- the
  single pinned source, byte-identical to the extension's ``MgrsOffset.h`` --
  instead of drifting as inline literals, and
* the ego discovery / mapping / distance logic is unit-testable
  (``tests/e2e/test_collect_gt.py``).

Output formats (kept identical to the old heredocs):

* default: one ``"<t> <mgrs_x> <mgrs_y>"`` row per sample (G1 ground truth),
  sampled every 0.05 s, ``gt_rows=N`` printed at the end.
* ``--goal X Y``: one ``"<distance_m>"`` row per sample (G2 ego-to-goal),
  sampled every 0.1 s, ``dist_rows=N`` printed at the end.

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

from scripts.e2e.verify_mgrs_handedness import world_m_to_mgrs_local


def ego_map_xy(x_m: float, y_m: float) -> tuple[float, float]:
    """CARLA PythonAPI ego position (metres) -> MGRS-local map XY (metres).

    CARLA reports metres; the map frame is the MGRS-local converter frame
    (single Y flip + offset). This is a pure affine wrapper so the gates share
    one mapping with the transform verifier and the extension.
    """
    mgrs_x, mgrs_y, _ = world_m_to_mgrs_local(x_m, y_m, 0.0)
    return (mgrs_x, mgrs_y)


def goal_distance(x_m: float, y_m: float, goal_x: float, goal_y: float) -> float:
    """XY distance (metres) from a CARLA ego position to a map-frame goal."""
    mgrs_x, mgrs_y = ego_map_xy(x_m, y_m)
    return math.hypot(mgrs_x - goal_x, mgrs_y - goal_y)


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


def main(argv: list[str] | None = None) -> int:
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
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2000)
    args = p.parse_args(argv)

    import carla

    world = carla.Client(args.host, args.port).get_world()
    world.wait_for_tick()  # sync mode: a cold client sees an empty snapshot until ticked
    ego = find_ego(world)

    period = 0.1 if args.goal else 0.05
    end = time.time() + args.window
    rows: list[str] = []
    while time.time() < end:
        loc = ego.get_transform().location
        if args.goal:
            rows.append(f"{goal_distance(loc.x, loc.y, args.goal[0], args.goal[1]):.4f}")
        else:
            mgrs_x, mgrs_y = ego_map_xy(loc.x, loc.y)
            rows.append(f"{time.time():.3f} {mgrs_x:.4f} {mgrs_y:.4f}")
        time.sleep(period)

    with open(args.out, "w") as f:
        f.write("\n".join(rows) + "\n")
    print(f"{'dist_rows' if args.goal else 'gt_rows'}={len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
