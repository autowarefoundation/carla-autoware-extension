"""benchmarks/analysis/publisher_counts.py: the publisher_counts.json
contract shared by collect_gt.py (writer), duel_verdict.py (windowed
reader) and sweep_verdict.py (whole-run reader).

The property these tests exist for is that a whole-run count and a
windowed count are DIFFERENT quantities, and that the file makes the
second one derivable at all: the pre-schema shape ({topic: count})
carried no stamps, so every consumer had only the first and the M2
reconciliation mixed one whole-run term with two windowed ones.
"""

from __future__ import annotations

import json

import pytest

from benchmarks.analysis.publisher_counts import (
    PUBLISHER_COUNTS_SCHEMA,
    PublisherCountsFormatError,
    publisher_counts_doc,
    read_publisher_counts,
)

TOPIC = "/sensing/lidar/top/pointcloud_raw_ex"


def _write(tmp_path, doc):
    path = tmp_path / "publisher_counts.json"
    path.write_text(json.dumps(doc))
    return path


def test_round_trip_writer_to_reader(tmp_path):
    stamps = [0, 100_000_000, 200_000_000]
    counts = read_publisher_counts(_write(tmp_path, publisher_counts_doc({TOPIC: stamps})))
    assert counts.whole_run_count(TOPIC) == 3
    assert counts.sim_stamps_ns[TOPIC] == tuple(stamps)


def test_doc_carries_the_schema_tag_and_a_count_beside_the_stamps():
    doc = publisher_counts_doc({TOPIC: [1, 2]})
    assert doc["schema"] == PUBLISHER_COUNTS_SCHEMA
    assert doc["topics"][TOPIC] == {"count": 2, "sim_stamps_ns": [1, 2]}


def test_count_in_window_is_the_closed_interval(tmp_path):
    """Inclusive on BOTH bounds, matching the `>= sim_lo & <= sim_hi`
    filter duel_verdict applies to observer.csv: a message stamped
    exactly on a boundary must be counted on both sides of the
    reconciliation or on neither, never on one."""
    stamps = [10, 20, 30, 40, 50]
    counts = read_publisher_counts(_write(tmp_path, publisher_counts_doc({TOPIC: stamps})))
    assert counts.count_in_window(TOPIC, 20, 40) == 3
    assert counts.count_in_window(TOPIC, 21, 39) == 1
    assert counts.count_in_window(TOPIC, 60, 70) == 0


def test_whole_run_count_and_windowed_count_are_different_quantities(tmp_path):
    """The distinction the schema exists to make available: the same
    file answers both questions, and the two answers differ whenever the
    run extends past its scoring window -- which is every run, since the
    window discards a 20 s warm-up."""
    stamps = list(range(0, 100, 10))
    counts = read_publisher_counts(_write(tmp_path, publisher_counts_doc({TOPIC: stamps})))
    assert counts.whole_run_count(TOPIC) == 10
    assert counts.count_in_window(TOPIC, 50, 90) == 5


def test_pre_schema_shape_is_refused_not_reinterpreted(tmp_path):
    """The backward-compatibility decision: a v1 `{topic: count}` file is
    REFUSED. Reading its whole-run count as though it were windowed is
    the defect this schema fixes, and no post-hoc windowing of it is
    possible, so it cannot be silently accepted."""
    path = _write(tmp_path, {TOPIC: 1200})
    with pytest.raises(PublisherCountsFormatError) as exc:
        read_publisher_counts(path)
    message = str(exc.value)
    assert PUBLISHER_COUNTS_SCHEMA in message
    assert "WHOLE-RUN" in message
    assert str(path) in message


def test_unknown_schema_tag_is_refused(tmp_path):
    path = _write(tmp_path, {"schema": "publisher_counts/99", "topics": {}})
    with pytest.raises(PublisherCountsFormatError, match="publisher_counts/99"):
        read_publisher_counts(path)


def test_count_disagreeing_with_the_stamps_is_refused(tmp_path):
    """A file whose own two records contradict each other is not
    silently resolved in favour of either: it is the one case where
    neither number can be trusted."""
    path = _write(
        tmp_path,
        {
            "schema": PUBLISHER_COUNTS_SCHEMA,
            "topics": {TOPIC: {"count": 5, "sim_stamps_ns": [1, 2, 3]}},
        },
    )
    with pytest.raises(PublisherCountsFormatError, match="count=5"):
        read_publisher_counts(path)


def test_a_missing_topic_is_named_not_a_bare_key_error(tmp_path):
    """`sweep_verdict._publisher_rate_ratio` has no guard around this
    lookup, so it aborts the whole sweep; the message must therefore say
    which topic was asked for and which the file holds."""
    counts = read_publisher_counts(_write(tmp_path, publisher_counts_doc({TOPIC: [1, 2]})))
    with pytest.raises(PublisherCountsFormatError) as exc:
        counts.whole_run_count("/other/topic")
    assert "/other/topic" in str(exc.value) and TOPIC in str(exc.value)


def test_a_non_object_document_is_refused(tmp_path):
    path = tmp_path / "publisher_counts.json"
    path.write_text(json.dumps([1, 2, 3]))
    with pytest.raises(PublisherCountsFormatError, match="JSON object"):
        read_publisher_counts(path)


def test_malformed_topic_entry_is_refused(tmp_path):
    path = _write(tmp_path, {"schema": PUBLISHER_COUNTS_SCHEMA, "topics": {TOPIC: 1200}})
    with pytest.raises(PublisherCountsFormatError, match="sim_stamps_ns"):
        read_publisher_counts(path)
