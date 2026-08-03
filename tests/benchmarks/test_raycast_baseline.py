"""TDD tests for benchmarks/scripts/raycast_baseline.py -- the M4 sweep's
ABLATION arm: the identical LiDAR rig with publishing disabled, so that
`transport cost = total - baseline`.

Three properties are load-bearing enough to pin here, and each is pinned by
RUNNING the real thing rather than by scanning the file for a literal:

  * the extension (cell A) rig is DERIVED from `runner.spawn`'s own attribute
    builder, not copied -- so a change to the committed rig follows into the
    baseline automatically -- with the sweep class's two keys overridden and
    every `ros*` attribute removed (publishing disabled IS the arm);
  * the tier4-native (cell B) rig is the patch-0003 default dict, whose
    literals are the ones benchmarks/patches/tier4-native/README.md certifies
    the patch reproduces, with the same two keys overridden and, again, no
    `ros*` attributes;
  * the module imports and answers `--help` with NO CARLA present. The test
    does not assert that by reading the source for an indented `import carla`:
    it BLOCKS the module on sys.meta_path and then reloads and runs it, which
    fails if the import ever moves back to module scope or to the top of
    `main()` (before argument parsing).

The clock.csv writer gets a real-file test for the same reason: the ablation
arm has no `/clock` publisher, so this writer is the sole producer of the
series `finalize_rtf.py` needs, and it shares the file with a `bench_observer`
that TRUNCATES it at run.sh step 6 (after the launcher started this client at
step 5). Simulating that truncation with real files is the only way to know
the append design survives it.
"""

from __future__ import annotations

import builtins
import csv
import importlib
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from benchmarks.analysis.bench_io import read_clock_csv
from benchmarks.scripts import raycast_baseline
from runner.spawn import top_lidar_attributes

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "benchmarks" / "scripts" / "raycast_baseline.py"

# cells.yaml `sweep_classes`: vlp16 = 16 channels / 288000 pps, 32ch = 32 /
# 1200000. The two launchers' Task-6 mapping emits exactly these, as
# `--lidar-channels N --lidar-pps N`.
VLP16 = {"channels": 16, "points_per_second": 288000}
CH32 = {"channels": 32, "points_per_second": 1200000}


def _no_ros_keys(attrs: dict[str, str]) -> dict[str, str]:
    return {k: v for k, v in attrs.items() if not k.startswith("ros")}


# --- the A-rig builder: derived from runner.spawn, ros-free, class-overridden ---


def test_extension_rig_is_runner_spawns_dict_minus_ros_attrs():
    """No overrides: the committed rig itself, with only the native-ROS2
    publisher attributes removed. Compared against the LIVE
    `top_lidar_attributes()` rather than a transcribed literal, so the
    baseline cannot silently drift from the rig it is the baseline for."""
    rig = raycast_baseline.extension_rig_attributes()

    assert rig == _no_ros_keys(top_lidar_attributes())
    assert rig["channels"] == "128"  # the committed VLS-128 default
    assert rig["points_per_second"] == "600000"
    assert rig["rotation_frequency"] == "10"
    assert rig["sensor_tick"] == "0.05"


def test_extension_rig_applies_the_sweep_class_overrides():
    rig = raycast_baseline.extension_rig_attributes(
        channels=VLP16["channels"], points_per_second=VLP16["points_per_second"]
    )

    expected = _no_ros_keys(
        top_lidar_attributes(overrides={"channels": "16", "points_per_second": "288000"})
    )
    assert rig == expected
    # Only the two keys a sweep class pins move; the rest of the rig is the
    # committed one (cells.yaml sweep_classes registers channels +
    # points_per_second only).
    assert rig["rotation_frequency"] == top_lidar_attributes()["rotation_frequency"]
    assert rig["range"] == top_lidar_attributes()["range"]


def test_extension_rig_carries_no_ros_attributes_at_all():
    """Publishing disabled is the arm's definition: no ros_topic_name, no
    ros2_extended_lidar, no ros_name, no ros2_qos_*."""
    rig = raycast_baseline.extension_rig_attributes(**{"channels": 32, "points_per_second": 1200000})

    assert [k for k in rig if k.startswith("ros")] == []
    assert "ros_topic_name" in top_lidar_attributes()  # the source DOES have them


# --- the B-rig builder: the patch-0003 literals ---


def test_tier4_rig_is_the_patch_0003_default_dict_minus_ros_attrs():
    """The literals benchmarks/patches/tier4-native/README.md certifies
    0003-autoware-demo-params.patch reproduces exactly (its recorded
    original-vs-patched attribute dump), minus the two ros_* keys."""
    rig = raycast_baseline.tier4_rig_attributes()

    assert rig == {
        "channels": "16",
        "range": "100.0",
        "upper_fov": "10.0",
        "lower_fov": "-20.0",
        "points_per_second": "288000",
        "sensor_tick": "0.1",
    }


def test_tier4_rig_applies_the_sweep_class_overrides():
    rig = raycast_baseline.tier4_rig_attributes(
        channels=CH32["channels"], points_per_second=CH32["points_per_second"]
    )

    assert rig["channels"] == "32"
    assert rig["points_per_second"] == "1200000"
    # sensor_tick is the demo's publish period (--lidar-rotation-hz -> 1/HZ),
    # NOT rotation_frequency, and a class never touches it.
    assert rig["sensor_tick"] == "0.1"
    assert rig["range"] == "100.0"
    assert [k for k in rig if k.startswith("ros")] == []


def test_rig_attributes_dispatches_and_refuses_an_unknown_rig():
    assert raycast_baseline.rig_attributes("extension") == (
        raycast_baseline.extension_rig_attributes()
    )
    assert raycast_baseline.rig_attributes("tier4") == raycast_baseline.tier4_rig_attributes()
    with pytest.raises(ValueError, match="nope"):
        raycast_baseline.rig_attributes("nope")


# --- offline: no CARLA at import time, and --help exits 0 ---


class _BlockCarla:
    """sys.meta_path finder that makes `import carla` raise, so a module that
    imports it at module scope (or before argument parsing) fails loudly here
    instead of on a machine that happens to have the wheel installed."""

    def find_module(self, fullname, path=None):  # pragma: no cover - py2-era hook
        return None

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "carla" or fullname.startswith("carla."):
            raise ImportError("no CARLA egg on this machine (blocked by the test)")
        return None


@pytest.fixture
def carla_blocked(monkeypatch):
    monkeypatch.delitem(sys.modules, "carla", raising=False)
    finder = _BlockCarla()
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    real_import = builtins.__import__

    def _guarded(name, *args, **kwargs):
        if name == "carla" or name.startswith("carla."):
            raise ImportError("no CARLA egg on this machine (blocked by the test)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guarded)
    yield


def test_module_reimports_cleanly_with_carla_blocked(carla_blocked):
    """RELOADED under the block, not merely imported: this host DOES have a
    (stale) carla wheel in ~/.local, so a module-scope `import carla` would
    otherwise sail through collection and the pin would be vacuous."""
    with pytest.raises(ImportError):
        importlib.import_module("carla")
    importlib.reload(raycast_baseline)


def test_help_exits_zero_with_carla_blocked(carla_blocked, capsys):
    """--help must reach argparse before anything touches CARLA. Reloaded
    first, for the reason above, so this covers a module-scope import as well
    as one at the top of main()."""
    module = importlib.reload(raycast_baseline)

    with pytest.raises(SystemExit) as exc:
        module.main(["--help"])

    assert exc.value.code == 0
    assert "--rig" in capsys.readouterr().out


def test_help_exits_zero_as_a_script_with_no_carla_importable():
    """The invocation the launchers and the operator actually use, in a child
    with PYTHONNOUSERSITE=1 -- which is what makes it a genuinely OFFLINE run
    on this host (the stale wheel lives in the user site directory, and
    `python3 -c "import carla"` under that env really does fail)."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        env={
            "PYTHONPATH": str(REPO_ROOT),
            "PATH": "/usr/bin:/bin",
            "HOME": str(Path.home()),
            "PYTHONNOUSERSITE": "1",
        },
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    assert "--out-dir" in proc.stdout


# --- the clock.csv writer: the ablation arm's only /clock substitute ---


def test_clock_writer_writes_a_header_then_rows_readable_by_the_real_reader(tmp_path):
    path = tmp_path / "clock.csv"
    with raycast_baseline.ClockCsvWriter(path) as writer:
        writer.write(1_000_000_000, 1_700_000_000_000_000_000)
        writer.write(1_050_000_000, 1_700_000_000_050_000_000)

    clock_ns, arrival_ns = read_clock_csv(path)
    assert list(clock_ns) == [1_000_000_000, 1_050_000_000]
    assert list(arrival_ns) == [1_700_000_000_000_000_000, 1_700_000_000_050_000_000]


def test_clock_writer_survives_the_observers_truncation(tmp_path):
    """bench_observer opens clock.csv with std::ofstream (O_TRUNC) in its
    constructor at run.sh step 6 -- AFTER the launcher started this client at
    step 5. Appending means the rows that follow that truncation land after
    the observer's identical header, so the file stays a valid CSV that
    `read_clock_csv` parses; only the pre-step-6 bring-up rows are lost."""
    path = tmp_path / "clock.csv"
    with raycast_baseline.ClockCsvWriter(path) as writer:
        writer.write(1_000_000_000, 1_700_000_000_000_000_000)
        # The observer, mid-run: truncate and write its own header.
        with open(path, "w", newline="") as observer:
            observer.write("clock_ns,arrival_system_ns\n")
        writer.write(1_050_000_000, 1_700_000_000_050_000_000)
        writer.write(1_100_000_000, 1_700_000_000_100_000_000)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["clock_ns", "arrival_system_ns"]
    assert len(rows) == 3  # header + the two post-truncation rows

    clock_ns, _ = read_clock_csv(path)
    assert list(clock_ns) == [1_050_000_000, 1_100_000_000]


def test_clock_writer_does_not_duplicate_a_header_that_already_exists(tmp_path):
    """The observer may win the race and create the file first."""
    path = tmp_path / "clock.csv"
    path.write_text("clock_ns,arrival_system_ns\n")

    with raycast_baseline.ClockCsvWriter(path) as writer:
        writer.write(1_000_000_000, 1_700_000_000_000_000_000)

    with open(path, newline="") as f:
        rows = list(csv.reader(f))
    assert rows == [["clock_ns", "arrival_system_ns"], ["1000000000", "1700000000000000000"]]


# --- main(), end to end, against a fake CARLA ------------------------------
#
# No CARLA server is available to this task (live collection is a later,
# strictly serial stage), so the live path is bounded HERE instead of left
# unverified: a structural fake stands in for the client/world/blueprints and
# main() runs for real against it -- the same trick runner/loop.py's own
# docstring names ("takes a `world` object structurally ... so they are
# unit-testable with a fake world too"). What this does NOT show is that the
# real server accepts these attribute names or that the rig raycasts at the
# rate asked for; that needs the live stage.


class _FakeBlueprint:
    def __init__(self, bp_id):
        self.id = bp_id
        self.attributes = {}

    def has_attribute(self, key):
        return True

    def set_attribute(self, key, value):
        self.attributes[key] = value


class _FakeActor:
    def __init__(self, blueprint, transform, attach_to=None):
        self.blueprint = blueprint
        self.transform = transform
        self.attach_to = attach_to
        self.listener = None
        self.stopped = False
        self.destroyed = False

    def listen(self, callback):
        self.listener = callback

    def stop(self):
        self.stopped = True

    def destroy(self):
        self.destroyed = True


class _FakeSettings:
    def __init__(self):
        self.synchronous_mode = False
        self.fixed_delta_seconds = None


class _FakeTimestamp:
    def __init__(self, elapsed_seconds):
        self.elapsed_seconds = elapsed_seconds


class _FakeSnapshot:
    def __init__(self, elapsed_seconds):
        self.timestamp = _FakeTimestamp(elapsed_seconds)


class _FakeWorld:
    def __init__(self):
        self.settings = _FakeSettings()
        self.applied = []
        self.actors = []
        self.ticks = 0
        self.elapsed = 100.0

    def get_settings(self):
        return self.settings

    def apply_settings(self, settings):
        self.applied.append((settings.synchronous_mode, settings.fixed_delta_seconds))

    def tick(self):
        self.ticks += 1
        self.elapsed += self.settings.fixed_delta_seconds or 0.05
        for actor in self.actors:
            if actor.listener is not None:
                actor.listener(object())

    def get_snapshot(self):
        return _FakeSnapshot(self.elapsed)

    def get_map(self):
        raise AssertionError("--initial-pose was given; the map must not be consulted")

    def get_blueprint_library(self):
        return self

    def find(self, bp_id):
        return _FakeBlueprint(bp_id)

    def spawn_actor(self, blueprint, transform, attach_to=None):
        actor = _FakeActor(blueprint, transform, attach_to)
        self.actors.append(actor)
        return actor


@pytest.fixture
def fake_carla(monkeypatch):
    world = _FakeWorld()
    module = types.ModuleType("carla")

    class _Client:
        def __init__(self, host, port):
            self.host, self.port = host, port

        def set_timeout(self, seconds):
            self.timeout = seconds

        def get_world(self):
            return world

    module.Client = _Client
    module.Location = lambda x, y, z: ("loc", x, y, z)
    module.Rotation = lambda roll, pitch, yaw: ("rot", roll, pitch, yaw)
    module.Transform = lambda location, rotation: ("xf", location, rotation)
    monkeypatch.setitem(sys.modules, "carla", module)
    return world


def test_main_runs_the_publish_disabled_rig_and_files_the_contract(tmp_path, fake_carla):
    rc = raycast_baseline.main(
        [
            "--rig", "extension",
            "--class-id", "vlp16",
            "--lidar-channels", "16",
            "--lidar-pps", "288000",
            "--tick-hz", "20.0",
            "--duration-s", "0.3",
            "--out-dir", str(tmp_path),
            "--initial-pose", "1", "2", "3", "0", "0", "90",
        ]
    )

    assert rc == 0
    ego, lidar = fake_carla.actors
    # The rig actually applied to the blueprint is the ros-free, class-driven
    # one -- checked on the blueprint, not on the builder's return value.
    assert lidar.blueprint.attributes == raycast_baseline.extension_rig_attributes(16, 288000)
    assert [k for k in lidar.blueprint.attributes if k.startswith("ros")] == []
    assert lidar.attach_to is ego
    assert lidar.listener is not None  # the stream subscription IS the raycast trigger
    assert lidar.stopped and lidar.destroyed and ego.destroyed
    # Sync at the registered tick, and the world's prior settings restored.
    assert fake_carla.applied[0] == (True, 0.05)
    assert fake_carla.applied[-1] == (False, None)

    clock_ns, arrival_ns = read_clock_csv(tmp_path / "clock.csv")
    assert clock_ns.size == fake_carla.ticks >= 2
    assert list(clock_ns) == sorted(clock_ns)
    assert list(arrival_ns) == sorted(arrival_ns)

    summary = json.loads((tmp_path / "raycast_baseline.json").read_text())
    assert summary["ticks"] == fake_carla.ticks
    assert summary["sensor_callbacks"] == fake_carla.ticks
    assert summary["class_id"] == "vlp16"
    assert summary["tick_hz"] == 20.0
    assert summary["attributes"]["channels"] == "16"


def test_main_writes_neither_publisher_counts_nor_quality_json(tmp_path, fake_carla):
    """The two files the ablation contract requires to be ABSENT: an absent
    publisher_counts.json reads as "not measurable" while a file-backed 0
    would FIRE the ceiling's publisher disjunct, and an absent quality.json is
    what makes sweep_verdict default quality_ok=True on this arm alone."""
    raycast_baseline.main(
        [
            "--rig", "tier4",
            "--tick-hz", "20.0",
            "--duration-s", "0.2",
            "--out-dir", str(tmp_path),
            "--initial-pose", "0", "0", "0", "0", "0", "0",
        ]
    )

    assert not (tmp_path / "publisher_counts.json").exists()
    assert not (tmp_path / "quality.json").exists()
    assert (tmp_path / "clock.csv").exists()
