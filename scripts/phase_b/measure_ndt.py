from __future__ import annotations
import argparse, sys

def ndt_pass(errors_m: list[float], max_err_m: float) -> bool:
    """G1 passes iff we got NDT poses AND every error stays under the threshold.
    An empty stream is a FAIL (the estimator never locked / never published)."""
    if not errors_m:
        return False
    return max(errors_m) <= max_err_m

def _load_series(path):
    """Each line: '<t> <x> <y>' (seconds, metres). Returns list[(t,x,y)]."""
    out = []
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) >= 3:
                out.append((float(p[0]), float(p[1]), float(p[2])))
    return out

def errors_from_series(ndt, gt):
    """Per NDT sample, nearest-in-time ground-truth; Euclidean XY error (metres)."""
    errs = []
    for tn, xn, yn in ndt:
        tg, xg, yg = min(gt, key=lambda g: abs(g[0] - tn))
        errs.append(((xn - xg) ** 2 + (yn - yg) ** 2) ** 0.5)
    return errs

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ndt", required=True, help="NDT pose series file (t x y)")
    ap.add_argument("--gt", required=True, help="CARLA ground-truth series file (t x y)")
    ap.add_argument("--max-err-m", type=float, default=0.5)
    a = ap.parse_args()
    ndt, gt = _load_series(a.ndt), _load_series(a.gt)
    errs = errors_from_series(ndt, gt) if (ndt and gt) else []
    ok = ndt_pass(errs, a.max_err_m)
    mx = max(errs) if errs else float("nan")
    print(f"G1 NDT: ndt_samples={len(ndt)} gt_samples={len(gt)} "
          f"max_err={mx:.3f} m threshold={a.max_err_m} m -> {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
