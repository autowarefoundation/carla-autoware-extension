"""Extension preflight check + the CARLA tick loop (sync + async fallback) + physics
substepping config (--substep-config).

Import discipline: this module imports ``subprocess``, ``time``, and ``yaml`` only, never
``carla``, so it (and the ``extension_exports_init`` preflight) stays importable under bare
pytest with no CARLA egg, which is how CI runs it (see ``runner/spawn.py`` for the same rule
on the spawn side). ``yaml`` is a pure-Python dependency already relied on by
``runner/kit.py`` for the same reason.
``run_sync_loop``/``run_async_loop`` take a ``world`` object structurally (get_settings /
apply_settings / tick / wait_for_tick), so they are unit-testable with a fake world too.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable

import yaml


def extension_exports_init(so_path: str) -> bool:
    """True iff ``so_path`` exports ``carla_ros2_extension_init`` as a defined (type ``T``)
    symbol, per ``nm -D``. Used by ``--extension-check`` as a build-freshness preflight
    (run_g0.sh style): a stale or wrong .so fails loudly here instead of silently no-op'ing
    at CARLA's ``--ros2-extension=`` load time.

    Returns False (never raises) for a nonexistent path, a non-ELF file, or an ELF file with
    no dynamic symbol table -- all of those make ``nm -D`` fail, which is exactly the "does
    not export the symbol" answer this preflight needs.
    """
    try:
        out = subprocess.run(
            ["nm", "-D", so_path], capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return any("carla_ros2_extension_init" in ln and " T " in ln for ln in out.splitlines())


def _default_should_continue() -> bool:
    return True


# Today's exact cadence (20 Hz): the one source of truth for both loop functions' own
# ``fixed_delta`` default AND ``runner/__main__.py``'s ``--fixed-delta`` argparse default,
# so the two never drift apart (--fixed-delta unset must reproduce this exactly).
DEFAULT_FIXED_DELTA = 0.05


def run_sync_loop(
    world,
    fixed_delta: float = DEFAULT_FIXED_DELTA,
    on_tick: Callable[[], None] | None = None,
    should_continue: Callable[[], bool] | None = None,
    paced: bool = True,
) -> None:
    """Synchronous fixed-delta tick loop with real-time pacing.

    This is the correct mode for closed-loop driving on this CARLA 0.10 build (verified live
    2026-07-23): given a valid trajectory the sync ego propels (445 m closed-loop drive), and
    NDT needs the sync-paced 20 Hz ``/clock``. An earlier "vehicles do not propel in sync"
    claim was refuted -- it had only ever been observed against a stop command
    (docs/e2e-report.md, Gates footnote).

    Loops until ``should_continue()`` returns False (a SIGINT handler flips it in ``__main__``);
    restores the world's PRIOR synchronous_mode AND fixed_delta_seconds in the ``finally`` so a
    Ctrl-C or exception never leaves the world stuck in sync mode (or a stale fixed-delta) for
    an unrelated client.

    ``paced`` (default True -- today's exact behaviour) gates the real-time pacing sleep
    below; ``--unpaced`` passes False so the M4 load sweep ticks the server as fast as
    possible instead of holding a 20 Hz wall-clock cadence. Sync MODE itself is unaffected
    either way -- only the sleep is skipped.
    """
    if should_continue is None:
        should_continue = _default_should_continue
    settings = world.get_settings()
    prev_sync = settings.synchronous_mode
    prev_fixed_delta = settings.fixed_delta_seconds
    settings.synchronous_mode = True
    settings.fixed_delta_seconds = fixed_delta
    world.apply_settings(settings)
    try:
        while should_continue():
            t0 = time.perf_counter()
            world.tick()
            if on_tick:
                on_tick()
            if paced:
                dt = time.perf_counter() - t0
                if dt < fixed_delta:
                    time.sleep(fixed_delta - dt)  # real-time pacing (20 Hz cadence)
    finally:
        settings.synchronous_mode = prev_sync
        settings.fixed_delta_seconds = prev_fixed_delta
        world.apply_settings(settings)


def run_async_loop(
    world,
    fixed_delta: float = DEFAULT_FIXED_DELTA,
    on_tick: Callable[[], None] | None = None,
    should_continue: Callable[[], bool] | None = None,
    paced: bool = True,
) -> None:
    """Async loop for deliberate experiments: the server ticks itself; the runner only paces
    the host loop and waits for each server tick. NOT the closed-loop driving path: with the
    server free-running, ``/clock`` runs at ~140 Hz and NDT breaks outright (18-65 m error;
    docs/e2e-report.md "Async localization"), so use ``run_sync_loop`` to drive.

    Loops until ``should_continue()`` returns False. Puts the world into async mode up front;
    unlike ``run_sync_loop`` there is no prior-mode restore in a ``finally`` because leaving the
    world in async mode on exit is the correct, harmless steady state (async is CARLA's default).

    ``paced`` (default True -- today's exact behaviour): see ``run_sync_loop``, same gate on
    the same real-time pacing sleep.
    """
    if should_continue is None:
        should_continue = _default_should_continue
    settings = world.get_settings()
    settings.synchronous_mode = False
    world.apply_settings(settings)
    while should_continue():
        t0 = time.perf_counter()
        world.wait_for_tick()
        if on_tick:
            on_tick()
        if paced:
            dt = time.perf_counter() - t0
            if dt < fixed_delta:
                time.sleep(fixed_delta - dt)


def load_physics_config(path: str) -> dict[str, float | int]:
    """Load the substepping parity values from a physics.yaml like
    ``benchmarks/config/physics.yaml`` (``--substep-config``).

    Returns exactly the two keys ``carla.WorldSettings`` needs: ``max_substep_delta_time``
    (float, seconds) and ``max_substeps`` (int). This is the single source of substepping
    parity between the extension (approach A) and the tier4-native fork (approach B)
    runners -- harmonising the two is what makes the A-vs-B benchmark duel a fair comparison.

    Raises ``ValueError`` naming the key, the file, and the cause (run_g0.sh preflight
    style -- same mandate as ``_apply_attributes``'s ``RuntimeError``/
    ``select_spawn_point``'s ``IndexError``) if a key is missing/null -- the committed
    ``benchmarks/config/physics.yaml`` ships with both keys null until Task 13 fills them
    in, so this is the expected failure mode of pointing ``--substep-config`` at it as-is
    -- or present but not a number.
    """
    with open(path) as f:
        doc = yaml.safe_load(f) or {}
    config: dict[str, float | int] = {}
    for key, cast in (("max_substep_delta_time", float), ("max_substeps", int)):
        value = doc.get(key)
        if value is None:
            raise ValueError(
                f"{path!r} does not set {key!r} to a number (found {value!r}): "
                "benchmarks/config/physics.yaml's schema is filled in by Task 13 -- pass "
                "a physics.yaml with both max_substep_delta_time and max_substeps set, "
                "or omit --substep-config to skip substepping parity."
            )
        try:
            config[key] = cast(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{path!r} has a malformed {key!r} value {value!r}: {exc}") from exc
    return config


def apply_substep_config(world, config: dict[str, float | int]) -> None:
    """Apply ``config`` (``load_physics_config``'s return) to ``world`` before the run
    (``--substep-config``, for A-hf/tier4 substepping parity). Reads the current settings,
    sets ONLY ``max_substep_delta_time``/``max_substeps``, and applies -- every other setting
    (sync mode, fixed_delta_seconds, ...) is left exactly as ``run_sync_loop``/
    ``run_async_loop`` will set it afterwards.
    """
    settings = world.get_settings()
    settings.max_substep_delta_time = config["max_substep_delta_time"]
    settings.max_substeps = config["max_substeps"]
    world.apply_settings(settings)
