"""Latency segment and staleness metrics.

Computes M1a (stamp-propagating latency) and M1b (data staleness) for
benchmark analysis. Formulas assume continuous downstream stamp
propagation; for hops where Autoware re-stamps with now(), use raw
timing instead of these functions.
"""

from __future__ import annotations

import numpy as np

from .clockfit import AffineFit, sim_to_wall


def one_hop_wall_ms(header_stamp_ns, arrival_system_ns, fit: AffineFit) -> np.ndarray:
    """One-hop wall latency: arrival wall time minus expected wall time.

    Args:
        header_stamp_ns: message header timestamp (simulation ns).
        arrival_system_ns: arrival time (wall ns).
        fit: affine fit for sim-to-wall conversion.

    Returns:
        Latency in milliseconds as float64 array.
    """
    expected_wall = sim_to_wall(fit, header_stamp_ns)
    return (np.asarray(arrival_system_ns, dtype=np.float64) - expected_wall) / 1e6


def match_stamps(src_stamp_ns, dst_stamp_ns):
    """Match stamps: return indices of common timestamps.

    Args:
        src_stamp_ns: source timestamps (ns).
        dst_stamp_ns: destination timestamps (ns).

    Returns:
        Tuple (i, j) where src[i] == dst[j] for common timestamps.
    """
    _, i, j = np.intersect1d(
        np.asarray(src_stamp_ns, dtype=np.int64),
        np.asarray(dst_stamp_ns, dtype=np.int64),
        return_indices=True,
    )
    return i, j


def segment_sim_ms(src_stamp_ns, dst_stamp_ns) -> np.ndarray:
    """Simulation-time latency: dst - src in milliseconds.

    Args:
        src_stamp_ns: source timestamp (simulation ns).
        dst_stamp_ns: destination timestamp (simulation ns).

    Returns:
        Latency in milliseconds as float64 array.
    """
    return (
        np.asarray(dst_stamp_ns, dtype=np.float64) - np.asarray(src_stamp_ns, dtype=np.float64)
    ) / 1e6


def staleness_ms(source_header_ns, published_ns) -> np.ndarray:
    """Data staleness: publish time minus source header in milliseconds.

    Args:
        source_header_ns: source header timestamp (simulation ns).
        published_ns: publish/processing timestamp (simulation ns).

    Returns:
        Staleness in milliseconds as float64 array.
    """
    return segment_sim_ms(source_header_ns, published_ns)
