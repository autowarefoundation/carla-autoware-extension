"""Sensor-kit calibration loader + base_link -> CARLA-vehicle transform math.

The Autoware sensor kit is the single source of truth for sensor placement. Two
calibration files describe the rig as a chain of static transforms:

  * ``sensors_calibration.yaml``     : base_link -> sensor_kit_base_link
  * ``sensor_kit_calibration.yaml``  : sensor_kit_base_link -> each sensor frame

The full pose of a sensor in base_link is the composition of the two. Because the
kit-level rotation is small but *materially non-zero* (yaw -0.0364 rad ~ -2.09 deg,
pitch 0.015 rad, roll -0.001 rad in the committed ``awsim_labs_sensor_kit`` calibration),
a bare per-axis translation sum is NOT correct for off-centreline sensors: it misplaces
e.g. ``velodyne_left`` (0.59 m off-axis) by ~1.7 cm in X. We therefore compose properly,
rotating the kit-level sensor offset by the base_link->kit rotation matrix before adding
the kit translation (``sensor_in_base_link``). For the top LiDAR and IMU, which sit at the
sensor_kit_base_link origin (kit offset 0,0,0), the composed result reduces to the
base_link->sensor_kit_base_link translation exactly, independent of the rotation.

Frame notes:
  * base_link is the REAR-AXLE centre (Autoware / ROS: X forward, Y left, Z up).
  * CARLA attaches sensors relative to the vehicle ORIGIN (~mid-wheelbase). The
    base_link -> vehicle-origin conversion shifts +wheelbase/2 forward in X
    (``base_link_to_vehicle_center``). Z passes through unchanged -- this ASSUMES the
    CARLA vehicle origin sits at base_link height (ground); the assumption is validated
    live by comparing the spawned top-lidar world transform to the ego's (see the
    "Phase B ego reconciliation" section of docs/nishishinjuku-map.md).
  * Handedness: CARLA's vehicle frame is left-handed (Y to the RIGHT) while base_link is
    right-handed (Y to the LEFT), related by the Y-flip M = diag(1,-1,1).
      - ROTATION is now applied (``carla_attach_rotation``): the composed base_link->sensor
        orientation is converted to a CARLA/UE Rotator via the M-conjugation mapping
        (roll:+, pitch:-, yaw:-; see ``ros_rpy_to_carla_rotation``). This is load-bearing:
        the runner calls ``world.set_publish_tf(False)`` (Task 24) so Autoware owns the TF
        tree and generates sensor TF from these SAME yamls; if CARLA attached at identity the
        top cloud would arrive ~90deg-rotated in base_link (NDT/G1 dead on arrival) and the
        IMU axes flipped (ekf/G2 corrupted). The kit mount rotations (velodyne_top yaw 1.575,
        IMU roll/yaw pi) MUST be applied at attach time to match that TF.
      - TRANSLATION Y-flip: every sensor this runner actually spawns (top LiDAR, IMU) sits on
        the centreline (kit Y = 0), so the +/-Y sign is immaterial and the position Y is
        carried through verbatim. Extending the rig to OFF-centre sensors (side LiDARs,
        cameras) would additionally require negating the position Y at the CARLA boundary;
        that is intentionally out of scope here and flagged rather than silently applied,
        because the live gross-error gate (a centreline top LiDAR) cannot verify a Y flip.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

import yaml

# The launch template uses sensor_model:=awsim_labs_sensor_kit, so the description package
# (and the provenance of the committed calibration yamls under runner/config/) is this one.
SENSOR_KIT_PACKAGE = "awsim_labs_sensor_kit_description"

_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
DEFAULT_SENSOR_KIT_CALIBRATION = os.path.join(_CONFIG_DIR, "sensor_kit_calibration.yaml")
DEFAULT_SENSORS_CALIBRATION = os.path.join(_CONFIG_DIR, "sensors_calibration.yaml")

# Frame ids used by the AWSIM-Labs kit for the sensors this runner spawns.
TOP_LIDAR_FRAME = "velodyne_top_base_link"
IMU_FRAME = "tamagawa/imu_link"

# Top-level keys of the two calibration files.
_BASE_LINK_KEY = "base_link"
_SENSOR_KIT_BASE_KEY = "sensor_kit_base_link"


@dataclass(frozen=True)
class Transform6:
    """A static 6-DoF transform (metres, radians) in the Autoware/URDF convention."""

    x: float
    y: float
    z: float
    roll: float
    pitch: float
    yaw: float

    @classmethod
    def from_mapping(cls, mapping: dict) -> "Transform6":
        return cls(
            x=float(mapping["x"]),
            y=float(mapping["y"]),
            z=float(mapping["z"]),
            roll=float(mapping["roll"]),
            pitch=float(mapping["pitch"]),
            yaw=float(mapping["yaw"]),
        )


@dataclass(frozen=True)
class KitConfig:
    """Parsed sensor-kit calibration: base_link->kit plus kit->each-sensor."""

    base_to_kit: Transform6
    kit_to_sensor: dict[str, Transform6]


def load_kit(
    sensor_kit_calibration: str = DEFAULT_SENSOR_KIT_CALIBRATION,
    sensors_calibration: str = DEFAULT_SENSORS_CALIBRATION,
) -> KitConfig:
    """Load the two calibration yamls into a :class:`KitConfig`.

    Both arguments default to the committed copies under ``runner/config/`` (extracted from
    ``awsim_labs_sensor_kit_description`` in the pinned Autoware image). The primary
    positional argument is the kit-level calibration; the base_link->kit file defaults
    alongside it.
    """
    with open(sensors_calibration) as f:
        sensors_doc = yaml.safe_load(f)
    with open(sensor_kit_calibration) as f:
        kit_doc = yaml.safe_load(f)

    base_to_kit = Transform6.from_mapping(sensors_doc[_BASE_LINK_KEY][_SENSOR_KIT_BASE_KEY])
    kit_to_sensor = {
        name: Transform6.from_mapping(tf) for name, tf in kit_doc[_SENSOR_KIT_BASE_KEY].items()
    }
    return KitConfig(base_to_kit=base_to_kit, kit_to_sensor=kit_to_sensor)


def _rotation_matrix(roll: float, pitch: float, yaw: float) -> tuple[tuple[float, ...], ...]:
    """URDF/TF extrinsic-xyz rotation matrix R = Rz(yaw) @ Ry(pitch) @ Rx(roll)."""
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return (
        (cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr),
        (sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr),
        (-sp, cp * sr, cp * cr),
    )


def _apply(matrix, vec):
    return tuple(sum(matrix[i][k] * vec[k] for k in range(3)) for i in range(3))


def sensor_in_base_link(kit: KitConfig, sensor_frame: str) -> tuple[float, float, float]:
    """Return the ``(x, y, z)`` of ``sensor_frame`` in base_link (ROS frame, metres).

    Composes base_link->sensor_kit_base_link with sensor_kit_base_link->sensor, applying
    the kit-level rotation to the sensor's kit offset (see module docstring for why a bare
    translation sum is insufficient for off-centre sensors).
    """
    bk = kit.base_to_kit
    sensor = kit.kit_to_sensor[sensor_frame]
    rot = _rotation_matrix(bk.roll, bk.pitch, bk.yaw)
    rx, ry, rz = _apply(rot, (sensor.x, sensor.y, sensor.z))
    return (bk.x + rx, bk.y + ry, bk.z + rz)


def _matmul(a, b):
    """3x3 matrix product a @ b (row-major tuples-of-tuples)."""
    return tuple(
        tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3)
    )


def _rpy_from_matrix(matrix) -> tuple[float, float, float]:
    """Extract ``(roll, pitch, yaw)`` [rad, ROS/URDF] from a rotation matrix built as
    ``R = Rz(yaw) @ Ry(pitch) @ Rx(roll)`` -- the exact inverse of :func:`_rotation_matrix`.

    Non-singular branch: pitch = atan2(-R20, |cos pitch|), yaw = atan2(R10, R00),
    roll = atan2(R21, R22). At the gimbal singularity (pitch = +-90deg, cos pitch -> 0) the
    yaw/roll terms both collapse to 0/0, so we pin yaw = 0 and recover the combined roll+-yaw
    from (-R12, R11); this uses the guarded ``math.hypot`` magnitude so it never divides 0/0.
    None of the AWSIM-Labs kit sensors sit at |pitch| = 90deg (max is velodyne_left ~40.7deg),
    but the guard keeps the extraction total for any composed chain.
    """
    cos_pitch = math.hypot(matrix[0][0], matrix[1][0])  # = |cos(pitch)|
    if cos_pitch > 1e-9:
        roll = math.atan2(matrix[2][1], matrix[2][2])
        pitch = math.atan2(-matrix[2][0], cos_pitch)
        yaw = math.atan2(matrix[1][0], matrix[0][0])
    else:
        roll = math.atan2(-matrix[1][2], matrix[1][1])
        pitch = math.atan2(-matrix[2][0], cos_pitch)
        yaw = 0.0
    return roll, pitch, yaw


def sensor_rotation_in_base_link(kit: KitConfig, sensor_frame: str) -> tuple[float, float, float]:
    """Return the composed ``(roll, pitch, yaw)`` [rad, ROS] of ``sensor_frame`` in base_link.

    The sensor's orientation in base_link is the ROTATION composition
    ``R = R(base_link->sensor_kit_base_link) @ R(sensor_kit_base_link->sensor)``; we multiply
    the two matrices and re-extract rpy. This is NOT a componentwise sum of the two yamls'
    rpy entries -- extrinsic Rz.Ry.Rx does not commute, so a per-axis sum is only correct when
    the two frames' axes align. Concretely: the top LiDAR's kit yaw (1.575) combines with the
    base->kit yaw (-0.0364) into a composed 1.5386 (not a bare 1.575), and the IMU's kit flip
    (roll pi, yaw pi == a 180deg roll about Y) folds through the small base tilt.
    """
    bk = kit.base_to_kit
    sensor = kit.kit_to_sensor[sensor_frame]
    composed = _matmul(
        _rotation_matrix(bk.roll, bk.pitch, bk.yaw),
        _rotation_matrix(sensor.roll, sensor.pitch, sensor.yaw),
    )
    return _rpy_from_matrix(composed)


def ros_rpy_to_carla_rotation(roll: float, pitch: float, yaw: float) -> tuple[float, float, float]:
    """Convert a ROS/URDF ``(roll, pitch, yaw)`` [rad] to a CARLA/UE Rotator ``(roll, pitch,
    yaw)`` [deg].

    CARLA/UE is left-handed (Y to the RIGHT, X forward, Z up); ROS/base_link is right-handed
    (Y to the LEFT). The two frames are related by the Y-flip ``M = diag(1, -1, 1)``.
    Conjugating a rotation by M (``R_ue-basis = M @ R_ros @ M``) negates the effective sense of
    a rotation about each axis; the UE Rotator's own left-handed sign convention then re-flips
    the ROLL axis, so the NET componentwise mapping is ``roll:+, pitch:-, yaw:-``. This is
    identical to carla-ros-bridge's ``carla_rotation_to_RPY`` inverse and consistent with the
    Task-19 quaternion pin ``carla_quat_to_mgrs = (-qx, qy, -qz, qw)`` (an involution derived
    via ``R(theta, n) -> R(theta, -M n)``).

    CRITICAL: apply this ONCE, to the fully composed base_link->sensor rpy -- never map the two
    yamls' rpy entries componentwise before composing (see :func:`sensor_rotation_in_base_link`).
    Pins (tests): identity->(0,0,0); ros yaw +90deg -> carla yaw -90deg;
    ros roll pi -> carla roll +180deg; ros pitch +theta -> carla pitch -theta.
    """
    return (math.degrees(roll), -math.degrees(pitch), -math.degrees(yaw))


def carla_attach_rotation(kit: KitConfig, sensor_frame: str) -> tuple[float, float, float]:
    """Full rotation pipeline: compose the sensor orientation in base_link across BOTH yamls,
    then convert once to a CARLA/UE Rotator (deg). Returns ``(roll, pitch, yaw)`` in degrees,
    ready to feed ``carla.Rotation(...)`` at attach time so the physical CARLA sensor frame
    matches the TF Autoware generates from the same kit yamls (the runner owns no TF --
    ``world.set_publish_tf(False)``). No wheelbase argument: a translation shift does not
    change orientation.
    """
    return ros_rpy_to_carla_rotation(*sensor_rotation_in_base_link(kit, sensor_frame))


def base_link_to_vehicle_center(xyz, wheelbase: float):
    """Shift a base_link-referenced ``(x, y, z)`` to the CARLA vehicle origin.

    base_link is the rear-axle centre; CARLA attaches sensors relative to the vehicle
    origin (~mid-wheelbase), so shift +wheelbase/2 forward in X. Y and Z pass through
    unchanged (the Z pass-through assumes the vehicle origin sits at base_link height;
    validated live -- see docs/nishishinjuku-map.md).
    """
    x, y, z = xyz
    return (x + wheelbase / 2.0, y, z)


def carla_attach_location(kit: KitConfig, sensor_frame: str, wheelbase: float):
    """Full pipeline: compose the sensor pose in base_link, then shift to vehicle origin.

    Returns the ``(x, y, z)`` a CARLA sensor should be attached at, relative to the ego
    vehicle. Handedness: for the centreline sensors this runner spawns (kit Y = 0) the ROS
    vs CARLA Y sign is immaterial and carried through verbatim (see module docstring).
    """
    return base_link_to_vehicle_center(sensor_in_base_link(kit, sensor_frame), wheelbase)
