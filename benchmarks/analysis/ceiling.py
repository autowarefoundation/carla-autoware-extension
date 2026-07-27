"""Pre-registered M4 sustainable-load ceiling criterion (spec: M4)."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class CeilingVerdict:
    reached: bool
    reasons: list = field(default_factory=list)


def evaluate_ceiling(
    sample_system_ns,
    rtf,
    publisher_rate_ratio: float,
    quality_ok: bool,
    rtf_threshold: float = 0.9,
    sustain_s: float = 10.0,
    rate_threshold: float = 0.9,
) -> CeilingVerdict:
    t = np.asarray(sample_system_ns, dtype=np.int64)
    r = np.asarray(rtf, dtype=np.float64)
    reasons = []

    below = r < rtf_threshold
    start = None
    for k in range(t.size):
        if below[k]:
            if start is None:
                start = t[k]
            elif (t[k] - start) / 1e9 >= sustain_s:
                reasons.append(f"rtf<{rtf_threshold} sustained >= {sustain_s}s")
                break
        else:
            start = None

    if publisher_rate_ratio < rate_threshold:
        reasons.append(f"publisher rate {publisher_rate_ratio:.2f} < {rate_threshold}")
    if not quality_ok:
        reasons.append("m5 quality gate failed")
    return CeilingVerdict(bool(reasons), reasons)
