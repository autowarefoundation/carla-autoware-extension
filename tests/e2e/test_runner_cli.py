"""Unit tests for the runner CLI/loop layer (``runner.loop`` / ``runner.__main__``).

Pure-Python only where possible: ``runner.loop`` never imports ``carla`` at module level, so
these tests collect and run under a bare ``python3 -m pytest`` with no CARLA egg, which is
how CI runs it (see ``tests/e2e/test_runner_kit.py`` for the same rule on the spawn side).
The tick-loop tests use a minimal fake ``world`` object (get_settings/apply_settings/tick/
wait_for_tick) rather than a real CARLA connection; the live E2E run is covered by the gate
scripts under ``scripts/e2e/`` and recorded in ``docs/e2e-report.md``.
"""

from __future__ import annotations

import os

import pytest

from runner.__main__ import build_arg_parser, build_lidar_overrides, select_spawn_point
from runner.__main__ import main as runner_main
from runner.loop import (
    apply_substep_config,
    extension_exports_init,
    load_physics_config,
    run_async_loop,
    run_sync_loop,
)
from runner.spawn import camera_attributes

# --- --extension-check: negative path (mandatory) ---


def test_extension_check_detects_missing_symbol(tmp_path):
    # A non-.so file has no exported init symbol.
    fake = tmp_path / "not_a_lib.so"
    fake.write_bytes(b"\x7fELF\x00")
    assert extension_exports_init(str(fake)) is False


def test_extension_check_detects_nonexistent_path(tmp_path):
    # nm fails outright on a path that does not exist -- must return False, not raise.
    missing = tmp_path / "does" / "not" / "exist.so"
    assert extension_exports_init(str(missing)) is False


# --- --extension-check: positive path against the REAL built extension .so ---
#
# The extension is built at extension/build/libcarla-autoware-extension.so on this dev
# machine (the extension's C++ build) but is NOT built in CI, so this test is gated on the
# artifact's presence -- same env/data-gated-skip precedent as the NuRec test suite
# (X2_PARAMS / N2_RUN_STORE-gated tests), applied here to a build artifact instead of a
# captured-data fixture.
_REAL_EXTENSION_SO = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "extension",
        "build",
        "libcarla-autoware-extension.so",
    )
)


@pytest.mark.skipif(
    not os.path.exists(_REAL_EXTENSION_SO),
    reason=f"extension not built on this machine ({_REAL_EXTENSION_SO} missing)",
)
def test_extension_check_detects_real_built_extension():
    assert extension_exports_init(_REAL_EXTENSION_SO) is True


# --- runner.__main__.main(): CLI wiring for --extension-check and the kit-yaml preflight.
#
# All of these return before `import carla` (see runner/__main__.py), so they run under bare
# pytest with no CARLA egg installed. main() takes an optional argv so it is callable directly,
# the same pattern stdlib/argparse CLIs use for testability.


def test_main_extension_check_ok_on_real_so(capsys):
    if not os.path.exists(_REAL_EXTENSION_SO):
        pytest.skip(f"extension not built on this machine ({_REAL_EXTENSION_SO} missing)")
    rc = runner_main(["--extension-check", "--extension-so", _REAL_EXTENSION_SO])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_main_extension_check_fails_loudly_on_missing_so(capsys, tmp_path):
    missing = tmp_path / "nope.so"
    rc = runner_main(["--extension-check", "--extension-so", str(missing)])
    assert rc == 1
    assert "PREFLIGHT FAIL" in capsys.readouterr().err


def test_main_extension_check_fails_loudly_when_extension_so_omitted(capsys):
    rc = runner_main(["--extension-check"])
    assert rc == 1
    assert "PREFLIGHT FAIL" in capsys.readouterr().err


def test_main_fails_loudly_on_missing_sensor_kit_calibration(capsys, tmp_path):
    missing = tmp_path / "no_such_sensor_kit_calibration.yaml"
    rc = runner_main(["--sensor-kit-calibration", str(missing)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "--sensor-kit-calibration" in err
    assert str(missing) in err


def test_main_fails_loudly_on_missing_sensors_calibration(capsys, tmp_path):
    missing = tmp_path / "no_such_sensors_calibration.yaml"
    rc = runner_main(["--sensors-calibration", str(missing)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "--sensors-calibration" in err
    assert str(missing) in err


# --- --spawn-index: map-independent selection of a recommended spawn point ---


def test_spawn_index_defaults_to_zero():
    # The historical behaviour was spawn point 0; the new flag must not move it.
    assert build_arg_parser().parse_args([]).spawn_index == 0


def test_spawn_index_parses_as_an_int():
    assert build_arg_parser().parse_args(["--spawn-index", "42"]).spawn_index == 42


def test_select_spawn_point_returns_the_requested_entry():
    assert select_spawn_point(["a", "b", "c"], 1) == "b"


@pytest.mark.parametrize("index", [3, 99])
def test_select_spawn_point_rejects_an_index_past_the_end(index):
    with pytest.raises(IndexError, match="out of range; the map has 3 spawn points"):
        select_spawn_point(["a", "b", "c"], index)


def test_select_spawn_point_rejects_a_negative_index():
    # A negative index would silently WRAP to a different spawn point rather
    # than fail, which is exactly the kind of quiet mis-start this guards.
    with pytest.raises(IndexError, match="out of range"):
        select_spawn_point(["a", "b", "c"], -1)


def test_select_spawn_point_rejects_any_index_on_a_map_with_no_spawn_points():
    with pytest.raises(IndexError, match="the map has 0 spawn points"):
        select_spawn_point([], 0)


# --- M4 knobs: sweep-class, camera, pacing, substepping CLI flags ---
#
# Regression pins first: every new flag must default to "no override" / today's exact
# runner behaviour when omitted, so the existing Nishi/Town10 gates stay green.


def test_lidar_override_flags_default_to_none():
    args = build_arg_parser().parse_args([])
    assert args.lidar_channels is None
    assert args.lidar_pps is None
    assert args.lidar_rotation_hz is None
    assert args.lidar_range is None


def test_lidar_override_flags_parse():
    args = build_arg_parser().parse_args(
        [
            "--lidar-channels",
            "16",
            "--lidar-pps",
            "288000",
            "--lidar-rotation-hz",
            "10",
            "--lidar-range",
            "100",
        ]
    )
    assert args.lidar_channels == 16
    assert args.lidar_pps == 288000
    assert args.lidar_rotation_hz == 10.0
    assert args.lidar_range == 100.0


# --- build_lidar_overrides: the flag-name -> attribute-key seam ---
#
# CLI parsing (above) and top_lidar_attributes(overrides=...)'s merge behaviour (in
# test_runner_kit.py) are both covered elsewhere; this is the mapping BETWEEN them
# (args.lidar_channels -> "channels", args.lidar_pps -> "points_per_second", ... + the
# str() conversion) -- exercised directly so a silent key-name typo or a missing str()
# cannot flow straight into the P4 sweep-class results uncaught.


def test_build_lidar_overrides_empty_when_every_flag_omitted():
    # No key present at all (not a key with a None value) -- this is what makes
    # top_lidar_attributes(overrides=build_lidar_overrides(args)) a true no-op by default.
    args = build_arg_parser().parse_args([])
    assert build_lidar_overrides(args) == {}


def test_build_lidar_overrides_maps_every_flag_to_its_attribute_key_as_str():
    args = build_arg_parser().parse_args(
        [
            "--lidar-channels",
            "16",
            "--lidar-pps",
            "288000",
            "--lidar-rotation-hz",
            "10",
            "--lidar-range",
            "100",
        ]
    )
    overrides = build_lidar_overrides(args)
    assert overrides == {
        "channels": "16",
        "points_per_second": "288000",
        "rotation_frequency": "10.0",
        "range": "100.0",
    }
    assert all(isinstance(v, str) for v in overrides.values())


def test_build_lidar_overrides_partial_combination_yields_only_given_keys():
    # Only --lidar-channels/--lidar-range given -> only those two keys, nothing for the
    # two omitted flags (--lidar-pps/--lidar-rotation-hz).
    args = build_arg_parser().parse_args(["--lidar-channels", "32", "--lidar-range", "50"])
    assert build_lidar_overrides(args) == {"channels": "32", "range": "50.0"}


def test_build_lidar_overrides_single_flag_given():
    args = build_arg_parser().parse_args(["--lidar-pps", "4600000"])
    assert build_lidar_overrides(args) == {"points_per_second": "4600000"}


def test_cameras_defaults_to_zero_no_cameras():
    # Today's exact rig spawns no cameras at all -- the M4 camera arm is opt-in.
    args = build_arg_parser().parse_args([])
    assert args.cameras == 0
    assert args.camera_width == 1600
    assert args.camera_height == 900
    assert args.camera_tick == 0.05  # 1/20 fps, the tick ceiling


def test_fixed_delta_defaults_to_todays_0_05():
    assert build_arg_parser().parse_args([]).fixed_delta == 0.05


def test_unpaced_defaults_to_false():
    assert build_arg_parser().parse_args([]).unpaced is False


def test_unpaced_flag_sets_true():
    assert build_arg_parser().parse_args(["--unpaced"]).unpaced is True


def test_substep_config_defaults_to_none():
    assert build_arg_parser().parse_args([]).substep_config is None


def test_cameras_two_produces_two_camera_specs_with_indexed_topics():
    # The brief's Step 1 CLI test: --cameras 2 -> two camera specs, indexed ros_name/
    # ros_topic_name, sensor_tick from --camera-tick. Built the same way __main__.main()
    # builds them (camera_attributes per index, driven by the parsed CLI args), but
    # exercised here pure-Python -- no CARLA connection needed.
    args = build_arg_parser().parse_args(["--cameras", "2", "--camera-tick", "0.1"])
    specs = [
        camera_attributes(i, args.camera_width, args.camera_height, args.camera_tick)
        for i in range(args.cameras)
    ]
    assert len(specs) == 2
    assert specs[0]["ros_topic_name"] == specs[0]["ros_name"] == "/sensing/camera/camera0/image_raw"
    assert specs[1]["ros_topic_name"] == specs[1]["ros_name"] == "/sensing/camera/camera1/image_raw"
    assert specs[0]["sensor_tick"] == specs[1]["sensor_tick"] == "0.1"
    assert specs[0]["image_size_x"] == "1600"
    assert specs[0]["image_size_y"] == "900"


# --- physics.yaml substep-config loading + application ---


def test_load_physics_config_reads_both_keys(tmp_path):
    physics_yaml = tmp_path / "physics.yaml"
    physics_yaml.write_text("max_substep_delta_time: 0.01\nmax_substeps: 10\n")
    config = load_physics_config(str(physics_yaml))
    assert config == {"max_substep_delta_time": 0.01, "max_substeps": 10}


def test_load_physics_config_names_key_file_and_cause_when_null(tmp_path):
    # The committed benchmarks/config/physics.yaml ships with both keys null (Task 13
    # fills them in) -- pointing --substep-config at it as-is must fail loudly, naming the
    # missing key and the file, not a bare TypeError from float(None).
    physics_yaml = tmp_path / "physics.yaml"
    physics_yaml.write_text("max_substep_delta_time:\nmax_substeps: 10\n")
    with pytest.raises(ValueError) as exc:
        load_physics_config(str(physics_yaml))
    msg = str(exc.value)
    assert "max_substep_delta_time" in msg  # names the missing key
    assert str(physics_yaml) in msg  # names the file


def test_load_physics_config_names_key_file_and_cause_when_key_missing_entirely(tmp_path):
    physics_yaml = tmp_path / "physics.yaml"
    physics_yaml.write_text("max_substep_delta_time: 0.01\n")  # max_substeps absent
    with pytest.raises(ValueError, match="max_substeps"):
        load_physics_config(str(physics_yaml))


def test_load_physics_config_names_key_file_and_cause_when_malformed(tmp_path):
    physics_yaml = tmp_path / "physics.yaml"
    physics_yaml.write_text("max_substep_delta_time: not_a_number\nmax_substeps: 10\n")
    with pytest.raises(ValueError) as exc:
        load_physics_config(str(physics_yaml))
    msg = str(exc.value)
    assert "max_substep_delta_time" in msg
    assert "not_a_number" in msg
    assert str(physics_yaml) in msg


def test_apply_substep_config_sets_world_settings():
    world = _FakeWorld()
    apply_substep_config(world, {"max_substep_delta_time": 0.005, "max_substeps": 16})
    settings = world.get_settings()
    assert settings.max_substep_delta_time == 0.005
    assert settings.max_substeps == 16


# --- tick loop helpers: should_continue wiring against a fake world ---


class _FakeSettings:
    def __init__(self, synchronous_mode: bool = False):
        self.synchronous_mode = synchronous_mode
        self.fixed_delta_seconds = None


class _FakeWorld:
    """Minimal stand-in for a CARLA ``World`` exposing exactly the surface
    ``run_sync_loop``/``run_async_loop`` touch: get_settings/apply_settings/tick/
    wait_for_tick. No CARLA import anywhere in this fixture."""

    def __init__(self):
        self._settings = _FakeSettings(synchronous_mode=False)
        self.applied_settings: list[tuple[bool, float | None]] = []
        self.tick_count = 0
        self.wait_for_tick_count = 0

    def get_settings(self):
        return self._settings

    def apply_settings(self, settings):
        self.applied_settings.append((settings.synchronous_mode, settings.fixed_delta_seconds))
        self._settings = settings

    def tick(self):
        self.tick_count += 1

    def wait_for_tick(self):
        self.wait_for_tick_count += 1


def _stop_after(n):
    calls = {"count": 0}

    def should_continue():
        calls["count"] += 1
        return calls["count"] <= n

    return should_continue


def test_run_sync_loop_ticks_until_should_continue_false():
    world = _FakeWorld()
    on_tick_counts = []

    run_sync_loop(
        world,
        fixed_delta=0.0,  # no real-time sleep -- keep the test instant and deterministic
        on_tick=lambda: on_tick_counts.append(world.tick_count),
        should_continue=_stop_after(3),
    )

    assert world.tick_count == 3
    assert on_tick_counts == [1, 2, 3]


def test_run_sync_loop_enables_sync_mode_during_the_loop():
    world = _FakeWorld()
    seen_sync_mode_during_tick = []

    def on_tick():
        seen_sync_mode_during_tick.append(world.get_settings().synchronous_mode)

    run_sync_loop(world, fixed_delta=0.0, on_tick=on_tick, should_continue=_stop_after(2))

    assert seen_sync_mode_during_tick == [True, True]
    # First apply_settings call switches sync mode on with the requested fixed_delta_seconds.
    assert world.applied_settings[0] == (True, 0.0)


def test_run_sync_loop_restores_prior_sync_mode_on_exit():
    world = _FakeWorld()
    world._settings.synchronous_mode = False  # prior mode: async

    run_sync_loop(world, fixed_delta=0.0, should_continue=_stop_after(1))

    # finally must restore the FULL prior (synchronous_mode, fixed_delta_seconds) tuple, not
    # just sync mode -- asserting the whole tuple is what actually exercises the
    # fixed_delta_seconds restore (a prior client's fixed_delta_seconds must not be left at
    # this loop's own value after exit).
    assert world.get_settings().synchronous_mode is False
    assert world.applied_settings[-1] == (False, None)


def test_run_sync_loop_restores_prior_fixed_delta_seconds_when_set():
    # A distinct prior fixed_delta_seconds (as another client would already have configured)
    # must be restored VERBATIM, not left at this loop's OWN fixed_delta -- this is what
    # actually proves a real prior-value restore, since the sibling test's prior value (None)
    # would pass even by accident if the restore silently no-opped.
    world = _FakeWorld()
    world._settings.synchronous_mode = False
    world._settings.fixed_delta_seconds = 0.1  # prior client's setting, != this loop's 0.05

    run_sync_loop(world, fixed_delta=0.05, should_continue=_stop_after(1))

    assert world.get_settings().fixed_delta_seconds == 0.1
    assert world.applied_settings[-1] == (False, 0.1)


def test_run_sync_loop_restores_prior_sync_mode_even_on_exception():
    world = _FakeWorld()
    world._settings.fixed_delta_seconds = 0.2  # distinct prior value, proves a real restore

    def boom():
        raise RuntimeError("tick callback exploded")

    with pytest.raises(RuntimeError):
        run_sync_loop(world, fixed_delta=0.0, on_tick=boom, should_continue=_stop_after(1))

    # The finally block must still have restored the prior (sync_mode, fixed_delta) tuple.
    assert world.get_settings().synchronous_mode is False
    assert world.applied_settings[-1] == (False, 0.2)


def test_run_sync_loop_default_should_continue_runs_at_least_one_tick():
    # should_continue=None must default to "always continue", not "never run" -- verified by
    # tick()ing once and then raising to break out (an infinite-loop default would hang here).
    world = _FakeWorld()

    def on_tick():
        raise StopIteration  # deliberate escape hatch, not a real loop-control signal

    with pytest.raises(StopIteration):
        run_sync_loop(world, fixed_delta=0.0, on_tick=on_tick)
    assert world.tick_count == 1


def test_run_async_loop_waits_for_tick_until_should_continue_false():
    world = _FakeWorld()

    run_async_loop(world, fixed_delta=0.0, should_continue=_stop_after(4))

    assert world.wait_for_tick_count == 4
    assert world.tick_count == 0  # async mode never calls tick() -- the server ticks itself


def test_run_async_loop_sets_asynchronous_mode():
    world = _FakeWorld()
    world._settings.synchronous_mode = True  # start from sync mode

    run_async_loop(world, fixed_delta=0.0, should_continue=_stop_after(1))

    assert world.applied_settings[0][0] is False
    assert world.get_settings().synchronous_mode is False


# --- --unpaced: skip the real-time pacing sleep, tick as fast as possible ---
#
# ``paced`` defaults to True on both loops -- today's exact real-time-paced behaviour --
# so every EXISTING test above (which never passes ``paced``) is itself a regression pin.


def test_run_sync_loop_paced_by_default_sleeps_when_the_tick_ran_fast(monkeypatch):
    world = _FakeWorld()
    sleep_calls = []
    monkeypatch.setattr("runner.loop.time.sleep", lambda s: sleep_calls.append(s))
    # perf_counter() called twice per iteration (t0, then after tick+on_tick); a 0.0 delta
    # between them means the tick "ran instantly", well under fixed_delta -- the pacing sleep
    # must fire to hold the 20 Hz cadence.
    monkeypatch.setattr("runner.loop.time.perf_counter", lambda: 0.0)

    run_sync_loop(world, fixed_delta=0.05, should_continue=_stop_after(1))

    assert sleep_calls == [0.05]


def test_run_sync_loop_unpaced_never_sleeps_even_when_the_tick_ran_fast(monkeypatch):
    world = _FakeWorld()
    sleep_calls = []
    monkeypatch.setattr("runner.loop.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("runner.loop.time.perf_counter", lambda: 0.0)

    run_sync_loop(world, fixed_delta=0.05, should_continue=_stop_after(1), paced=False)

    assert sleep_calls == []


def test_run_async_loop_paced_by_default_sleeps_when_the_tick_ran_fast(monkeypatch):
    world = _FakeWorld()
    sleep_calls = []
    monkeypatch.setattr("runner.loop.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("runner.loop.time.perf_counter", lambda: 0.0)

    run_async_loop(world, fixed_delta=0.05, should_continue=_stop_after(1))

    assert sleep_calls == [0.05]


def test_run_async_loop_unpaced_never_sleeps_even_when_the_tick_ran_fast(monkeypatch):
    world = _FakeWorld()
    sleep_calls = []
    monkeypatch.setattr("runner.loop.time.sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr("runner.loop.time.perf_counter", lambda: 0.0)

    run_async_loop(world, fixed_delta=0.05, should_continue=_stop_after(1), paced=False)

    assert sleep_calls == []
