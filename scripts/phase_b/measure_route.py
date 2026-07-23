from __future__ import annotations
import argparse
import sys


def route_completed(goal_distances_m: list[float], goal_tol_m: float) -> bool:
    """G2 passes iff the ego reaches within goal_tol_m of the goal at any sample."""
    return bool(goal_distances_m) and min(goal_distances_m) <= goal_tol_m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--distances",
        required=True,
        help="file of goal-distance samples (metres, whitespace-separated)",
    )
    ap.add_argument("--goal-tol-m", type=float, default=1.0)
    a = ap.parse_args()
    dists = [float(x) for x in open(a.distances).read().split()]
    ok = route_completed(dists, a.goal_tol_m)
    closest = min(dists) if dists else float("nan")
    print(
        f"G2 route: samples={len(dists)} closest_approach={closest:.3f} m "
        f"tol={a.goal_tol_m} m -> {'PASS' if ok else 'FAIL'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
