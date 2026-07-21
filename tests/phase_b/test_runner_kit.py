"""Unit tests for the Phase B sensor-kit spawn layer (``runner.kit`` / ``runner.spawn``).

Pure-Python only: importing these modules must NOT pull in ``carla`` (``spawn.py``
lazy-imports it inside the spawn functions), so this suite collects and runs under a
bare ``python3 -m pytest`` with no special venv, per the M0 CI lesson. The live spawn /
attach path (ego wheelbase reconcile, top-lidar world-transform check) is exercised
separately and recorded in ``docs/nishishinjuku-map.md`` ("Phase B ego reconciliation").

The kit-yaml assertions run against the REAL committed calibration files under
``runner/config/`` (extracted from ``awsim_labs_sensor_kit_description`` in the pinned
``ghcr.io/autowarefoundation/autoware:universe-devel`` image), not a synthetic fixture.
"""

import math

import pytest

from runner.kit import (
    IMU_FRAME,
    SENSOR_KIT_PACKAGE,
    TOP_LIDAR_FRAME,
    KitConfig,
    base_link_to_vehicle_center,
    carla_attach_location,
    carla_attach_rotation,
    load_kit,
    ros_rpy_to_carla_rotation,
    sensor_in_base_link,
    sensor_rotation_in_base_link,
)
from runner.spawn import (
    EGO_BLUEPRINT,
    IMU_TOPIC,
    SAMPLE_VEHICLE_WHEELBASE,
    TOP_LIDAR_TOPIC,
    _apply_attributes,
    ego_attributes,
    imu_attributes,
    top_lidar_attributes,
)

# --- base_link -> vehicle-origin longitudinal conversion (brief Step 1) ---


def test_base_link_offset_is_half_wheelbase_forward():
    # sample_vehicle wheel_base = 2.79 -> a sensor at base_link moves +1.395 m in X
    # (base_link is the rear-axle centre; CARLA attaches relative to the vehicle origin,
    # ~mid-wheelbase, so shift +wheelbase/2 forward).
    x, y, z = base_link_to_vehicle_center((0.0, 0.0, 0.0), wheelbase=2.79)
    assert abs(x - 1.395) < 1e-6
    assert y == 0.0 and z == 0.0


def test_base_link_offset_passes_y_and_z_through():
    # Only X is shifted; Y and Z are carried through unchanged (the documented Z
    # pass-through assumes the CARLA vehicle origin sits at base_link height).
    x, y, z = base_link_to_vehicle_center((1.0, 0.5, 2.0), wheelbase=2.85)
    assert abs(x - (1.0 + 1.425)) < 1e-6
    assert y == 0.5 and z == 2.0


# --- kit yaml loading against the committed real calibration ---


def test_sensor_kit_package_name():
    # The launch template uses sensor_model:=awsim_labs_sensor_kit, so the description
    # package (and thus the committed yaml provenance) is awsim_labs_sensor_kit_description.
    assert SENSOR_KIT_PACKAGE == "awsim_labs_sensor_kit_description"


def test_load_kit_defaults_to_committed_copy():
    kit = load_kit()
    assert isinstance(kit, KitConfig)
    # base_link -> sensor_kit_base_link (sensors_calibration.yaml).
    assert math.isclose(kit.base_to_kit.x, 0.9, abs_tol=1e-9)
    assert math.isclose(kit.base_to_kit.z, 2.0, abs_tol=1e-9)
    # The top lidar frame is present in the kit-level calibration.
    assert TOP_LIDAR_FRAME in kit.kit_to_sensor


# --- transform composition (base_link->kit (+) kit->sensor), rotation-aware ---


def test_top_lidar_composed_translation():
    # velodyne_top_base_link sits at the sensor_kit_base_link origin (0,0,0), so its
    # base_link translation is exactly the base_link->sensor_kit_base_link offset.
    kit = load_kit()
    x, y, z = sensor_in_base_link(kit, TOP_LIDAR_FRAME)
    assert math.isclose(x, 0.9, abs_tol=1e-9)
    assert math.isclose(y, 0.0, abs_tol=1e-9)
    assert math.isclose(z, 2.0, abs_tol=1e-9)


def test_composition_applies_kit_rotation_for_offcentre_sensor():
    # velodyne_left is 0.59 m off the centreline, so the (small but non-zero) kit-level
    # rotation (yaw -0.0364 rad) MUST be applied to its offset: a bare translation-sum
    # would misplace it by ~1.7 cm in X. This proves rotation is composed, not summed.
    kit = load_kit()
    x, y, z = sensor_in_base_link(kit, "velodyne_left_base_link")
    assert math.isclose(x, 0.916871, abs_tol=1e-5)
    assert math.isclose(y, 0.589471, abs_tol=1e-5)
    assert math.isclose(z, 1.693895, abs_tol=1e-5)
    # And it is materially different from the naive translation-sum X (0.9 + 0.0).
    assert abs(x - 0.9) > 1e-2


def test_carla_attach_location_top_lidar():
    # Full pipeline: compose in base_link, then shift to the CARLA vehicle origin.
    kit = load_kit()
    x, y, z = carla_attach_location(kit, TOP_LIDAR_FRAME, wheelbase=SAMPLE_VEHICLE_WHEELBASE)
    assert math.isclose(x, 0.9 + SAMPLE_VEHICLE_WHEELBASE / 2.0, abs_tol=1e-9)  # 2.295
    assert math.isclose(y, 0.0, abs_tol=1e-9)
    assert math.isclose(z, 2.0, abs_tol=1e-9)


# --- spawn attribute assembly (pure; no CARLA connection) ---


def test_ego_attributes():
    attrs = ego_attributes()
    assert attrs["role_name"] == "ego"  # valid hero criterion -> RegisterVehicle
    assert attrs["ros2_ackermann_control"] == "true"  # opt in to the Ackermann sink


def test_ego_blueprint_is_measured_lincoln():
    # The Lincoln MKZ the ported steering-compensation LERP table (Task 20) was measured on.
    # CARLA 0.10 ids it without the 0.9-era year suffix (mkz_2020 does not exist in the 0.10
    # blueprint library, verified live in Step 4b); it is "vehicle.lincoln.mkz".
    assert EGO_BLUEPRINT == "vehicle.lincoln.mkz"
    assert SAMPLE_VEHICLE_WHEELBASE == 2.79


def test_top_lidar_attributes_native():
    attrs = top_lidar_attributes()
    assert attrs["ros_topic_name"] == TOP_LIDAR_TOPIC == "/sensing/lidar/top/pointcloud_raw_ex"
    assert attrs["ros2_extended_lidar"] == "true"  # 10-field PointXYZIRCAEDT layout
    assert attrs["ros2_qos_reliability"] == "best_effort"
    assert attrs["ros2_qos_durability"] == "volatile"
    assert attrs["ros2_qos_history_depth"] == "5"
    # All attribute values are strings (CARLA set_attribute takes strings).
    assert all(isinstance(v, str) for v in attrs.values())


def test_imu_attributes():
    attrs = imu_attributes()
    assert attrs["ros_topic_name"] == IMU_TOPIC == "/sensing/imu/tamagawa/imu_raw"
    assert all(isinstance(v, str) for v in attrs.values())


# --- ROS rpy -> CARLA/UE Rotator conversion pins (Y-flip M-conjugation) ---
#
# The Autoware sensor TF (generated from the SAME committed kit yamls) carries large mount
# rotations; the runner calls set_publish_tf(False) so Autoware owns the TF tree, which means
# the physical CARLA sensor frame MUST be attached with those rotations applied or the clouds
# arrive rotated in base_link. CARLA/UE is left-handed (Y right) vs ROS right-handed (Y left):
# the two are related by M = diag(1,-1,1); conjugation R_ue = M.R_ros.M plus UE's left-handed
# Rotator sign convention nets a componentwise mapping roll:+, pitch:-, yaw:- -- identical to
# carla-ros-bridge's carla_rotation_to_RPY inverse and consistent with the Task-19 quaternion
# pin (-qx, qy, -qz, qw). These four pins fix the sign convention independently.


def test_rotation_conversion_identity():
    roll, pitch, yaw = ros_rpy_to_carla_rotation(0.0, 0.0, 0.0)
    assert abs(roll) < 1e-12 and abs(pitch) < 1e-12 and abs(yaw) < 1e-12


def test_rotation_conversion_pure_yaw_flips_sign():
    # ROS yaw +90deg (right-handed about +Z) -> CARLA yaw -90deg (Y-flip).
    roll, pitch, yaw = ros_rpy_to_carla_rotation(0.0, 0.0, math.pi / 2)
    assert math.isclose(yaw, -90.0, abs_tol=1e-9)
    assert abs(roll) < 1e-9 and abs(pitch) < 1e-9


def test_rotation_conversion_pure_roll_preserves_sign():
    # ROS roll pi -> CARLA roll +180deg: the roll axis sign is NOT flipped (pitch/yaw are).
    roll, pitch, yaw = ros_rpy_to_carla_rotation(math.pi, 0.0, 0.0)
    assert math.isclose(roll, 180.0, abs_tol=1e-9)
    assert abs(pitch) < 1e-9 and abs(yaw) < 1e-9


def test_rotation_conversion_pitch_flips_sign():
    # ROS pitch +0.5 rad -> CARLA pitch -28.6479deg (pitch axis sign flipped).
    roll, pitch, yaw = ros_rpy_to_carla_rotation(0.0, 0.5, 0.0)
    assert math.isclose(pitch, -math.degrees(0.5), abs_tol=1e-9)  # -28.64789
    assert abs(roll) < 1e-9 and abs(yaw) < 1e-9


# --- composed base_link->sensor rotation from BOTH committed yamls, then convert once ---


def test_top_lidar_composed_carla_rotation():
    # velodyne_top kit (roll 0, pitch 0, yaw 1.575) composed with base->kit
    # (roll -0.001, pitch 0.015, yaw -0.0364) via R = R_bk . R_ks, then rpy re-extracted:
    #   composed ROS rpy = (roll 0.015004, pitch 0.000937, yaw 1.538615) rad
    # Hand check: composed yaw 88.156deg == raw kit yaw 90.240deg MINUS base->kit yaw
    # 2.086deg -- i.e. the two yamls are COMPOSED, not read from one. Convert (roll:+,
    # pitch:-, yaw:-):
    kit = load_kit()
    roll, pitch, yaw = carla_attach_rotation(kit, TOP_LIDAR_FRAME)
    assert math.isclose(roll, 0.859670, abs_tol=1e-4)
    assert math.isclose(pitch, -0.053676, abs_tol=1e-4)
    assert math.isclose(yaw, -88.156119, abs_tol=1e-4)
    # The dominant term is a ~-90deg yaw: the top cloud must arrive rotated in base_link,
    # NOT aligned with the ego (which is what an identity attach would wrongly produce).
    assert abs(yaw) > 80.0


def test_imu_composed_carla_rotation():
    # tamagawa/imu_link kit (roll pi, pitch 0, yaw pi) folded through the small base tilt.
    # Rz(pi).Rx(pi) == Ry(pi), so the kit flip is a 180deg roll about Y; composed with the
    # base (roll -0.001, pitch 0.015, yaw -0.0364) the re-extracted ROS rpy is
    #   (roll -3.140593, pitch -0.015000, yaw 3.105193) rad. Convert (roll:+, pitch:-, yaw:-):
    kit = load_kit()
    roll, pitch, yaw = carla_attach_rotation(kit, IMU_FRAME)
    assert math.isclose(roll, -179.942704, abs_tol=1e-4)
    assert math.isclose(pitch, 0.859437, abs_tol=1e-4)
    assert math.isclose(yaw, -177.914434, abs_tol=1e-4)


def test_velodyne_left_composed_rotation_proves_chain_composes():
    # Off-axis sensor: velodyne_left kit (roll -0.02, pitch 0.71, yaw 1.575). Its composed
    # ROS pitch is 40.7281deg -- NEITHER the bare kit pitch (40.6807deg) NOR a naive rpy sum
    # (0.71+0.015 rad = 41.540deg): the base tilt is folded through the ~90deg kit yaw, which
    # only matrix composition (not componentwise addition of the two yamls) produces.
    kit = load_kit()
    ros = sensor_rotation_in_base_link(kit, "velodyne_left_base_link")
    composed_pitch_deg = math.degrees(ros[1])
    assert math.isclose(composed_pitch_deg, 40.7281, abs_tol=1e-3)
    assert abs(composed_pitch_deg - math.degrees(0.71)) > 1e-2  # != bare kit pitch
    assert abs(composed_pitch_deg - math.degrees(0.71 + 0.015)) > 0.5  # != naive rpy sum
    roll, pitch, yaw = carla_attach_rotation(kit, "velodyne_left_base_link")
    assert math.isclose(roll, -0.011477, abs_tol=1e-4)
    assert math.isclose(pitch, -40.728132, abs_tol=1e-4)
    assert math.isclose(yaw, -88.895557, abs_tol=1e-4)


# --- fail-loudly on missing load-bearing native attributes (run_g0 preflight style) ---


class _FakeBlueprint:
    """Minimal stand-in for a CARLA blueprint for ``_apply_attributes`` unit tests.

    ``set_attribute`` mimics stock CARLA (raises on an undeclared attribute) so a test that
    reaches it on a missing attr would fail loudly too -- but the point is our OWN named,
    actionable error fires first for the load-bearing native attrs.
    """

    def __init__(self, declared, bp_id="sensor.lidar.ray_cast"):
        self._declared = set(declared)
        self.id = bp_id
        self.applied: dict[str, str] = {}

    def has_attribute(self, key):
        return key in self._declared

    def set_attribute(self, key, value):
        assert key in self._declared, f"stock CARLA raises on unknown attribute {key!r}"
        self.applied[key] = value


def test_apply_attributes_fails_loud_on_missing_topic_name():
    # A stock 0.10 build lacking the M1 native-ROS2 patches declares the geometry/QoS attrs
    # but NOT ros_topic_name -> must raise (naming attr + blueprint + M1), never silently
    # drop a stock-layout cloud onto the Autoware topic.
    stock = _FakeBlueprint(
        declared={
            "channels",
            "rotation_frequency",
            "range",
            "ros2_qos_reliability",
            "ros2_qos_durability",
            "ros2_qos_history_depth",
        }
    )
    with pytest.raises(RuntimeError) as exc:
        _apply_attributes(stock, top_lidar_attributes())
    msg = str(exc.value)
    assert "ros_topic_name" in msg  # names the missing attribute
    assert stock.id in msg  # names the blueprint
    assert "M1" in msg  # points at the missing native-ROS2 patches
    assert stock.applied == {}  # ros_topic_name is first -> nothing applied before the raise


def test_apply_attributes_fails_loud_on_missing_extended_lidar():
    # Same mandate, isolating ros2_extended_lidar (ros_topic_name present so the loop reaches
    # it): a build with the topic name but no extended-layout flag would emit a 4-field stock
    # cloud on the _ex topic -- refuse it.
    bp = _FakeBlueprint(
        declared={
            "ros_topic_name",
            "channels",
            "rotation_frequency",
            "range",
            "ros2_qos_reliability",
            "ros2_qos_durability",
            "ros2_qos_history_depth",
        }
    )
    with pytest.raises(RuntimeError) as exc:
        _apply_attributes(bp, top_lidar_attributes())
    assert "ros2_extended_lidar" in str(exc.value)


def test_apply_attributes_skips_optional_ackermann_when_absent():
    # ros2_ackermann_control is genuinely optional (kept behind has_attribute): a build
    # without it still spawns the ego, just without native-Ackermann control routing.
    bp = _FakeBlueprint(declared={"role_name"}, bp_id="vehicle.lincoln.mkz")
    _apply_attributes(bp, ego_attributes())
    assert bp.applied["role_name"] == "ego"
    assert "ros2_ackermann_control" not in bp.applied


def test_apply_attributes_applies_all_when_present():
    # Full native build: every declared attr is applied (no raise, no skip).
    bp = _FakeBlueprint(declared=set(top_lidar_attributes()))
    _apply_attributes(bp, top_lidar_attributes())
    assert bp.applied == top_lidar_attributes()
