"""Unit tests for the gates' shared ground-truth collector (``scripts.e2e.collect_gt``).

Pure-Python only: the module lazy-imports ``carla`` inside ``main()``, so these
tests collect and run under a bare ``python3 -m pytest`` with no CARLA egg,
which is how CI runs it.
"""

import math

from scripts.e2e import collect_gt as gt
from scripts.e2e.map_frame import NISHISHINJUKU_ORIGIN


def test_ego_map_xy_local_projector_rear_axle_basis():
    # actor at (10, 0) heading +x -> base_link at (8.575, 0) -> map (8.575, -0.0)
    mx, my = gt.ego_map_xy(10.0, 0.0, 0.0)
    assert (round(mx, 3), round(my, 3)) == (8.575, 0.0)


def test_ego_map_xy_can_disable_the_rear_axle_shift():
    assert gt.ego_map_xy(10.0, 5.0, 0.0, rear_axle_offset=0.0) == (10.0, -5.0)


def test_ego_map_xy_with_mgrs_origin():
    mx, my = gt.ego_map_xy(0.0, 0.0, 0.0, origin=NISHISHINJUKU_ORIGIN, rear_axle_offset=0.0)
    assert (mx, my) == (81655.73, 50137.43)


def test_goal_distance_is_measured_from_base_link():
    d = gt.goal_distance(10.0, 0.0, 0.0, goal_x=8.575, goal_y=0.0)
    assert math.isclose(d, 0.0, abs_tol=1e-9)


class _Actor:
    def __init__(self, role):
        self.attributes = {"role_name": role}


class _Actors(list):
    def filter(self, _pattern):
        return self


class _World:
    def __init__(self, actors):
        self._actors = actors

    def get_actors(self):
        return _Actors(self._actors)


def test_find_ego_returns_role_ego_and_retries():
    calls = []
    world = _World([_Actor("hero")])
    try:
        gt.find_ego(world, attempts=2, delay_s=0.0, sleep=lambda s: calls.append(s))
    except RuntimeError:
        pass
    assert len(calls) == 2
    ego = _Actor("ego")
    assert gt.find_ego(_World([_Actor("hero"), ego]), attempts=1, sleep=lambda s: None) is ego
