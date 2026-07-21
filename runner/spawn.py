"""Spawn the ego + native sensor rig with Autoware topic names / QoS / extended LiDAR.

The heavy lifting (sensor placement, transform composition) lives in ``runner.kit``. This
module owns the CARLA-facing spawn: choosing the ego blueprint, opting the ego into the
native ROS 2 Ackermann control path, and stamping the M1 native-publisher attributes
(``ros_topic_name`` / ``ros2_qos_*`` / ``ros2_extended_lidar``) onto the LiDAR and IMU.

Import discipline: ``carla`` is imported lazily INSIDE the spawn functions, never at module
top level, so this module (and the attribute-builder functions the unit tests exercise)
imports cleanly under bare pytest on a machine with no CARLA egg -- the M0 CI lesson.
"""

from __future__ import annotations

from runner.kit import (
    IMU_FRAME,
    TOP_LIDAR_FRAME,
    KitConfig,
    carla_attach_location,
    carla_attach_rotation,
)

# Ego blueprint: the Lincoln MKZ the ported steering-compensation LERP table
# (AutowareSteeringCompensation.h, Task 20) was measured on. In the CARLA 0.10 (UE5)
# blueprint library the vehicle is id'd WITHOUT the 0.9-era year suffix -- it is
# "vehicle.lincoln.mkz", NOT "vehicle.lincoln.mkz_2020" (0.10 dropped the year suffix on
# every vehicle, e.g. dodge.charger, mini.cooper). The _2020 id does not exist in this
# build (verified live: 17 vehicle blueprints enumerated, only vehicle.lincoln.mkz present);
# finding it raises, which was the Task 23 4b spawn failure until corrected. Its measured
# wheelbase is reconciled against the sample_vehicle 2.79 m that base_link_to_vehicle_center
# assumes; the accepted delta is recorded in docs/nishishinjuku-map.md, not silently absorbed.
EGO_BLUEPRINT = "vehicle.lincoln.mkz"
SAMPLE_VEHICLE_WHEELBASE = 2.79  # sample_vehicle_description/vehicle_info.param.yaml wheel_base

TOP_LIDAR_BLUEPRINT = "sensor.lidar.ray_cast"
IMU_BLUEPRINT = "sensor.other.imu"

# Autoware topic contract (AWSIM template). The top LiDAR publishes the 10-field
# PointXYZIRCAEDT "_ex" cloud at 10 Hz best_effort; the IMU is the tamagawa raw feed.
TOP_LIDAR_TOPIC = "/sensing/lidar/top/pointcloud_raw_ex"
IMU_TOPIC = "/sensing/imu/tamagawa/imu_raw"

# LiDAR ROS 2 QoS: best_effort / volatile / depth 5 to match the AWSIM top-lidar relay
# (the concatenate/relay node subscribes best_effort). depth 5 buffers a few 10 Hz scans.
_LIDAR_QOS_RELIABILITY = "best_effort"
_LIDAR_QOS_DURABILITY = "volatile"
_LIDAR_QOS_HISTORY_DEPTH = "5"

# Velodyne VLS-128 top lidar: 128 channels, 10 Hz spin (the AWSIM top-lidar publish rate,
# NOT the brief-draft's 20 -- the Autoware topic contract is 10 Hz best_effort).
_TOP_LIDAR_CHANNELS = "128"
_TOP_LIDAR_ROTATION_FREQUENCY = "10"
_TOP_LIDAR_RANGE = "120.0"


def ego_attributes() -> dict[str, str]:
    """Ego blueprint attributes: named-ego hero + native Ackermann control opt-in.

    ``role_name`` "ego" is a valid hero criterion (ActorDispatcher registers the sole
    Phase B vehicle as the ROS 2 ego); ``ros2_ackermann_control`` "true" routes the
    ego onto the Ackermann control sink (mutually exclusive with direct VehicleControl).
    """
    return {
        "role_name": "ego",
        "ros2_ackermann_control": "true",
    }


def top_lidar_attributes() -> dict[str, str]:
    """Native ROS 2 attributes + geometry for the top LiDAR (all values are strings)."""
    return {
        "ros_topic_name": TOP_LIDAR_TOPIC,
        "ros2_extended_lidar": "true",
        "ros2_qos_reliability": _LIDAR_QOS_RELIABILITY,
        "ros2_qos_durability": _LIDAR_QOS_DURABILITY,
        "ros2_qos_history_depth": _LIDAR_QOS_HISTORY_DEPTH,
        "channels": _TOP_LIDAR_CHANNELS,
        "rotation_frequency": _TOP_LIDAR_ROTATION_FREQUENCY,
        "range": _TOP_LIDAR_RANGE,
    }


def imu_attributes() -> dict[str, str]:
    """Native ROS 2 attributes for the IMU. The GNSS path is observer-side (poses come
    from the extension), so no CARLA GNSS sensor/topic is spawned here."""
    return {
        "ros_topic_name": IMU_TOPIC,
    }


# Load-bearing native ROS 2 publisher attributes (M1 patches): if the blueprint does not
# declare these, the sensor would silently fall back to a STOCK layout/topic -- the exact
# misconfiguration this repo's fail-loudly mandate exists to catch (a 4-field stock cloud on
# the /..._ex topic, or the wrong topic entirely). We refuse to spawn rather than mislead a
# downstream NDT/detection gate into root-causing a "bad sensor" that is really a bad build.
_REQUIRED_NATIVE_ATTRS = ("ros_topic_name", "ros2_extended_lidar")
# Genuinely optional: a build without native Ackermann routing still spawns the ego (it just
# falls back to direct VehicleControl), so this one keeps the has_attribute skip.
_OPTIONAL_ATTRS = ("ros2_ackermann_control",)


def _apply_attributes(blueprint, attrs: dict[str, str]) -> None:
    """Apply ``attrs`` to ``blueprint``, failing loudly on missing load-bearing native attrs.

    Policy (run_g0.sh preflight style -- name the attribute, the blueprint, and the cause):
      * ``_REQUIRED_NATIVE_ATTRS`` (ros_topic_name / ros2_extended_lidar): RAISE if the
        blueprint does not declare them -- a build lacking the M1 native-ROS2 publisher
        patches must not silently produce a stock-layout cloud on the Autoware topic.
      * ``_OPTIONAL_ATTRS`` (ros2_ackermann_control): SKIP if absent (genuinely optional).
      * everything else (role_name / ros2_qos_* / channels / rotation_frequency / range):
        set unconditionally -- stock geometry attrs always exist, and a missing native QoS
        attr surfaces loudly as CARLA's own set_attribute error.
    """
    for key, value in attrs.items():
        if key in _REQUIRED_NATIVE_ATTRS and not blueprint.has_attribute(key):
            raise RuntimeError(
                f"blueprint {blueprint.id!r} does not declare the required native ROS 2 "
                f"attribute {key!r}: this CARLA build lacks the M1 native-ROS2 publisher "
                f"patches (feat/autoware-seminative-integration middleware). Refusing to "
                f"spawn -- a stock blueprint would emit a stock-layout cloud on the Autoware "
                f"topic and silently mis-feed the NDT/detection gates. Rebuild CARLA with the "
                f"native-ROS2 layer, or verify the blueprint id."
            )
        if key in _OPTIONAL_ATTRS and not blueprint.has_attribute(key):
            continue
        blueprint.set_attribute(key, value)


def spawn_ego(world, blueprint_library, spawn_transform):
    """Spawn the ego vehicle (named-ego hero, Ackermann control opt-in)."""
    blueprint = blueprint_library.find(EGO_BLUEPRINT)
    _apply_attributes(blueprint, ego_attributes())
    return world.spawn_actor(blueprint, spawn_transform)


def ego_wheelbase(ego) -> float:
    """Best-effort measured CARLA wheelbase (m) from physics-control wheel positions.

    Wheel positions are reported in world-scale CENTIMETRES, so divide by 100. In CARLA
    0.10 the field was renamed ``WheelPhysicsControl.position`` -> ``.location``, so read
    ``wheel.location`` here.

    IMPORTANT (verified live, Task 23 4b): the CARLA 0.10 (UE5/Chaos) build does NOT
    populate wheel geometry -- ``location``, ``offset`` and ``old_location`` are all
    (0, 0, 0) for every wheel and there is no ``get_wheel_position`` client API (the
    geometry lives in the vehicle's binary skeletal-mesh sockets). This therefore returns
    0.0 on 0.10; treat a ~0.0 result as "wheelbase unavailable, fall back to the bounding
    box / the sample_vehicle value" rather than a real measurement. The helper is retained
    for builds/versions that DO expose wheel locations. See the "Phase B ego reconciliation"
    section of docs/nishishinjuku-map.md for the live evidence and the reconcile decision.
    """
    physics = ego.get_physics_control()
    xs = [wheel.location.x / 100.0 for wheel in physics.wheels]
    return abs(max(xs) - min(xs))


def _spawn_sensor(world, blueprint_library, ego, blueprint_id, attrs, location, rotation):
    """Attach a sensor to ``ego`` at (``location`` [m], ``rotation`` [deg]) with ``attrs``.

    ``rotation`` is the CARLA/UE Rotator (roll, pitch, yaw) in degrees from
    ``runner.kit.carla_attach_rotation`` -- the composed kit mount rotation, applied here so
    the physical CARLA sensor frame matches the TF Autoware generates from the same kit yamls.
    ``carla`` is imported lazily HERE (never at module top level) so the pure attribute /
    transform math stays importable under bare pytest with no CARLA egg.
    """
    import carla

    blueprint = blueprint_library.find(blueprint_id)
    _apply_attributes(blueprint, attrs)
    transform = carla.Transform(
        carla.Location(x=location[0], y=location[1], z=location[2]),
        carla.Rotation(roll=rotation[0], pitch=rotation[1], yaw=rotation[2]),
    )
    return world.spawn_actor(blueprint, transform, attach_to=ego)


def spawn_top_lidar(
    world, blueprint_library, ego, kit: KitConfig, wheelbase=SAMPLE_VEHICLE_WHEELBASE
):
    """Spawn the top LiDAR at its kit-derived pose (translation + mount rotation) with native
    ROS 2 attributes."""
    location = carla_attach_location(kit, TOP_LIDAR_FRAME, wheelbase)
    rotation = carla_attach_rotation(kit, TOP_LIDAR_FRAME)
    return _spawn_sensor(
        world,
        blueprint_library,
        ego,
        TOP_LIDAR_BLUEPRINT,
        top_lidar_attributes(),
        location,
        rotation,
    )


def spawn_imu(world, blueprint_library, ego, kit: KitConfig, wheelbase=SAMPLE_VEHICLE_WHEELBASE):
    """Spawn the IMU at its kit-derived pose (translation + mount rotation) with the tamagawa
    raw topic. The IMU mount is a ~180deg flip (kit roll/yaw pi), so the rotation is NOT
    cosmetic -- an identity attach would invert the IMU axes and corrupt the ekf."""
    location = carla_attach_location(kit, IMU_FRAME, wheelbase)
    rotation = carla_attach_rotation(kit, IMU_FRAME)
    return _spawn_sensor(
        world, blueprint_library, ego, IMU_BLUEPRINT, imu_attributes(), location, rotation
    )


def spawn_sensors(
    world, blueprint_library, ego, kit: KitConfig, wheelbase=SAMPLE_VEHICLE_WHEELBASE
):
    """Spawn the native sensor rig (top LiDAR + IMU) attached to ``ego``.

    Returns the spawned sensor actors. The GNSS pose is supplied by the extension, so no
    CARLA GNSS sensor is spawned.

    Spawned ONE AT A TIME and accumulated in ``spawned`` as each succeeds, rather than built
    as a single list-literal return: if a LATER sensor spawn raises (e.g. the IMU spawn fails
    after the top LiDAR already succeeded), a list-literal return would lose the reference to
    the already-spawned LiDAR entirely -- this function never returns on the exception path,
    so the caller's ``sensors`` variable stays whatever it was before the call (typically
    ``[]``), its finally-teardown has nothing to destroy, and the orphaned LiDAR actor keeps
    running as a duplicate ROS 2 publisher for every subsequent run. So: on any exception here,
    destroy every actor already spawned in THIS call (each destroy in its own try/except, so a
    secondary destroy failure can never mask the original spawn error or stop the rest from
    being destroyed), then re-raise the original exception unchanged so the caller still sees
    the real failure.
    """
    spawned = []
    try:
        spawned.append(spawn_top_lidar(world, blueprint_library, ego, kit, wheelbase))
        spawned.append(spawn_imu(world, blueprint_library, ego, kit, wheelbase))
    except Exception:
        for actor in spawned:
            try:
                actor.destroy()
            except Exception:
                pass
        raise
    return spawned
