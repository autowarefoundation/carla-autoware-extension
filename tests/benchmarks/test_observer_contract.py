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

from benchmarks.analysis.bench_io import read_clock_csv, read_observer_csv
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
    _assert_unwritable_out_dir_fails_loudly(tmp_path / "ro_out")
    _assert_malformed_spec_fails_loudly(tmp_path / "malformed_spec_out")


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
