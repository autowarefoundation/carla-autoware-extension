"""Extension preflight check + the CARLA tick loop (sync + async fallback).

Import discipline: this module imports ``subprocess`` and ``time`` only, never ``carla``,
so it (and the ``extension_exports_init`` preflight) stays importable under bare pytest with
no CARLA egg -- the M0 CI lesson (see ``runner/spawn.py`` for the same rule on the spawn side).
``run_sync_loop``/``run_async_loop`` take a ``world`` object structurally (get_settings /
apply_settings / tick / wait_for_tick), so they are unit-testable with a fake world too.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable


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


def run_sync_loop(
    world,
    fixed_delta: float = 0.05,
    on_tick: Callable[[], None] | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> None:
    """Synchronous fixed-delta tick loop with real-time pacing.

    NOTE (load-bearing, verified live): CARLA 0.10 (UE5/Chaos) vehicles do NOT propel in
    synchronous mode in this build -- control is delivered and wheels configured, but the ego
    stays at 0 m/s. Validate propulsion EARLY on any live run; if the ego does not move, use
    ``--async`` (``run_async_loop``) instead, where MPC-style steering-delay compensation
    absorbs the host-loop latency (see CLAUDE.md "CARLA 0.10 ... vehicles DO NOT propel").

    Loops until ``should_continue()`` returns False (a SIGINT handler flips it in ``__main__``);
    restores the world's PRIOR synchronous_mode AND fixed_delta_seconds in the ``finally`` so a
    Ctrl-C or exception never leaves the world stuck in sync mode (or a stale fixed-delta) for
    an unrelated client.
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
            dt = time.perf_counter() - t0
            if dt < fixed_delta:
                time.sleep(fixed_delta - dt)  # real-time pacing (20 Hz cadence)
    finally:
        settings.synchronous_mode = prev_sync
        settings.fixed_delta_seconds = prev_fixed_delta
        world.apply_settings(settings)


def run_async_loop(
    world,
    fixed_delta: float = 0.05,
    on_tick: Callable[[], None] | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> None:
    """Async fallback loop: the server ticks itself; the runner only paces the host loop and
    waits for each server tick, letting steering-delay compensation absorb the latency (CARLA
    vehicles do not propel in sync mode in this build -- see ``run_sync_loop``).

    Loops until ``should_continue()`` returns False. Puts the world into async mode up front;
    unlike ``run_sync_loop`` there is no prior-mode restore in a ``finally`` because leaving the
    world in async mode on exit is the correct, harmless steady state (async is CARLA's default).
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
        dt = time.perf_counter() - t0
        if dt < fixed_delta:
            time.sleep(fixed_delta - dt)
