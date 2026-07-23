from scripts.phase_b.measure_ndt import ndt_pass

def test_pass_when_within_threshold():
    errs = [0.1, 0.2, 0.15, 0.3]
    assert ndt_pass(errs, max_err_m=0.5) is True

def test_fail_when_diverges():
    errs = [0.1, 0.6, 0.2]
    assert ndt_pass(errs, max_err_m=0.5) is False

def test_fail_on_empty_stream():
    assert ndt_pass([], max_err_m=0.5) is False   # no NDT poses = not tracking
