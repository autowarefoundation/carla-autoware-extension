from scripts.phase_b.measure_route import route_completed


def test_completed_when_final_distance_small():
    dists = [40.0, 20.0, 5.0, 0.8]
    assert route_completed(dists, goal_tol_m=1.0) is True


def test_not_completed_when_stalled():
    dists = [40.0, 39.5, 39.4, 39.4]  # never approaches goal (ego did not move)
    assert route_completed(dists, goal_tol_m=1.0) is False
