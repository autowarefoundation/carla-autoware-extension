"""Unit tests for the Phase B runner CLI/loop layer (``runner.loop`` / ``runner.__main__``).

Pure-Python only where possible: ``runner.loop`` never imports ``carla`` at module level, so
these tests collect and run under a bare ``python3 -m pytest`` with no CARLA egg (the M0 CI
lesson -- see ``tests/phase_b/test_runner_kit.py`` for the same rule on the spawn side). The
tick-loop tests use a minimal fake ``world`` object (get_settings/apply_settings/tick/
wait_for_tick) rather than a real CARLA connection, since the live E2E run is deliberately
out of scope for this task (M4's job, per the task brief).
"""

from __future__ import annotations

import os

import pytest

from runner.__main__ import main as runner_main
from runner.loop import extension_exports_init, run_async_loop, run_sync_loop

# --- --extension-check: negative path (mandatory, brief Step 1) ---


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
# machine (Task 9-13's C++ work) but is NOT built in CI, so this test is gated on the
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
