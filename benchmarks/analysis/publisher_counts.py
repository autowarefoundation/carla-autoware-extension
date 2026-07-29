"""`publisher_counts.json`: the M2 reconciliation's publisher-side term.

Written by `benchmarks/scripts/collect_gt.py --count-lidar`, read by
`scripts/duel_verdict.py` (which windows it) and by
`scripts/sweep_verdict.py` (which does not -- its whole reconciliation is
whole-run). One module owns the on-disk shape so writer and readers
cannot drift: the file is a run-directory artifact other tools may read,
not a private scratch file.

WHY PER-MESSAGE STAMPS AND NOT A BARE COUNT
-------------------------------------------
The v1 shape was `{topic: count}` -- a cumulative counter with no time
information at all, so the only count it could offer was the WHOLE RUN's.
`duel_verdict.py` reconciles it against an expected count and an observed
count that are both windowed to the run's registered scoring window, and
a whole-run publisher count against a windowed pair is not a slower or
noisier answer, it is a different quantity: on a healthy 60 s static run
with a 40 s window it makes `publisher_drop_rate` structurally
non-positive (clamped to 0.000) and fabricates ~0.333 of
`observer_loss_rate` out of the interval mismatch alone. Recording each
message's stamp is what lets the publisher-side term be windowed
IDENTICALLY to the other two (owner ruling, 2026-07-28; see
`benchmarks/README.md`, `achieved_rate_ratio`).

THE STAMP DOMAIN IS SIM, NOT WALL
---------------------------------
`sim_stamps_ns` are simulation-time nanoseconds -- CARLA's episode
`elapsed_seconds` scaled by `collect_gt.sim_ns_from_elapsed`, the same
domain and the same rounding rule as `gt.csv`'s `sim_ns` column. That is
the domain the duel's window bounds (`_RunWindow.sim_lo`/`sim_hi`) and
the observed term (`observer.csv`'s `header_stamp_ns`) live in, so the
publisher-side filter is the same comparison on the same clock rather
than a conversion through the run's clock fit. The campaign already
depends on those two agreeing: `analysis/quality.py`'s `evaluate_quality`
joins `gt.csv`'s `sim_ns` to the NDT pose's ROS header stamp within
`JOIN_TOL_NS` (25 ms).

DEPENDENCIES
------------
Standard library only, deliberately. This module is imported by
`collect_gt.py`, which runs under whichever interpreter each cell's
launcher picks -- for cell B that is `$HOME/carla-tier4-venv`, which
carries the tier4 `carla` wheel and pip and nothing else. A `numpy` (or
`yaml`) import reached from here would fail at collection time on the
cells whose publisher-side counts this file exists to record.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

# On-disk schema tag. Present in every file this module writes and
# REQUIRED by the reader: the v1 shape ({topic: count}) carried no tag,
# so its absence is what identifies it.
PUBLISHER_COUNTS_SCHEMA = "publisher_counts/2"


class PublisherCountsFormatError(ValueError):
    """`publisher_counts.json` is not in the schema this module reads.

    A distinct, nameable state -- never folded into "not measurable"
    (which means no publisher-side count exists at all, the E-cell case)
    and never repaired by guessing. A v1 file records a whole-run count
    that CANNOT be windowed after the fact, so reading one under v2's
    semantics would reintroduce the exact defect the schema bump fixes.
    """


@dataclass(frozen=True)
class PublisherCounts:
    """One run's publisher-side message stamps, keyed by topic.

    `count_in_window` is the duel's term (windowed to the run's resolved
    scoring window); `whole_run_count` is the M4 sweep's (whose expected
    and observed terms are whole-run too). Both are offered here so each
    tool NAMES which one it wants at the call site instead of one of them
    being what a bare attribute happens to hold.
    """

    sim_stamps_ns: Mapping[str, tuple[int, ...]]

    def _stamps(self, topic: str) -> tuple[int, ...]:
        try:
            return self.sim_stamps_ns[topic]
        except KeyError:
            raise PublisherCountsFormatError(
                f"no publisher-side count for topic {topic!r}; the file "
                f"records {sorted(self.sim_stamps_ns)}"
            ) from None

    def whole_run_count(self, topic: str) -> int:
        """Every message recorded for `topic`, unwindowed."""
        return len(self._stamps(topic))

    def count_in_window(self, topic: str, sim_lo: int, sim_hi: int) -> int:
        """Messages whose sim stamp lies in the CLOSED interval
        `[sim_lo, sim_hi]` -- the same inclusive bounds
        `duel_verdict._reconcile_run` filters `observer.csv`'s
        `header_stamp_ns` on, so a message on a boundary is counted on
        both sides of the reconciliation or on neither."""
        return sum(1 for s in self._stamps(topic) if sim_lo <= s <= sim_hi)


def publisher_counts_doc(sim_stamps_ns: Mapping[str, Sequence[int]]) -> dict:
    """The `publisher_counts.json` document for per-topic sim stamps.

    `count` is written alongside the stamps because it is what an
    operator reads at a glance in a run directory; the reader checks the
    two agree rather than trusting either alone.
    """
    return {
        "schema": PUBLISHER_COUNTS_SCHEMA,
        "topics": {
            topic: {"count": len(stamps), "sim_stamps_ns": [int(s) for s in stamps]}
            for topic, stamps in sim_stamps_ns.items()
        },
    }


def read_publisher_counts(path) -> PublisherCounts:
    """Parse `publisher_counts.json`, refusing anything else by name.

    Refused (`PublisherCountsFormatError`), never coerced: a v1
    `{topic: count}` file, an unknown schema tag, and a `count` that
    disagrees with the number of stamps recorded for the same topic.
    """
    path = Path(path)
    doc = json.loads(path.read_text())
    if not isinstance(doc, dict):
        raise PublisherCountsFormatError(
            f"{path}: expected a JSON object, got {type(doc).__name__}"
        )
    schema = doc.get("schema")
    if schema is None:
        raise PublisherCountsFormatError(
            f"{path}: no 'schema' key -- this is the pre-{PUBLISHER_COUNTS_SCHEMA} "
            f"shape ({{topic: count}}), a WHOLE-RUN count with no per-message "
            f"stamps. It cannot be windowed to a scoring window after the fact, "
            f"so it is refused rather than read as if it were windowed. Re-run "
            f"the collection with a collect_gt.py that writes "
            f"{PUBLISHER_COUNTS_SCHEMA}."
        )
    if schema != PUBLISHER_COUNTS_SCHEMA:
        raise PublisherCountsFormatError(
            f"{path}: schema {schema!r}, expected {PUBLISHER_COUNTS_SCHEMA!r}"
        )
    topics = doc.get("topics")
    if not isinstance(topics, dict):
        raise PublisherCountsFormatError(f"{path}: 'topics' must be an object")

    stamps: dict[str, tuple[int, ...]] = {}
    for topic, entry in topics.items():
        try:
            recorded = int(entry["count"])
            series = tuple(int(s) for s in entry["sim_stamps_ns"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PublisherCountsFormatError(
                f"{path}: topic {topic!r} must carry an integer 'count' and an "
                f"integer 'sim_stamps_ns' list ({exc})"
            ) from exc
        if recorded != len(series):
            raise PublisherCountsFormatError(
                f"{path}: topic {topic!r} records count={recorded} but "
                f"{len(series)} stamp(s); the file is inconsistent and neither "
                f"number may be used"
            )
        stamps[topic] = series
    return PublisherCounts(stamps)
