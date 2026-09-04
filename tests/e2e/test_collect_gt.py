"""Unit tests for the gates' shared ground-truth collector (``scripts.e2e.collect_gt``).

Pure-Python only: the module lazy-imports ``carla`` inside ``main()``, so these
tests collect and run under a bare ``python3 -m pytest`` with no CARLA egg,
which is how CI runs it.
"""

import math

import pytest

from scripts.e2e.collect_gt import ego_map_xy, find_ego, goal_distance
from scripts.e2e.verify_mgrs_handedness import CONVERTER_OFFSET, MAP_ENV_VAR, MAP_OFFSETS


def test_ego_map_xy_matches_the_pinned_affine():
    # The mapping must be the single pinned affine (offset + X pass-through,
    # Y flip), not an independent re-derivation.
    ox, oy, _ = CONVERTER_OFFSET
    x, y = ego_map_xy(-278.39, 220.54)
    assert math.isclose(x, ox - 278.39, abs_tol=1e-9)
    assert math.isclose(y, oy - 220.54, abs_tol=1e-9)


def test_goal_distance_is_map_frame_hypot():
    ox, oy, _ = CONVERTER_OFFSET
    # Ego at CARLA (3, -4) -> map (ox+3, oy+4); goal at map (ox, oy) -> distance 5.
    assert math.isclose(goal_distance(3.0, -4.0, ox, oy), 5.0, abs_tol=1e-9)


def test_ego_map_xy_accepts_another_maps_offset():
    town10 = MAP_OFFSETS["Town10HD_Opt"]
    ox, oy, _ = town10
    x, y = ego_map_xy(-28.35, -69.72, town10)
    assert math.isclose(x, ox - 28.35, abs_tol=1e-9)
    assert math.isclose(y, oy + 69.72, abs_tol=1e-9)  # Y flip still applies


def test_goal_distance_accepts_another_maps_offset():
    town10 = MAP_OFFSETS["Town10HD_Opt"]
    assert math.isclose(goal_distance(3.0, -4.0, 0.0, 0.0, town10), 5.0, abs_tol=1e-9)


def test_defaults_do_not_read_the_environment(monkeypatch):
    # These are pure affine helpers: an exported map name must not silently move
    # what a default-argument call returns. main() resolves the active map once.
    monkeypatch.setenv(MAP_ENV_VAR, "Town10HD_Opt")
    ox, oy, _ = CONVERTER_OFFSET
    assert ego_map_xy(0.0, 0.0) == (ox, oy)


class _FakeActor:
    def __init__(self, role_name):
        self.attributes = {"role_name": role_name}


class _FakeActorList(list):
    def filter(self, pattern):
        assert pattern == "vehicle.*"
        return self


class _FakeWorld:
    """World whose actor list is empty for the first ``empty_reads`` queries."""

    def __init__(self, empty_reads, ego=None):
        self._empty_reads = empty_reads
        self._ego = ego

    def get_actors(self):
        if self._empty_reads > 0:
            self._empty_reads -= 1
            return _FakeActorList([_FakeActor("npc")])
        return _FakeActorList([_FakeActor("npc"), self._ego])


def test_find_ego_retries_until_the_ego_appears():
    ego = _FakeActor("ego")
    sleeps = []
    found = find_ego(_FakeWorld(empty_reads=3, ego=ego), sleep=sleeps.append)
    assert found is ego
    assert len(sleeps) == 3  # one sleep per empty read, none after success


def test_find_ego_fails_loudly_after_exhausting_attempts():
    with pytest.raises(RuntimeError, match="no ego actor"):
        find_ego(_FakeWorld(empty_reads=10**9), attempts=5, sleep=lambda _: None)
