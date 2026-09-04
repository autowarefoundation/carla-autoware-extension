import numpy as np
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
