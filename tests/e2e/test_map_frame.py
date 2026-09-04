from scripts.e2e import map_frame as mf


def test_local_projector_is_a_pure_y_flip():
    assert mf.carla_to_map(10.0, 5.0) == (10.0, -5.0, 0.0)


def test_nishishinjuku_origin_reproduces_the_pinned_affine():
    x, y, z = mf.carla_to_map(0.0, 0.0, 0.0, origin=mf.NISHISHINJUKU_ORIGIN)
    assert (x, y, z) == (81655.73, 50137.43, 42.49998)
    x, y, _ = mf.carla_to_map(100.0, 50.0, origin=mf.NISHISHINJUKU_ORIGIN)
    assert (round(x, 2), round(y, 2)) == (81755.73, 50087.43)


def test_yaw_negates():
    assert mf.carla_yaw_to_map(90.0) == -90.0


def test_rear_axle_shifts_backwards_along_heading():
    x, y = mf.rear_axle(0.0, 0.0, 0.0)  # heading +x
    assert (round(x, 3), round(y, 3)) == (-1.425, 0.0)
    x, y = mf.rear_axle(0.0, 0.0, 90.0)  # heading +y (CARLA yaw is left-handed about +z)
    assert (round(x, 3), round(y, 3)) == (0.0, -1.425)
    assert mf.rear_axle(3.0, 4.0, 45.0, offset_m=0.0) == (3.0, 4.0)


def test_parse_origin():
    assert mf.parse_origin("1,2,3") == (1.0, 2.0, 3.0)
    assert mf.parse_origin("") == (0.0, 0.0, 0.0)
