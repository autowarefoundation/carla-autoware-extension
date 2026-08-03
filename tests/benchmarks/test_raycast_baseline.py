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

The clock.csv writer gets real-file tests for the same reason, and they model
the observer's ACTUAL behaviour rather than a convenient version of it (see
`RealBenchObserverClockFile`). The ablation arm has no `/clock` publisher, so
this writer is the sole producer of the series `finalize_rtf.py` needs -- and
it shares the file with a `bench_observer` that truncates it at run.sh step 6,
after the launcher started this client at step 5, and whose header is BUFFERED
until teardown. A first version of these tests modelled that as `open(path,
"w")` + write + close, which flushes immediately; against the real thing the
file is headerless for the whole run, the watchdog KeyErrors on every row, and
every ablation run is excluded `stall:clock`. Both consumers -- `read_clock_csv`
and `clock_watchdog.newest_arrival_ns` -- are therefore asserted, and both
answers to "does /clock flow?" are covered: self-heal when this client is the
only writer, stand down when it is not.
"""

from __future__ import annotations

import builtins
import csv
import importlib
import json
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest
import yaml

from benchmarks.analysis.bench_io import read_clock_csv
from benchmarks.scripts import clock_watchdog, raycast_baseline
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
    rig = raycast_baseline.extension_rig_attributes(
        **{"channels": 32, "points_per_second": 1200000}
    )

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


class RealBenchObserverClockFile:
    """The clock.csv half of `bench_observer`, modelled on what the COMMITTED
    node actually does -- verified live, not inferred from its source:

      * `open_or_throw` calls `f.open(path)` in default mode, i.e. O_TRUNC, in
        the CONSTRUCTOR (run.sh step 6, after the launcher started the ablation
        client at step 5);
      * the header is written to a BUFFERED ofstream and is NOT flushed there.
        Only the /clock callback (per row) and the destructor flush;
      * so with nothing publishing /clock the file stays 0 bytes for the whole
        run and gains its 27 bytes at teardown, at the stream's own offset 0.

    Measured 2026-08-03 against the real `bench-observer:universe-devel`
    container: a clock.csv holding a header and two rows became 0 bytes the
    moment the container started, stayed 0 for as long as it ran, and was
    exactly 27 bytes -- header only -- after `docker kill -s INT`. An earlier
    version of this test used `open(path, "w")` + write + close, which flushes
    the header immediately: the one behaviour the real observer does NOT have,
    which is why its passing said nothing about the live path.
    """

    HEADER = b"clock_ns,arrival_system_ns\n"

    def __init__(self, path):
        self.path = Path(path)
        self._fd = None
        self._offset = 0

    def construct(self):
        """run.sh step 6: truncate now, buffer the header."""
        self._fd = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o644)
        os.ftruncate(self._fd, 0)

    def clock_callback(self, clock_ns, arrival_ns):
        """A /clock message: header (first time) + row, flushed, at the
        observer's OWN sequential offset -- not at the file's end."""
        payload = b""
        if self._offset == 0:
            payload += self.HEADER
        payload += f"{clock_ns},{arrival_ns}\n".encode()
        os.pwrite(self._fd, payload, self._offset)
        self._offset += len(payload)

    def destructor(self):
        """teardown SIGINT: flush what is still buffered, at offset 0."""
        if self._offset == 0:
            os.pwrite(self._fd, self.HEADER, 0)
            self._offset = len(self.HEADER)
        os.close(self._fd)
        self._fd = None


def test_clock_header_is_byte_identical_to_the_observers_own():
    """A LITERAL PIN, and only that -- there is no behaviour here beyond the
    two literals agreeing. It is load-bearing anyway: the self-healing
    re-assert below is safe precisely because the observer's buffered header,
    flushed at offset 0 at teardown, overwrites our re-asserted one with the
    SAME bytes. If the two ever diverge, that write corrupts the first row."""
    cpp = (REPO_ROOT / "benchmarks" / "observer" / "src" / "bench_observer.cpp").read_text()
    assert 'clock_csv_ << "clock_ns,arrival_system_ns\\n"' in cpp
    assert raycast_baseline.CLOCK_HEADER == "clock_ns,arrival_system_ns\n"


def test_client_survives_the_real_observer_truncation_and_teardown_flush(tmp_path):
    """The live sequence end to end against the observer's REAL behaviour:
    client rows (step 5) -> observer truncates (step 6) -> client keeps
    writing -> observer's destructor flush (teardown).

    Both consumers are asserted, because they fail differently and at
    different times: the WATCHDOG polls during the run and excludes it
    `stall:clock` when it cannot parse a row, while `read_clock_csv` is what
    finalize_rtf and sweep_verdict go through afterwards.
    """
    path = tmp_path / "clock.csv"
    observer = RealBenchObserverClockFile(path)
    with raycast_baseline.ClockCsvWriter(path) as writer:
        writer.write(1_000_000_000, 1_700_000_000_000_000_000)
        observer.construct()  # run.sh step 6
        assert path.stat().st_size == 0, "the model must really truncate"

        writer.write(1_050_000_000, 1_700_000_000_050_000_000)
        writer.write(1_100_000_000, 1_700_000_000_100_000_000)
        # MID-RUN, which is when the watchdog looks. A headerless file makes
        # csv.DictReader treat the first data row as the field NAMES and
        # KeyError on every row -> "no /clock rows at all" -> stall:clock.
        assert clock_watchdog.newest_arrival_ns(path) == 1_700_000_000_100_000_000
        assert writer.header_reasserts == 1
        assert not writer.stood_down

        writer.write(1_150_000_000, 1_700_000_000_150_000_000)

    observer.destructor()  # teardown SIGINT: 27 identical bytes at offset 0

    clock_ns, arrival_ns = read_clock_csv(path)
    assert list(clock_ns) == [1_050_000_000, 1_100_000_000, 1_150_000_000]
    assert arrival_ns[-1] == 1_700_000_000_150_000_000
    assert clock_watchdog.newest_arrival_ns(path) == 1_700_000_000_150_000_000
    with open(path, newline="") as f:
        assert list(csv.reader(f))[0] == ["clock_ns", "arrival_system_ns"]


def test_client_stands_down_when_the_observer_is_also_writing(tmp_path):
    """The other answer to the /clock question: if anything IS publishing
    /clock the observer is an active, per-row-flushed writer to this file, and
    two byte streams cannot share it. The client must yield -- the observer's
    series is the authoritative one in that case anyway -- not interleave."""
    path = tmp_path / "clock.csv"
    observer = RealBenchObserverClockFile(path)
    with raycast_baseline.ClockCsvWriter(path) as writer:
        writer.write(1_000_000_000, 1_700_000_000_000_000_000)
        observer.construct()
        writer.write(1_050_000_000, 1_700_000_000_050_000_000)
        assert not writer.stood_down

        # /clock starts flowing: the observer flushes a header and rows of its
        # own, extending the file past anything this client wrote.
        for i in range(5):
            observer.clock_callback(2_000_000_000 + i * 50_000_000, 1_800_000_000_000_000_000 + i)

        writer.write(1_100_000_000, 1_700_000_000_100_000_000)
        assert writer.stood_down
        assert "bytes" in writer.stand_down_reason
        rows_at_stand_down = writer.rows
        writer.write(1_150_000_000, 1_700_000_000_150_000_000)
        assert writer.rows == rows_at_stand_down  # permanent, not per-call

    observer.destructor()
    # The observer's own series is intact and is what the run gets scored from.
    clock_ns, _ = read_clock_csv(path)
    assert list(clock_ns)[:5] == [2_000_000_000 + i * 50_000_000 for i in range(5)]


def test_tier4_sensor_tick_matches_the_launchers_rotation_hz():
    """I4: cell B's scan period is doubly-sourced. cells/tier4_autoware.sh
    passes `--lidar-rotation-hz $TIER4_LIDAR_ROTATION_HZ` to the patched demo,
    which turns it into `sensor_tick = 1/HZ` -- and this module transcribes the
    resulting literal. sensor_tick IS the ray budget per second, i.e. the
    quantity being measured, so the two agreeing by coincidence is not good
    enough: this reads the launcher's real value and derives the period."""
    text = (REPO_ROOT / "benchmarks" / "cells" / "tier4_autoware.sh").read_text()
    m = re.search(r"^TIER4_LIDAR_ROTATION_HZ=([0-9.]+)$", text, re.M)
    assert m, "TIER4_LIDAR_ROTATION_HZ not found in cells/tier4_autoware.sh"
    assert re.search(r"--lidar-rotation-hz\s+\"?\$TIER4_LIDAR_ROTATION_HZ", text), (
        "TIER4_LIDAR_ROTATION_HZ is no longer what reaches the demo's "
        "--lidar-rotation-hz; the derivation below is then wrong"
    )

    # patch 0003: `blueprint.set_attribute("sensor_tick", str(1.0 / args.lidar_rotation_hz))`
    assert raycast_baseline.tier4_rig_attributes()["sensor_tick"] == str(1.0 / float(m.group(1)))


@pytest.mark.parametrize("cell", ["A", "B", "B-cyc"])
def test_the_ablation_client_is_sampled_by_a_process_map_label(cell):
    """I3: without an entry matching the client, resources.csv records the
    ablation arm's ONLY process as nothing at all -- and `sample_pattern_entry`
    reports a zero row for an unmatched pattern rather than failing, so it
    reads as "this process used no CPU". The raycast cost the arm exists to
    measure would be unrecoverable after the run.

    The pattern is checked against the command line the launcher really
    produces (`env` execs in place, so the module path survives on the
    process's own cmdline), not merely for existence.

    `B-cyc` JOINED THIS PARAMETRIZATION 2026-08-03 (P4 whole-branch review,
    blocker B1) and the reason is worth keeping: it is the cell the P4 sweep
    actually sweeps, and it was the one cell this guard did not cover. Cells A
    and B were fixed by Task 7's I3 round, ordered "before any GPU-hours";
    B-cyc was registered in a different lane, in ignorance of that round, and
    so shipped with exactly the defect the round existed to remove. Its
    launcher IS cell B's (`approach: tier4-native`), so the command line is the
    same one -- only the process-map entry was missing."""
    doc = yaml.safe_load(
        (REPO_ROOT / "benchmarks" / "config" / "processes" / f"{cell}.yaml").read_text()
    )
    patterns = [e["pattern"] for e in doc["processes"] if "pattern" in e]
    launcher = {"A": "extension.sh", "B": "tier4-native.sh", "B-cyc": "tier4-native.sh"}[cell]
    cmdline = (REPO_ROOT / "benchmarks" / "cells" / launcher).read_text()
    assert "-m benchmarks.scripts.raycast_baseline" in cmdline
    assert any(
        p in "python3 -m benchmarks.scripts.raycast_baseline --host localhost" for p in patterns
    ), f"processes/{cell}.yaml has no entry matching the ablation client's cmdline: {patterns}"


def test_bcyc_process_map_body_stays_byte_identical_to_cell_bs():
    """B2: `processes/B-cyc.yaml`'s header CLAIMS the file is a byte-for-byte
    copy of `processes/B.yaml` below the header, and that claim silently became
    FALSE at merge time -- one lane copied B.yaml, another added the
    `raycast-baseline` entry to B.yaml, both merged textually clean, and
    nothing anywhere compared them again. The consequence was the defect the
    test above exists to catch.

    So the header's claim gets a machine check rather than a promise. Compared
    from `processes:` down, because the headers deliberately differ (B-cyc's
    records the transport derivation and this history); everything below is the
    copy the claim is about."""

    def body(name):
        text = (REPO_ROOT / "benchmarks" / "config" / "processes" / name).read_text()
        marker = "\nprocesses:\n"
        assert marker in text, f"processes/{name} has no `processes:` block"
        return text[text.index(marker) :]

    assert body("B-cyc.yaml") == body("B.yaml"), (
        "processes/B-cyc.yaml's body has drifted from processes/B.yaml's. Its "
        "own header states the byte-for-byte copy as a standing obligation: "
        "mirror the B.yaml edit here in the same commit, or amend that header."
    )


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
            "--rig",
            "extension",
            "--class-id",
            "vlp16",
            "--lidar-channels",
            "16",
            "--lidar-pps",
            "288000",
            "--tick-hz",
            "20.0",
            "--duration-s",
            "0.3",
            "--out-dir",
            str(tmp_path),
            "--initial-pose",
            "1",
            "2",
            "3",
            "0",
            "0",
            "90",
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
            "--rig",
            "tier4",
            "--tick-hz",
            "20.0",
            "--duration-s",
            "0.2",
            "--out-dir",
            str(tmp_path),
            "--initial-pose",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
        ]
    )

    assert not (tmp_path / "publisher_counts.json").exists()
    assert not (tmp_path / "quality.json").exists()
    assert (tmp_path / "clock.csv").exists()


def test_non_positive_tick_hz_is_refused_by_name():
    """M3: --tick-hz is inverted into fixed_delta_seconds, so 0 is a
    ZeroDivisionError and a negative is a negative delta -- both after the
    CARLA connect, on a booted cell. Unreachable through the launchers (both
    read the value from the registry, which refuses a null) but reachable by
    hand, and this file's whole style is to refuse by name at the top."""
    for bad in ("0", "-20.0"):
        with pytest.raises(SystemExit) as exc:
            raycast_baseline.main(
                ["--rig", "extension", "--tick-hz", bad, "--out-dir", "/tmp/does-not-matter"]
            )
        assert exc.value.code == 2
