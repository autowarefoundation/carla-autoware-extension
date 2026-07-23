from __future__ import annotations
import argparse
import re
import sys


def rate_in_band(measured_hz: float, target: float, tol: float) -> bool:
    """A rate passes only inside [target-tol, target+tol]. This deliberately fails
    the ~70-84 Hz free-running headless case: 20 Hz must be a real cadence produced by
    the runner's real-time pacing, not wall-clock liveness."""
    return (target - tol) <= measured_hz <= (target + tol)


def parse_hz(text: str):
    """Pull the last 'average rate:' from `ros2 topic hz` output; None if none present."""
    m = re.findall(r"average rate:\s*([0-9]+\.?[0-9]*)", text)
    return float(m[-1]) if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hz-file", required=True, help="captured `ros2 topic hz` output")
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--tol", type=float, required=True)
    ap.add_argument("--label", default="rate")
    a = ap.parse_args()
    hz = parse_hz(open(a.hz_file).read())
    ok = hz is not None and rate_in_band(hz, a.target, a.tol)
    shown = f"{hz:.2f}" if hz is not None else "none"
    print(
        f"G3 {a.label}: measured={shown} Hz target={a.target}+-{a.tol} Hz -> {'PASS' if ok else 'FAIL'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
