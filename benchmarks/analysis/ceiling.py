"""Pre-registered M4 sustainable-load ceiling criterion (spec: M4).

The spec pre-registers FOUR disjuncts, applied identically to every sweep
point: sustained RTF < 0.9 for 10 s; on the UNPACED arm, sustained ticks/s
< 90% of the paced target; pointcloud publisher-side rate < 90% of expected;
or the M5 quality gate fails. The first two are per-sample series scored with
the same sustain rule, the third is a run-level scalar, and each is a separate
input here so a verdict always says which one fired.

A paced arm passes `rtf` and leaves `tick_rate_ratio` unset; an unpaced arm
does the reverse (its RTF carries no headroom information -- that is why the
spec substitutes ticks/s there). A point that measures both may pass both.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class CeilingVerdict:
    reached: bool
    reasons: list[str] = field(default_factory=list)


def _as_series(t: np.ndarray, values, name: str) -> np.ndarray:
    v = np.asarray(values, dtype=np.float64)
    if t.size != v.size:
        raise ValueError(f"sample_system_ns and {name} length mismatch: {t.size} != {v.size}")
    return v


def _sustained_below(t: np.ndarray, values: np.ndarray, threshold: float, sustain_s: float) -> bool:
    """True once `values` stays under `threshold` for `sustain_s` of sample time.

    The window opens at the first sample below the threshold and is reset by
    any sample at or above it, so a dip counts only while it is unbroken.
    Elapsed time comes from the sample timestamps, never from a sample count,
    so a non-uniform sampling grid scores the same as a uniform one.
    """
    below = values < threshold
    start = None
    for k in range(t.size):
        if below[k]:
            if start is None:
                start = t[k]
            elif (t[k] - start) / 1e9 >= sustain_s:
                return True
        else:
            start = None
    return False


def evaluate_ceiling(
    sample_system_ns,
    rtf,
    publisher_rate_ratio: float,
    quality_ok: bool,
    rtf_threshold: float = 0.9,
    sustain_s: float = 10.0,
    rate_threshold: float = 0.9,
    tick_rate_ratio=None,
    tick_rate_threshold: float = 0.9,
) -> CeilingVerdict:
    """Score one sweep point against the pre-registered ceiling criterion.

    Args:
        sample_system_ns: per-sample wall timestamps (the series' time base).
        rtf: per-sample sim/wall rate on a PACED arm, or None on an arm where
            RTF is not a saturation signal (the unpaced arm).
        publisher_rate_ratio: pointcloud publisher-side rate as a fraction of
            expected -- publisher-side, so observer loss cannot fake a ceiling.
        quality_ok: the M5 closed-loop quality gate's verdict for this point.
        tick_rate_ratio: per-sample ticks/s as a fraction of the PACED target,
            the unpaced arm's substitute for RTF, or None if not measured.

    At least one of `rtf` / `tick_rate_ratio` must be given: with neither, the
    sustained-throughput disjunct goes unevaluated and a silent "not reached"
    would misreport the point.
    """
    t = np.asarray(sample_system_ns, dtype=np.int64)
    if rtf is None and tick_rate_ratio is None:
        raise ValueError("need rtf (paced arm) or tick_rate_ratio (unpaced arm), got neither")
    reasons = []

    if rtf is not None:
        r = _as_series(t, rtf, "rtf")
        if _sustained_below(t, r, rtf_threshold, sustain_s):
            reasons.append(f"rtf<{rtf_threshold} sustained >= {sustain_s}s")

    if tick_rate_ratio is not None:
        tr = _as_series(t, tick_rate_ratio, "tick_rate_ratio")
        if _sustained_below(t, tr, tick_rate_threshold, sustain_s):
            reasons.append(
                f"unpaced tick rate ratio<{tick_rate_threshold} sustained >= {sustain_s}s"
            )

    if publisher_rate_ratio < rate_threshold:
        reasons.append(f"pointcloud publisher rate {publisher_rate_ratio:.2f} < {rate_threshold}")
    if not quality_ok:
        reasons.append("m5 quality gate failed")
    return CeilingVerdict(bool(reasons), reasons)
