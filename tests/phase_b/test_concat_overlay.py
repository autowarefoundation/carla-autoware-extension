"""Pin the single-LiDAR concatenate overlay (Phase B M4-blocker #2).

The stock awsim_labs concat node waits on 3 pre-sync clouds; the runner spawns 1 top
LiDAR, so the overlay (docker/overlay/.../concatenate_and_time_sync_node.param.yaml)
reduces the concat to that one input and switches to the `naive` strategy. These tests
guard against an accidental edit re-introducing the 1-vs-3 mismatch that left NDT silent,
and against the compose bind-mount being dropped (which would silently restore the stock
3-LiDAR config). Pure YAML parsing -- importable under bare pytest, no ROS/CARLA needed.
"""

from __future__ import annotations

import os

import yaml

from runner.spawn import TOP_LIDAR_ROS_NAME

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_OVERLAY = os.path.join(
    _REPO,
    "docker",
    "overlay",
    "awsim_labs_sensor_kit_launch",
    "config",
    "concatenate_and_time_sync_node.param.yaml",
)
# The container path pointcloud_preprocessor.launch.py loads by default -- the overlay is
# only effective if the compose mount lands exactly here.
_KIT_CONFIG_PATH = (
    "/opt/autoware/share/awsim_labs_sensor_kit_launch/config/"
    "concatenate_and_time_sync_node.param.yaml"
)


def _overlay_params() -> dict:
    with open(_OVERLAY) as f:
        doc = yaml.safe_load(f)
    return doc["/**"]["ros__parameters"]


def test_overlay_has_exactly_one_input_the_top_lidar():
    params = _overlay_params()
    inputs = params["input_topics"]
    assert inputs == ["/sensing/lidar/top/pointcloud_before_sync"]
    # The single concat input must be the SAME LiDAR the runner spawns and frames.
    assert TOP_LIDAR_ROS_NAME == "velodyne_top"
    assert f"/sensing/lidar/top/" in inputs[0]


def test_overlay_uses_naive_strategy_needing_no_per_lidar_arrays():
    params = _overlay_params()
    strategy = params["matching_strategy"]
    assert strategy["type"] == "naive"
    # naive takes no per-LiDAR offset/noise arrays; their presence would mean a stale
    # copy of the advanced config whose array length must match len(input_topics).
    assert "lidar_timestamp_offsets" not in strategy
    assert "lidar_timestamp_noise_window" not in strategy


def test_compose_mounts_overlay_over_the_kit_default_path():
    with open(os.path.join(_REPO, "docker", "compose.yaml")) as f:
        compose = yaml.safe_load(f)
    volumes = compose["services"]["autoware"]["volumes"]
    targets = [v.split(":", 2)[1] for v in volumes if v.count(":") >= 1]
    assert _KIT_CONFIG_PATH in targets, (
        "compose.yaml must bind-mount the single-LiDAR overlay over the kit's default "
        f"concat config path {_KIT_CONFIG_PATH!r}, or the stock 3-LiDAR config silently wins"
    )
