"""Unit tests for the CARLA-world -> MGRS-local coordinate transform.

These pin the integration's #1 coordinate risk (handedness / Y-flip and the unit
convention) as pure, CARLA-free assertions. The live measured verification of
the same relation against the Nishi-Shinjuku map lives in
``scripts/e2e/probe_carla_mgrs.py`` and ``docs/mgrs-handedness.md``.
"""

import math

from scripts.e2e.verify_mgrs_handedness import (
    CONVERTER_OFFSET,
    mgrs_local_to_world_cm,
    world_m_to_mgrs_local,
    world_to_mgrs_local,
)


def test_offset_constants():
    assert CONVERTER_OFFSET == (81655.73, 50137.43, 42.49998)


def test_origin_maps_to_offset():
    # CARLA world origin (0,0,0) cm maps to exactly the converter offset in MGRS-local metres.
    mx, my, mz = world_to_mgrs_local(0.0, 0.0, 0.0)
    assert math.isclose(mx, 81655.73, abs_tol=1e-3)
    assert math.isclose(my, 50137.43, abs_tol=1e-3)
    assert math.isclose(mz, 42.49998, abs_tol=1e-3)


def test_y_is_flipped():
    # +Y in CARLA (left-handed, cm) must DECREASE MGRS-local y (right-handed, m).
    _, y_pos, _ = world_to_mgrs_local(0.0, 100.0, 0.0)  # +1 m in CARLA Y
    assert math.isclose(y_pos, 50137.43 - 1.0, abs_tol=1e-3)


def test_x_is_metres_not_cm():
    x_pos, _, _ = world_to_mgrs_local(100.0, 0.0, 0.0)  # +1 m in CARLA X
    assert math.isclose(x_pos, 81655.73 + 1.0, abs_tol=1e-3)


# --- Inverse and round-trip (both directions are a required deliverable) ---


def test_inverse_of_offset_is_origin():
    # The converter offset in MGRS-local metres maps back to CARLA world origin (cm).
    x, y, z = mgrs_local_to_world_cm(*CONVERTER_OFFSET)
    assert math.isclose(x, 0.0, abs_tol=1e-6)
    assert math.isclose(y, 0.0, abs_tol=1e-6)
    assert math.isclose(z, 0.0, abs_tol=1e-6)


def test_inverse_y_is_flipped():
    # +1 m north in MGRS-local must be -100 cm (i.e. -1 m) in CARLA Y (left-handed).
    _, y_cm, _ = mgrs_local_to_world_cm(81655.73, 50137.43 + 1.0, 42.49998)
    assert math.isclose(y_cm, -100.0, abs_tol=1e-6)


def test_round_trip_forward_inverse():
    # A representative interior probe point round-trips to itself.
    world = (12345.0, -6789.0, 250.0)  # cm
    mgrs = world_to_mgrs_local(*world)
    back = mgrs_local_to_world_cm(*mgrs)
    for a, b in zip(world, back):
        assert math.isclose(a, b, abs_tol=1e-6)


# --- PythonAPI metres helper (guards the x100 cm-vs-m footgun) ---


def test_world_m_x_is_one_metre_not_one_cm():
    # The CARLA PythonAPI reports metres: +1 m in X -> +1 m in MGRS-local x.
    mx, _, _ = world_m_to_mgrs_local(1.0, 0.0, 0.0)
    assert math.isclose(mx, 81656.73, abs_tol=1e-3)


def test_world_m_y_is_flipped():
    # +1 m in CARLA Y (metres) must DECREASE MGRS-local y by 1 m (Y flip).
    _, my, _ = world_m_to_mgrs_local(0.0, 1.0, 0.0)
    assert math.isclose(my, 50137.43 - 1.0, abs_tol=1e-3)


def test_world_m_equals_world_cm_scaled():
    # world_m_to_mgrs_local(x) == world_to_mgrs_local(x*100): the only difference
    # between the PythonAPI (metres) and .so (cm) entry points is the x100 scale.
    for x_m, y_m, z_m in [(1.0, 0.0, 0.0), (-3.21, 4.56, 2.5), (100.0, -50.0, 10.0)]:
        a = world_m_to_mgrs_local(x_m, y_m, z_m)
        b = world_to_mgrs_local(x_m * 100.0, y_m * 100.0, z_m * 100.0)
        for u, v in zip(a, b):
            assert math.isclose(u, v, abs_tol=1e-9)
