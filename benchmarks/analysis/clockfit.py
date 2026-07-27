"""Least-squares affine mapping from simulation time to wall time.

Fitted per run over every /clock receipt; committed with the raw data so
sim-time and wall-time latencies are never mixed (spec: Metrics preamble).

Timestamps arrive as absolute nanosecond epochs (~1.7e18), which exceeds
float64's exact-integer range (2**53 ~= 9e15): converting to float64 before
centering already quantizes the data to ~256 ns steps, corrupting the fit
before least squares even runs. So we shift by the first sample in the
input's own dtype (exact for int64 ns) *before* converting to float64, fit
in that shifted domain, and fold the shift back into the absolute intercept.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AffineFit:
    slope: float  # wall ns advanced per sim ns (1/RTF)
    intercept_ns: float
    max_abs_residual_ns: float
    n: int


def fit_sim_wall_affine(sim_ns, wall_ns) -> AffineFit:
    x = np.asarray(sim_ns)
    y = np.asarray(wall_ns)
    if x.size != y.size or x.size < 2:
        raise ValueError("need >= 2 paired (sim, wall) samples")
    # Shift in the input's own dtype first: exact for int64 ns epochs,
    # unlike centering after a float64 cast (see module docstring).
    x0, y0 = x[0], y[0]
    xf = (x - x0).astype(np.float64)
    yf = (y - y0).astype(np.float64)
    xm, ym = xf.mean(), yf.mean()
    slope = float(np.dot(xf - xm, yf - ym) / np.dot(xf - xm, xf - xm))
    b = float(ym - slope * xm)
    # Fold the shift back in: absolute, so sim_to_wall stays correct.
    intercept = b + float(y0) - slope * float(x0)
    resid = yf - (slope * xf + b)
    return AffineFit(slope, intercept, float(np.max(np.abs(resid))), int(x.size))


def sim_to_wall(fit: AffineFit, sim_ns):
    return fit.slope * np.asarray(sim_ns, dtype=np.float64) + fit.intercept_ns
