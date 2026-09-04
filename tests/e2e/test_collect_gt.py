"""Unit tests for the gates' shared ground-truth collector (``scripts.e2e.collect_gt``).

Pure-Python only: the module lazy-imports ``carla`` inside ``main()``, so these
tests collect and run under a bare ``python3 -m pytest`` with no CARLA egg,
which is how CI runs it. The ``main()`` tests below exploit that same lazy
import as their seam: they install a fake module at ``sys.modules["carla"]``
before calling ``main()``, so ``import carla`` inside it resolves to the
fake instead of touching a live simulator, with no change to production code.
"""

import math
import sys
import types

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


def test_goal_distance_applies_origin_to_the_ego_only_not_the_goal():
    # Non-zero, asymmetric origin/goal so a re-applied origin on the goal side
    # (a double-application regression) is numerically distinguishable from
    # the correct single application: ego CARLA (50, 30, yaw=0) -> base_link
    # (48.575, 30) -> map (1048.575, 1970.0) under origin (1000, 2000, 0); the
    # goal (1080.0, 1970.0) is already in that map frame, so the distance is
    # the plain metric gap, 31.425 m -- not the ~2197 m a double-applied
    # origin would produce.
    d = gt.goal_distance(
        50.0, 30.0, 0.0, goal_x=1080.0, goal_y=1970.0, origin=(1000.0, 2000.0, 0.0)
    )
    assert math.isclose(d, 31.425, abs_tol=1e-9)


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


# --- main() coverage: no live simulator, injected via sys.modules["carla"]. ---


class _Loc:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class _Rot:
    def __init__(self, yaw):
        self.yaw = yaw


class _Transform:
    def __init__(self, x, y, yaw):
        self.location = _Loc(x, y)
        self.rotation = _Rot(yaw)


class _EgoActor(_Actor):
    def __init__(self, x, y, yaw):
        super().__init__("ego")
        self._transform = _Transform(x, y, yaw)

    def get_transform(self):
        return self._transform


class _MainWorld(_World):
    def wait_for_tick(self, timeout=None):
        return None


class _FakeClient:
    def __init__(self, world, host, port):
        self._world = world
        self.host = host
        self.port = port

    def get_world(self):
        return self._world


def _install_fake_carla(monkeypatch, world):
    """Stand in for the real ``carla`` module at the point ``main()`` imports it.

    ``main()`` does a lazy, function-local ``import carla`` (for the pure-pytest
    import discipline documented at module level), which means
    ``sys.modules["carla"]`` is already a working seam -- no production code
    needs to change to make ``main()`` testable without a live simulator.
    """
    fake_carla = types.ModuleType("carla")
    fake_carla.Client = lambda host, port: _FakeClient(world, host, port)
    monkeypatch.setitem(sys.modules, "carla", fake_carla)


def test_main_g1_style_invocation_writes_base_link_gt_rows(tmp_path, monkeypatch):
    # Mirrors Task 15's G1 invocation shape with ORIGIN unset (flag omitted):
    #   collect_gt --window "$WIN" --out "$OUT/g1_gt.txt" --port "$PORT"
    out = tmp_path / "g1_gt.txt"
    ego = _EgoActor(50.0, 30.0, 0.0)  # base_link (48.575, 30) -> map (48.575, -30)
    _install_fake_carla(monkeypatch, _MainWorld([ego]))
    argv = ["--window", "0.02", "--out", str(out), "--port", "1"]
    rc = gt.main(argv)
    assert rc == 0
    lines = out.read_text().strip().splitlines()
    assert lines
    t_str, mx_str, my_str = lines[0].split()
    float(t_str)  # timestamp column parses as a float
    assert (round(float(mx_str), 3), round(float(my_str), 3)) == (48.575, -30.0)


def test_main_g2_style_invocation_writes_goal_distance_rows(tmp_path, monkeypatch):
    # Mirrors Task 15's G2 invocation shape with ORIGIN set:
    #   collect_gt --window "$WIN" --out "$OUT/g2_dist.txt" --port "$PORT" \
    #       --goal "$GX" "$GY" --map-origin "$ORIGIN"
    # Same ego pose/origin/goal as the double-application regression test above.
    out = tmp_path / "g2_dist.txt"
    ego = _EgoActor(50.0, 30.0, 0.0)
    _install_fake_carla(monkeypatch, _MainWorld([ego]))
    argv = [
        "--window",
        "0.02",
        "--out",
        str(out),
        "--port",
        "1",
        "--goal",
        "1080.0",
        "1970.0",
        "--map-origin",
        "1000,2000,0",
    ]
    rc = gt.main(argv)
    assert rc == 0
    lines = out.read_text().strip().splitlines()
    assert lines
    assert math.isclose(float(lines[0]), 31.425, abs_tol=1e-9)
