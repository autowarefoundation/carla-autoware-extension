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
# (AutowareSteeringCompensation.h) was measured on. In the CARLA 0.10 (UE5)
# blueprint library the vehicle is id'd WITHOUT the 0.9-era year suffix -- it is
# "vehicle.lincoln.mkz", NOT "vehicle.lincoln.mkz_2020" (0.10 dropped the year suffix on
# every vehicle, e.g. dodge.charger, mini.cooper). The _2020 id does not exist in this
# build (verified live: 17 vehicle blueprints enumerated, only vehicle.lincoln.mkz present);
# finding it raises, which was the initial live spawn failure until corrected.
EGO_BLUEPRINT = "vehicle.lincoln.mkz"

TOP_LIDAR_BLUEPRINT = "sensor.lidar.ray_cast"
IMU_BLUEPRINT = "sensor.other.imu"

# Autoware topic contract (AWSIM template). The top LiDAR publishes the 10-field
# PointXYZIRCAEDT "_ex" cloud at 10 Hz best_effort; the IMU is the tamagawa raw feed.
TOP_LIDAR_TOPIC = "/sensing/lidar/top/pointcloud_raw_ex"
IMU_TOPIC = "/sensing/imu/tamagawa/imu_raw"

# Top LiDAR header.frame_id. This is the M4-blocker-#1 fix (docs/phase-b-report.md):
# without a `ros_name` attribute the fork's ActorDispatcher (ActorDispatcher.cpp:275-293)
# mangles the blueprint id into "ray_cast__" and uses THAT as both ros_name and the
# published cloud's header.frame_id. "ray_cast__" is absent from the TF tree Autoware
# builds from the sensor kit (which has only base_link / sensor_kit_base_link /
# velodyne_{top,left,right,rear}), so `crop_box_filter_self` cannot transform the cloud
# and silently drops every frame -- killing the entire localization chain. Naming the
# frame "velodyne_top" (the kit's top-LiDAR sensor frame, per the report's proven
# diagnostic and the AWSIM convention) slots the cloud into that tree. `ros_name` is a
# real, settable blueprint attribute in the fork (ActorBlueprintFunctionLibrary.cpp:230),
# so this needs no CARLA rebuild.
#
# KNOWN RESIDUAL (bounded, within the gate): the runner mounts the sensor at the
# velodyne_top_base_link calibration pose (TOP_LIDAR_FRAME below), but the VLS-128 URDF
# places the `velodyne_top` sensor frame +0.06611 m in Z above velodyne_top_base_link
# (vls_description VLS-128.urdf.xacro base_scan_joint). So Autoware's TF interprets the
# cloud ~6.6 cm higher than the sensor physically sits -- a systematic Z bias well inside
# the G1 gross-error gate (max_err <= 0.5 m, XY). Zeroing it (mount at velodyne_top by
# adding that sensor-frame offset, or label the cloud velodyne_top_base_link) is a
# precision refinement to confirm against the live TF tree in the staged E2E re-run.
TOP_LIDAR_ROS_NAME = "velodyne_top"

# LiDAR ROS 2 QoS: best_effort / volatile / depth 5 to match the AWSIM top-lidar relay
# (the concatenate/relay node subscribes best_effort). depth 5 buffers a few 10 Hz scans.
_LIDAR_QOS_RELIABILITY = "best_effort"
_LIDAR_QOS_DURABILITY = "volatile"
_LIDAR_QOS_HISTORY_DEPTH = "5"

# Velodyne VLS-128 top lidar: 128 channels, 10 Hz spin (the AWSIM top-lidar publish rate,
# NOT a naively-assumed 20 -- the Autoware topic contract is 10 Hz best_effort).
_TOP_LIDAR_CHANNELS = "128"
_TOP_LIDAR_ROTATION_FREQUENCY = "10"
_TOP_LIDAR_RANGE = "120.0"

# sensor_tick pins the capture period (sim seconds) so each cloud is a fixed 0.05 s
# accumulation REGARDLESS of the host loop mode. In sync (0.05 fixed delta) this matches the
# tick, so it is a no-op -- one ~half-rotation cloud per tick at ~20 Hz. In ASYNC (the G2
# propulsion mode) the server free-runs at ~140 fps, and WITHOUT this the native LiDAR emits
# one thin ~25-deg, ~2k-point slice PER SERVER FRAME (~140 Hz). NDT cannot match those
# fragments (transform_probability ~3.97, pose jittered ~4 m off ground truth), which would
# fail G2's 1.0 m goal tolerance even though the ego drives the route. Pinning sensor_tick
# restores full 0.05 s clouds (~15k points) at 20 Hz in async too, so NDT locks the same as
# sync. Verified live 2026-07-23. Applied to the IMU as well so it does not flood at ~140 Hz.
_SENSOR_TICK = "0.05"


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
        # Required M1-discriminator attrs first: `_apply_attributes` raises its named,
        # actionable error on these BEFORE mutating the blueprint, so a stock build lacking
        # the native-ROS2 patches fails loudly rather than half-configured. `ros_name`
        # (the blocker-1 frame_id fix) is a naming attr set unconditionally like role_name,
        # so it deliberately follows the two required discriminators.
        "ros_topic_name": TOP_LIDAR_TOPIC,
        "ros2_extended_lidar": "true",
        "ros_name": TOP_LIDAR_ROS_NAME,
        "ros2_qos_reliability": _LIDAR_QOS_RELIABILITY,
        "ros2_qos_durability": _LIDAR_QOS_DURABILITY,
        "ros2_qos_history_depth": _LIDAR_QOS_HISTORY_DEPTH,
        "channels": _TOP_LIDAR_CHANNELS,
        "rotation_frequency": _TOP_LIDAR_ROTATION_FREQUENCY,
        "range": _TOP_LIDAR_RANGE,
        "sensor_tick": _SENSOR_TICK,
    }


def imu_attributes() -> dict[str, str]:
    """Native ROS 2 attributes for the IMU. The GNSS path is observer-side (poses come
    from the extension), so no CARLA GNSS sensor/topic is spawned here."""
    return {
        "ros_topic_name": IMU_TOPIC,
        "sensor_tick": _SENSOR_TICK,
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


def spawn_top_lidar(world, blueprint_library, ego, kit: KitConfig):
    """Spawn the top LiDAR at its kit-derived pose (translation + mount rotation) with native
    ROS 2 attributes."""
    location = carla_attach_location(kit, TOP_LIDAR_FRAME)
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


def spawn_imu(world, blueprint_library, ego, kit: KitConfig):
    """Spawn the IMU at its kit-derived pose (translation + mount rotation) with the tamagawa
    raw topic. The IMU mount is a ~180deg flip (kit roll/yaw pi), so the rotation is NOT
    cosmetic -- an identity attach would invert the IMU axes and corrupt the ekf."""
    location = carla_attach_location(kit, IMU_FRAME)
    rotation = carla_attach_rotation(kit, IMU_FRAME)
    return _spawn_sensor(
        world, blueprint_library, ego, IMU_BLUEPRINT, imu_attributes(), location, rotation
    )


def spawn_sensors(world, blueprint_library, ego, kit: KitConfig):
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
        spawned.append(spawn_top_lidar(world, blueprint_library, ego, kit))
        spawned.append(spawn_imu(world, blueprint_library, ego, kit))
    except Exception:
        for actor in spawned:
            try:
                actor.destroy()
            except Exception:
                pass
        raise
    return spawned
