"""End-to-end contract test for bench_observer/bench_pub.

Starts the bench-observer:universe-devel image (see
benchmarks/docker/bench-observer.Dockerfile, digest pinned in
benchmarks/pins.yaml under bench_observer_images), runs a synthetic
bench_pub publisher against a bench_observer recorder inside the
container for a fixed 5 s window, then reads the resulting observer.csv
back on the host through the *real* benchmarks.analysis.bench_io readers
-- the same code path the analysis pipeline uses -- so this test verifies
the CSV contract as actually produced, not as re-typed in the test. It
also exercises bench_observer's two constructor-time failure paths
(unwritable out_dir, malformed topic spec): both only exist compiled
inside the pinned image, so docker is the only way to reach them.

Everything here is one pytest item (not several) so the file contributes
exactly one skip to the default (no BENCH_E2E) run, regardless of how
many scenarios it covers -- see the commit history for why that count is
pinned.

Docker-gated: skipped unless BENCH_E2E=1, since it needs the prebuilt
image and takes several seconds of wall time.
"""

from __future__ import annotations

import os
import subprocess

import numpy as np
import pytest

from benchmarks.analysis.bench_io import (
    read_clock_csv,
    read_observer_csv,
    read_pose_csv,
    read_tf_csv,
)
from benchmarks.analysis.cadence import inter_arrival_stats

pytestmark = pytest.mark.skipif(
    os.environ.get("BENCH_E2E") != "1", reason="docker end-to-end; set BENCH_E2E=1"
)

IMAGE = "bench-observer:universe-devel"
TOPIC = "/bench/cloud"
RATE_HZ = 10.0
POINTS_PER_MSG = 1000
POINT_STEP = 32
RUN_SECONDS = 5

_SOURCE_ENV = (
    ". /opt/ros/humble/setup.sh; "
    "if [ -f /opt/autoware/setup.bash ]; then . /opt/autoware/setup.bash; fi; "
    ". /ws/install/setup.bash"
)
_BIN = "/ws/install/bench_observer/lib/bench_observer"

# Runs bench_pub and bench_observer as direct children of the container's
# PID 1 (not through the `ros2 run` Python wrapper, whose PID does not
# forward signals to the real binary), waits RUN_SECONDS, then sends each
# a real SIGINT -- the signal rclcpp's own handler turns into a clean
# context shutdown, so main() returns normally and the ofstream
# destructors flush their buffers. A plain `kill`/SIGTERM (the bash
# default) has no such handler here: the process dies with its write
# buffer unflushed, and the CSV comes back empty.
_RUN_SCRIPT = rf"""
set -e
{_SOURCE_ENV}
"{_BIN}/bench_pub" --ros-args \
  -p topic:={TOPIC} -p rate_hz:={RATE_HZ} \
  -p points_per_msg:={POINTS_PER_MSG} -p point_step:={POINT_STEP} &
PUB_PID=$!
"{_BIN}/bench_observer" --ros-args \
  -p out_dir:=/out -p "topics:=[{TOPIC}|sensor_msgs/msg/PointCloud2|generic]" &
OBS_PID=$!
sleep {RUN_SECONDS}
kill -INT "$PUB_PID" "$OBS_PID"
wait "$PUB_PID" "$OBS_PID"
"""


def _docker_run(volume: str, script: str, *, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "run", "--rm", "-v", volume, IMAGE, "bash", "-lc", script],
        timeout=timeout,
        capture_output=True,
        text=True,
    )


def _assert_ok(result: subprocess.CompletedProcess, args_repr: str) -> None:
    """Surfaces captured stdout/stderr on failure.

    CalledProcessError's default __str__ omits them, so a live failure
    with plain check=True would give no diagnostic without a manual
    re-run; assert on the returncode ourselves instead.
    """
    assert result.returncode == 0, (
        f"{args_repr} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


def test_observer_contract(tmp_path):
    _assert_happy_path(tmp_path / "bench_observer_out")
    _assert_typed_pose_and_tf_kinds(tmp_path / "typed_out")
    _assert_unwritable_out_dir_fails_loudly(tmp_path / "ro_out")
    _assert_malformed_spec_fails_loudly(tmp_path / "malformed_spec_out")
    _assert_five_field_spec_fails_loudly(tmp_path / "five_field_out")
    _assert_tf_without_a_child_frame_fails_loudly(tmp_path / "tf_no_arg_out")
    _assert_two_tf_specs_on_one_topic_fail_loudly(tmp_path / "tf_dup_out")


def _assert_happy_path(out_dir):
    out_dir.mkdir()
    # No --gpus/nvidia-container-toolkit: unlike bridge_bench, this image
    # never touches CUDA (rclcpp-only recorder/publisher), and the build +
    # this run both succeed against the CUDA base with no GPU flags.
    result = _docker_run(f"{out_dir}:/out", _RUN_SCRIPT, timeout=60)
    _assert_ok(result, "docker run (happy path)")

    d = read_observer_csv(out_dir / "observer.csv")
    assert TOPIC in d
    cloud = d[TOPIC]

    # ~50 rows for 5 s @ 10 Hz.
    n = cloud["arrival_system_ns"].size
    expected = RATE_HZ * RUN_SECONDS
    assert expected * 0.7 <= n <= expected * 1.3, f"expected ~{expected} rows, got {n}"

    # 1000 pts * 32 B payload plus CDR/PointCloud2 header overhead.
    payload = POINTS_PER_MSG * POINT_STEP
    size_bytes = cloud["size_bytes"]
    assert np.all(size_bytes > payload), (
        f"size_bytes must exceed the {payload}-byte payload "
        f"(CDR + PointCloud2 header overhead); got min={size_bytes.min()}"
    )

    # Arrivals come back in file order, and that order is chronological.
    arrivals = cloud["arrival_system_ns"]
    assert np.all(np.diff(arrivals) > 0)

    # No /clock publisher runs in this container, so the observer never
    # sees a clock tick: the sentinel holds throughout, and clock.csv
    # itself stays header-only.
    assert np.all(cloud["clock_ns"] == -1)
    clock, _wall = read_clock_csv(out_dir / "clock.csv")
    assert clock.size == 0

    stats = inter_arrival_stats(arrivals)
    assert stats.hz == pytest.approx(RATE_HZ, abs=1.0)


# --- the typed `pose` and `tf` kinds --------------------------------------
#
# Driven by `ros2 topic pub` rather than a bench_pub-style C++ publisher: the
# only thing the two kinds need on the wire is a real message of the right
# type at a known stamp, and no Autoware node is invented to produce it. The
# published values are chosen so a wrong implementation cannot pass:
#
#   * the pose's x/y are LARGE (Nishi-Shinjuku magnitudes) with 7 decimals, so
#     std::ostream's default 6 SIGNIFICANT digits would record 81371.1 while
#     the required fixed 4-decimal format records 81371.1235.
#   * the /tf message carries TWO transforms, only one matching the registered
#     child_frame_id, and the non-matching one's stamp is 999 s. A kind with no
#     frame filter would record both (an aggregate rate) and a generic
#     subscription's `stamp_from_cdr` would read the SEQUENCE LENGTH (2) at CDR
#     byte 4 and record ~2e9 instead of the transform's own 7.125e9.
POSE_TOPIC = "/localization/pose_estimator/pose_with_covariance"
TF_TOPIC = "/tf"
TF_CHILD = "base_link"
TF_OTHER_CHILD = "velodyne_top"
POSE_STAMP_NS = 12_250_000_000
POSE_X_RECORDED = 81371.1235
POSE_Y_RECORDED = 49912.7654
TF_STAMP_NS = 7_125_000_000
TF_OTHER_STAMP_NS = 999_000_000_000
TF_SEQUENCE_LENGTH_AS_STAMP_NS = 2_000_000_000

# Plain (non-f) strings: the ROS message YAML is all braces.
_POSE_MSG = (
    "{header: {stamp: {sec: 12, nanosec: 250000000}, frame_id: map}, "
    "pose: {pose: {position: {x: 81371.1234567, y: 49912.7654321, z: 0.5}}}}"
)
_TF_MSG = (
    "{transforms: ["
    "{header: {stamp: {sec: 7, nanosec: 125000000}, frame_id: map}, "
    "child_frame_id: base_link, transform: {translation: {x: 1.0, y: 2.0, z: 0.0}}}, "
    "{header: {stamp: {sec: 999, nanosec: 0}, frame_id: base_link}, "
    "child_frame_id: velodyne_top, transform: {translation: {x: 0.0, y: 0.0, z: 2.0}}}]}"
)

_TYPED_SCRIPT = f"""
set -e
{_SOURCE_ENV}
"{_BIN}/bench_observer" --ros-args -p out_dir:=/out -p \
  "topics:=[{POSE_TOPIC}|geometry_msgs/msg/PoseWithCovarianceStamped|pose,\
{TF_TOPIC}|tf2_msgs/msg/TFMessage|tf|{TF_CHILD}]" &
OBS_PID=$!
sleep 3
ros2 topic pub -r {RATE_HZ:g} {POSE_TOPIC} \
  geometry_msgs/msg/PoseWithCovarianceStamped '{_POSE_MSG}' >/dev/null 2>&1 &
POSE_PID=$!
ros2 topic pub -r {RATE_HZ:g} {TF_TOPIC} \
  tf2_msgs/msg/TFMessage '{_TF_MSG}' >/dev/null 2>&1 &
TF_PID=$!
sleep {RUN_SECONDS}
kill -INT "$POSE_PID" "$TF_PID" "$OBS_PID" || true
wait "$OBS_PID"
"""


def _assert_typed_pose_and_tf_kinds(out_dir):
    out_dir.mkdir()
    result = _docker_run(f"{out_dir}:/out", _TYPED_SCRIPT, timeout=120)
    _assert_ok(result, "docker run (typed pose + tf kinds)")

    poses = read_pose_csv(out_dir / "pose.csv")
    assert POSE_TOPIC in poses, f"pose.csv recorded {sorted(poses)}"
    pose = poses[POSE_TOPIC]
    assert pose["header_stamp_ns"].size > 0
    assert np.all(pose["header_stamp_ns"] == POSE_STAMP_NS)
    # Exact equality at 4 decimals: the ostream default (6 significant digits)
    # would have written 81371.1, which is 0.02 m away and would fail here.
    np.testing.assert_allclose(pose["x_m"], POSE_X_RECORDED, atol=1e-9)
    np.testing.assert_allclose(pose["y_m"], POSE_Y_RECORDED, atol=1e-9)

    tf = read_tf_csv(out_dir / "tf.csv")
    assert set(tf) == {(TF_TOPIC, TF_CHILD)}, (
        f"tf.csv must hold ONLY the registered child frame; got {sorted(tf)}"
    )
    stamps = tf[(TF_TOPIC, TF_CHILD)]["header_stamp_ns"]
    assert stamps.size > 0
    assert np.all(stamps == TF_STAMP_NS), (
        "the recorded stamp must be the MATCHING transform's own header stamp, "
        f"not {TF_OTHER_STAMP_NS} (the other transform's) and not "
        f"{TF_SEQUENCE_LENGTH_AS_STAMP_NS} (the CDR sequence length a generic "
        "subscription would read at byte 4)"
    )
    assert tf[(TF_TOPIC, TF_CHILD)]["frame_ids"] == ("map",)

    # Both typed kinds also emit an observer.csv row with the 0 size sentinel,
    # exactly as the `odometry` kind does, and the tf rows there are the
    # FILTERED ones -- one per matching transform, not one per message.
    obs = read_observer_csv(out_dir / "observer.csv")
    assert POSE_TOPIC in obs and TF_TOPIC in obs
    assert np.all(obs[POSE_TOPIC]["size_bytes"] == 0)
    assert np.all(obs[TF_TOPIC]["size_bytes"] == 0)
    assert np.all(obs[TF_TOPIC]["header_stamp_ns"] == TF_STAMP_NS)
    assert obs[TF_TOPIC]["header_stamp_ns"].size == stamps.size


def _assert_five_field_spec_fails_loudly(out_dir):
    """A fourth field is optional; a FIFTH is refused. The three-field parser
    silently discarded any tail, so a misplaced filter would have produced an
    unfiltered recording that looked filtered."""
    out_dir.mkdir()
    bad_spec = f"{TF_TOPIC}|tf2_msgs/msg/TFMessage|tf|{TF_CHILD}|extra"
    script = (
        f'{_SOURCE_ENV}; "{_BIN}/bench_observer" --ros-args '
        f'-p out_dir:=/out -p "topics:=[{bad_spec}]"'
    )
    result = _docker_run(f"{out_dir}:/out", script, timeout=30)
    assert result.returncode != 0
    assert "malformed topic spec" in result.stderr


def _assert_tf_without_a_child_frame_fails_loudly(out_dir):
    """An unfiltered /tf recording is the failure this kind exists to prevent,
    so a `tf` spec with no fourth field must not start."""
    out_dir.mkdir()
    script = (
        f'{_SOURCE_ENV}; "{_BIN}/bench_observer" --ros-args '
        f'-p out_dir:=/out -p "topics:=[{TF_TOPIC}|tf2_msgs/msg/TFMessage|tf]"'
    )
    result = _docker_run(f"{out_dir}:/out", script, timeout=30)
    assert result.returncode != 0
    assert "needs a child_frame_id" in result.stderr


def _assert_two_tf_specs_on_one_topic_fail_loudly(out_dir):
    """Two child frames on one topic would interleave in observer.csv under one
    `topic` key, so a rate taken there would silently be their sum."""
    out_dir.mkdir()
    specs = (
        f"{TF_TOPIC}|tf2_msgs/msg/TFMessage|tf|{TF_CHILD},"
        f"{TF_TOPIC}|tf2_msgs/msg/TFMessage|tf|{TF_OTHER_CHILD}"
    )
    script = (
        f'{_SOURCE_ENV}; "{_BIN}/bench_observer" --ros-args -p out_dir:=/out -p "topics:=[{specs}]"'
    )
    result = _docker_run(f"{out_dir}:/out", script, timeout=30)
    assert result.returncode != 0
    assert "two `tf` specs for topic" in result.stderr


def _assert_unwritable_out_dir_fails_loudly(ro_dir):
    """A bad bind-mount must abort startup, not silently record nothing."""
    ro_dir.mkdir()
    # No "topics" param: the node's default (empty vector) is enough to
    # exercise the ofstream-open check, without touching the unrelated
    # ROS2 CLI quirk where -p "topics:=[]" fails to parse as an empty
    # list ("No parameter value set") before the node is even created.
    script = f'{_SOURCE_ENV}; "{_BIN}/bench_observer" --ros-args -p out_dir:=/out'
    result = _docker_run(f"{ro_dir}:/out:ro", script, timeout=30)
    assert result.returncode != 0
    assert "cannot open output file" in result.stderr
    assert "/out/observer.csv" in result.stderr


def _assert_malformed_spec_fails_loudly(out_dir):
    """A spec missing a field must be rejected at parse time, not silently
    fall through to create_generic_subscription with an empty type."""
    out_dir.mkdir()
    bad_spec = "/bench/cloud|sensor_msgs/msg/PointCloud2"  # missing "|kind"
    script = (
        f'{_SOURCE_ENV}; "{_BIN}/bench_observer" --ros-args '
        f'-p out_dir:=/out -p "topics:=[{bad_spec}]"'
    )
    result = _docker_run(f"{out_dir}:/out", script, timeout=30)
    assert result.returncode != 0
    assert "malformed topic spec" in result.stderr
    assert bad_spec in result.stderr
