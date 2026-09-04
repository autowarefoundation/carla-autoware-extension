import numpy as np
import pytest
from benchmarks.analysis.ceiling import evaluate_ceiling

T = np.arange(0, 60_000_000_000, 1_000_000_000)  # 1 Hz samples, 60 s


def test_healthy_run_not_at_ceiling():
    v = evaluate_ceiling(T, np.full(T.size, 0.99), 0.98, True)
    assert not v.reached and v.reasons == []


def test_sustained_low_rtf_triggers():
    rtf = np.full(T.size, 0.99)
    rtf[20:35] = 0.5  # 15 s below threshold
    v = evaluate_ceiling(T, rtf, 0.98, True)
    assert v.reached and any("rtf" in r for r in v.reasons)


def test_brief_dip_does_not_trigger():
    rtf = np.full(T.size, 0.99)
    rtf[20:25] = 0.5  # 5 s < sustain_s
    v = evaluate_ceiling(T, rtf, 0.98, True)
    assert not v.reached


def test_publisher_rate_triggers():
    v = evaluate_ceiling(T, np.full(T.size, 0.99), 0.85, True)
    assert v.reached and any("rate" in r for r in v.reasons)


def test_quality_gate_triggers():
    v = evaluate_ceiling(T, np.full(T.size, 0.99), 0.98, False)
    assert v.reached and any("quality" in r for r in v.reasons)


# --- the unpaced arm's ticks/s disjunct (spec M4, 4th criterion) ---


def test_unpaced_sustained_low_tick_rate_triggers():
    """The unpaced arm has no meaningful RTF, so the spec substitutes
    ticks/s < 90% of the PACED target. Same sustain rule, separate input."""
    ticks = np.full(T.size, 0.99)
    ticks[20:35] = 0.5  # 15 s below threshold
    v = evaluate_ceiling(T, None, 0.98, True, tick_rate_ratio=ticks)
    assert v.reached and any("tick rate" in r for r in v.reasons)


def test_unpaced_brief_tick_dip_does_not_trigger():
    ticks = np.full(T.size, 0.99)
    ticks[20:25] = 0.5  # 5 s < sustain_s
    v = evaluate_ceiling(T, None, 0.98, True, tick_rate_ratio=ticks)
    assert not v.reached and v.reasons == []


def test_rtf_and_tick_rate_are_reported_as_distinct_disjuncts():
    """Both series may be measured on one point; the verdict must name which
    of the two fired rather than collapsing them into one slot."""
    ticks = np.full(T.size, 0.99)
    ticks[10:40] = 0.5
    v = evaluate_ceiling(T, np.full(T.size, 0.99), 0.98, True, tick_rate_ratio=ticks)
    assert v.reached
    assert [r for r in v.reasons if "tick rate" in r]
    assert not [r for r in v.reasons if r.startswith("rtf<")]


def test_all_four_disjuncts_can_fire_together():
    low = np.full(T.size, 0.5)
    v = evaluate_ceiling(T, low, 0.85, False, tick_rate_ratio=low)
    assert v.reached and len(v.reasons) == 4


def test_neither_throughput_series_given_raises():
    with pytest.raises(ValueError, match="tick_rate_ratio"):
        evaluate_ceiling(T, None, 0.98, True)


def test_tick_rate_length_mismatch_raises():
    with pytest.raises(ValueError, match="tick_rate_ratio"):
        evaluate_ceiling(T, None, 0.98, True, tick_rate_ratio=np.full(T.size - 1, 0.99))
