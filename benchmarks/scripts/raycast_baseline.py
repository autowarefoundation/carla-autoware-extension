#!/usr/bin/env python3
"""The M4 sweep's ABLATION arm: the identical LiDAR rig, publishing disabled.

    PYTHONPATH=. python3 benchmarks/scripts/raycast_baseline.py \
        --rig extension --tick-hz 20.0 --out-dir <run-dir> \
        --lidar-channels 16 --lidar-pps 288000

The transport sweep decomposes where sensor-pipeline time goes. This is the
decomposition's BASELINE: a plain CARLA client that spawns the same ego + top
LiDAR the cell's normal path spawns, with every native-ROS 2 attribute removed
and no ``enable_for_ros()`` call, listens with a do-nothing sink, and
sync-ticks the world at the cell's REGISTERED tick for the run's window. No
ROS, no DDS, no Autoware -- so

    transport cost = total - baseline

DISCLOSED LIMITATION (mandatory; the wrap doc depends on it). A CARLA sensor
only produces data while a client is subscribed to its stream, so the baseline
has to ``sensor.listen(...)`` to make the raycast happen at all -- and that
listen ships every cloud over the client stream, which is an RPC hop the
native cells' in-process publisher does NOT pay. The "baseline" therefore
includes work the native path does not do, so ``transport cost = total -
baseline`` is a **LOWER BOUND** for the native cells (A, B), not an equality.
It is not softened anywhere downstream and must not be quoted as one.

WHAT THIS WRITES, AND WHY IT IS THIS FILE
`sweep_verdict.py` scores an ablation run from `manifest.json` (arm
"ablation"), `resources.csv`'s `rtf` series, `observer.csv` (existence),
NO `publisher_counts.json` (publishing is disabled by design, and a
file-backed `0` would FIRE the ceiling's publisher disjunct on a run that
never intended to publish) and NO `quality.json` (the ablation arm defaults
`quality_ok=True` with a note, because no closed loop runs). Every one of
those is written -- or deliberately not written -- by the harness around this
client, with one exception:

`clock.csv`. The `rtf` column is NOT produced by the sampler (which writes the
`-1` "not measured" sentinel in every row) but by `sampler/finalize_rtf.py`,
which derives it from `clock.csv`; and `clock.csv` is normally written by
`bench_observer` from `/clock`, which nothing publishes on this arm. So this
client writes `clock.csv` itself, one row per tick, `clock_ns` from the world
snapshot and `arrival_system_ns` from `time.time_ns()` -- the same
`CLOCK_REALTIME` domain `sample_resources.py` stamps its `sample_system_ns`
with, which is what makes finalize_rtf's [t-1s, t] window join valid. That
file is also what keeps `run.sh` step 7's clock watchdog from excluding every
ablation run as `stall:clock`, and what gives step 15's smoke the >= 2 rows
`fit_sim_wall_affine` needs.

WHY THE ABLATION ARM BOOTS CARLA WITHOUT `--ros2` (measured 2026-08-03)
A bring-up probe booted the extension fork's editor exactly as this arm did
before that measurement -- `--ros2 --rmw=cyclonedds --ros2-extension`, no
runner, no Autoware -- and probed it from the campaign's own matched
Humble/cyclonedds instrument (the host's Jazzy CLI cannot even parse the fork's
type hashes, so it is not a trustworthy witness here). Two findings, both
load-bearing:

  * `/clock` is not merely advertised, it EMITS at 19.959 Hz (two windows, 21
    and 41 samples, min 0.050 s / max 0.051 s) once this client ticks the
    world. So `bench_observer` would be an ACTIVE, per-row-flushed writer to
    `clock.csv` at the same time as this one -- two byte streams at two
    independent offsets in one file. This also SETTLES the open contradiction
    benchmarks/README.md records as "Task 14's to settle" for the extension
    fork: a `--ros2` editor publishes `/clock` with no runner attached.
  * a `/carla/<vehicle>/ray_cast2/point_cloud` topic is advertised for a rig
    spawned with NO `ros_*` attributes and no `enable_for_ros()`. Removing the
    attributes does NOT stop the server's native layer from standing a
    publisher up for the sensor, so "publishing disabled" was not actually
    true under `--ros2`.

Booted with no `--ros2` at all, the same instrument sees only its own
`/parameter_events` and `/rosout`: the server is silent, nothing can publish,
and this client is the unambiguous sole writer of `clock.csv`. That is the boot
the launchers' ablation branch now uses. It is what makes the arm's name true,
and it is also the right baseline for the decomposition -- a DDS participant
standing publishers up is transport cost, not raycast cost. The direction is
safe for the disclosed lower bound above: dropping the ROS 2 layer can only
make the baseline SMALLER, and `T - B` stays a lower bound as long as
`B >= pure raycast`, which the client-stream hop already guarantees.

THIS WRITER STILL DEFENDS ITSELF, so the file contract does not rest on that
boot flag staying dropped. `bench_observer` runs on every arm (run.sh step 6
starts it unconditionally, and its constructor is what creates the
`observer.csv` `sweep_verdict.py` requires to EXIST). Its clock.csv behaviour
was verified live rather than assumed: it opens the file with
`std::ofstream::open` (i.e. O_TRUNC) at step 6 -- AFTER the launcher started
this client at step 5 -- and its header is BUFFERED, not flushed (only the
`/clock` callback and the destructor flush). Measured: a clock.csv holding a
header and two rows became **0 bytes** the instant the observer started, stayed
0 bytes for the whole run, and gained its 27-byte header only when SIGINT ran
the destructor. So `ClockCsvWriter`:

  * appends (`O_APPEND` places each write at the file's current end,
    atomically) and tracks exactly how many bytes it has written;
  * on `size < expected` -- the step-6 truncation -- RE-ASSERTS the header and
    carries on. Without that the file is headerless for the whole run,
    `clock_watchdog.newest_arrival_ns` hands the first data row to
    `csv.DictReader` as field NAMES and KeyErrors on every row, and every
    ablation run is excluded `stall:clock` after the 30 s grace. The
    re-assertion is idempotent against the observer's own teardown flush, which
    writes the same 27 bytes at offset 0: `CLOCK_HEADER` is byte-identical to
    `bench_observer.cpp`'s literal (pinned by a test).
  * on `size > expected` -- something else is EXTENDING the file, i.e. `/clock`
    is flowing after all -- STANDS DOWN: it stops writing clock.csv for the
    rest of the run and says so loudly, on stderr and in
    `raycast_baseline.json`. The observer's own per-row-flushed series is then
    the better one anyway, and it feeds finalize_rtf and the watchdog exactly
    as on every other arm. Yielding is always safe; interleaving two byte
    streams in one file never is.
  * re-checks the size AFTER the row lands (added 2026-08-03) and REBUILDS the
    file if it shrank underneath. The three rules above stat, decide, then
    append, and `O_APPEND` resolves the offset at write time -- so a truncation
    landing in that window puts a data row at offset 0 and the next row's
    shrink rule would re-assert the header AFTER it, which reproduces the
    headerless-file failure exactly. Reported as `clock_toctou_repairs`.

DISCLOSED RIG DIFFERENCES, beyond the RPC hop above. Each is stated with the
direction it biases `T - B`, because a reader can only use the number if the
direction is known:
  * The baseline spawns the top LiDAR only. Cell A's measured rig is LiDAR +
    IMU, and cell B's demo additionally spawns IMU, GNSS, vehicle_status and a
    traffic-light camera.

    MAGNITUDE CORRECTED 2026-08-03 (P4 whole-branch review); the correction
    is recorded rather than the sentence silently swapped, because the
    understatement was in the campaign's favour. This entry used to read
    "Their publish cost therefore lands inside `T - B`". That is too small by
    a lot: those sensors are not spawned in `B` AT ALL, so their ENTIRE cost
    lands in `T - B` -- spawn, per-tick simulation, RENDER and publish, not
    only the publish half. On cell B that set includes a traffic-light
    CAMERA, whose render pass is not transport by any reading of the word. So
    `T - B` OVER-estimates transport with respect to the un-spawned sensor
    set, in the opposite direction to the RPC-hop caveat above, and this is
    the larger of the two terms.
    The rescue is unchanged and is what makes the number usable: this whole
    gap is a per-run CONSTANT, independent of the sweep class, so it shifts
    the INTERCEPT of transport-vs-class and not the SLOPE -- and the slope is
    what the sweep reads. Quoting a single cell's `T - B` as "the transport
    cost" is what the constant forbids; reading how `T - B` grows with the
    class is what it permits.
    Strictly, `T - B` is a lower bound on the native transport cost only if
    `H >= (R_T - R_B) + Ohm`, where `H` is the client-stream RPC hop this
    baseline pays, `R_T`/`R_B` are the two rigs' raycast costs and `Ohm` is
    the un-spawned sensors' whole-lifecycle cost. That inequality is asserted
    nowhere and measured nowhere. It is stated here so the bound is not
    quoted as if it had been established.
  * Cell B's demo applies `max_substep_delta_time=0.001, max_substeps=10`
    (patch 0003's `DEFAULT_SUBSTEP_CONFIG`); this client leaves CARLA's own
    physics-substepping defaults in place. With one stationary vehicle the
    difference is small, and its direction is safe: CARLA's defaults substep
    a 0.05 s tick where the demo's configuration cannot, so the baseline is if
    anything INFLATED, which makes `T - B` more conservative, not less.
  * The mount pose is the committed sensor-kit pose for both rigs -- exact for
    `--rig extension`, an estimate for `--rig tier4` (see `default_mount`).

IMPORT DISCIPLINE. ``carla`` is imported lazily inside ``main()``, after
argument parsing, so this module -- and the rig builders the unit tests
exercise -- import cleanly under bare pytest with no CARLA egg, which is how
CI runs it. Same rule, same reason, as ``runner/spawn.py`` and
``runner/__main__.py``.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

from runner.kit import TOP_LIDAR_FRAME, carla_attach_location, carla_attach_rotation, load_kit
from runner.loop import run_sync_loop
from runner.spawn import EGO_BLUEPRINT, TOP_LIDAR_BLUEPRINT, top_lidar_attributes

EXTENSION_RIG = "extension"
TIER4_RIG = "tier4"
RIGS = (EXTENSION_RIG, TIER4_RIG)

# The tier4-native (cell B) rig: the LITERAL defaults of
# benchmarks/patches/tier4-native/0003-autoware-demo-params.patch's
# generate_vlp16_blueprint, as recorded in that patch set's README ("It is PURE
# parameterization, and that was verified rather than asserted" -- the
# original-vs-patched attribute dump), MINUS its two `ros_*` keys
# (`ros_name: velodyne_top`, `ros_topic_name:
# /sensing/lidar/top/pointcloud_raw_ex`), which are exactly what this arm
# ablates. Transcribed rather than imported because the patched module lives in
# the fork tree, not in this repo -- so it is pinned by a unit test against the
# README's certified dump, and the two files must be changed together.
#
# `sensor_tick` is the demo's PUBLISH PERIOD (patch flag --lidar-rotation-hz ->
# 1/HZ), not the blueprint's `rotation_frequency`, which this demo has never
# set -- the identically-named extension-runner flag drives a different
# attribute. A sweep class pins channels + points_per_second only
# (cells.yaml `sweep_classes`), so neither is a class knob.
TIER4_LIDAR_ATTRIBUTES: dict[str, str] = {
    "channels": "16",
    "range": "100.0",
    "upper_fov": "10.0",
    "lower_fov": "-20.0",
    "points_per_second": "288000",
    "sensor_tick": "0.1",
}

CLOCK_HEADER = "clock_ns,arrival_system_ns\n"

# A hard cap on the tick loop, not the scoring window. The window is whatever
# run.sh sleeps (step 10) and whatever the sampler + finalize_rtf then cover;
# this only bounds how long an ORPHANED client (its launcher gone, its teardown
# missed) can keep ticking a server nobody is watching. Overridden per run by
# the launcher's BENCH_ABLATION_DURATION_S.
DEFAULT_DURATION_S = 600.0


def _ros_free(attrs: dict[str, str]) -> dict[str, str]:
    """`attrs` without any `ros*` attribute.

    Dropping them IS the ablation: `ros_topic_name` / `ros2_extended_lidar` /
    `ros_name` / `ros2_qos_*` are what make the fork's native publisher emit,
    and a rig that kept even one of them would be measuring the transport this
    arm exists to subtract. Matched on the `ros` prefix rather than by an
    explicit key list so a new native-publisher attribute added to
    `runner/spawn.py` is ablated by default instead of silently publishing
    from the baseline.
    """
    return {k: v for k, v in attrs.items() if not k.startswith("ros")}


def _class_overrides(channels: int | None, points_per_second: int | None) -> dict[str, str]:
    """The sweep class's two attribute overrides, as CARLA's string values.

    Only a key whose flag was actually given appears, so an omitted flag is a
    true no-op and each rig's own default stands (the same rule
    `runner/__main__.py::build_lidar_overrides` follows for the live rig).
    """
    overrides: dict[str, str] = {}
    if channels is not None:
        overrides["channels"] = str(channels)
    if points_per_second is not None:
        overrides["points_per_second"] = str(points_per_second)
    return overrides


def extension_rig_attributes(
    channels: int | None = None, points_per_second: int | None = None
) -> dict[str, str]:
    """Cell A's top-LiDAR rig with publishing disabled.

    DERIVED from `runner.spawn.top_lidar_attributes` -- the committed rig
    itself -- rather than transcribed, so a change to the measured rig follows
    into its own baseline automatically instead of the two drifting apart
    silently.
    """
    return _ros_free(top_lidar_attributes(_class_overrides(channels, points_per_second)))


def tier4_rig_attributes(
    channels: int | None = None, points_per_second: int | None = None
) -> dict[str, str]:
    """Cell B's top-LiDAR rig with publishing disabled (see
    TIER4_LIDAR_ATTRIBUTES for why this one is transcribed, not imported)."""
    return {**TIER4_LIDAR_ATTRIBUTES, **_class_overrides(channels, points_per_second)}


def rig_attributes(
    rig: str, channels: int | None = None, points_per_second: int | None = None
) -> dict[str, str]:
    if rig == EXTENSION_RIG:
        return extension_rig_attributes(channels, points_per_second)
    if rig == TIER4_RIG:
        return tier4_rig_attributes(channels, points_per_second)
    raise ValueError(f"unknown rig {rig!r}; registered rigs: {', '.join(RIGS)}")


def default_mount() -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """(location_m, rotation_deg) for the top LiDAR, from the committed kit.

    `runner/kit.py` composes base_link -> sensor_kit_base_link -> velodyne_top
    out of `runner/config/*.yaml` (the `awsim_labs_sensor_kit` calibration),
    which is the extension family's real mount and is therefore exact for
    `--rig extension`.

    For `--rig tier4` it is an APPROXIMATION, and a disclosed one: that
    family's mount lives in the fork's own `autoware_demo.py` transform chain
    (ego -> base_link -> sensor_kit -> lidar), which is not committed to this
    repo, so there is nothing here to derive it from. Ray COUNT is independent
    of it (channels x points_per_second is what the sweep classes move), so it
    cannot invalidate `T - B` the way a different ray budget would -- but
    per-ray cost does track traced distance and what each ray terminates on,
    so a wrong mount is not free either, and "both stacks model the same AWSIM
    kit, so it is centimetre-scale" is an argument, not evidence.

    PLAN OF RECORD for closing it, which needs no fork-tree access: on cell B's
    first MEASURED (non-ablation) run a CARLA client is already attached for
    ground truth, so read the spawned LiDAR actor's transform relative to the
    ego through the API, record it, and pass it to `--mount` on that cell's
    ablation runs. Until that is done the tier4 baseline carries this estimate,
    and `--mount` is the seam it goes through.

    DISCHARGED 2026-08-04 (Task 14). The paragraph above is kept as written
    rather than edited, because what it predicted is part of the record. Task
    11 took the measurement on cell B-cyc's first measured run (PROVENANCE
    sec 14.5; benchmarks/evidence/p4-task11-bringup/b-cyc-lidar-mount.log),
    and `cells/tier4-native.sh` now passes it as `--mount` on every tier4
    ablation run -- so this function is no longer on that family's measured
    path. Two corrections it is owed:

      * "both stacks model the same AWSIM kit, so it is centimetre-scale" was
        an argument, and it was WRONG: the gap is 1.397071 m along the
        vehicle's x axis -- the tier4 rig's extra `base_link` anchor actor --
        while the rotation is EXACTLY this kit's, to the last digit.
      * a direct `--rig tier4` invocation with no `--mount` still gets the
        estimate, so it stays reachable by hand. The launcher is the only
        production caller, and it always passes the measured pose.
    """
    kit = load_kit()
    return carla_attach_location(kit, TOP_LIDAR_FRAME), carla_attach_rotation(kit, TOP_LIDAR_FRAME)


class ClockCsvWriter:
    """Self-defending appender for the run directory's `clock.csv`.

    See the module docstring for the measured `bench_observer` behaviour this
    is built against. Three rules, each paid for by a live observation:

      * APPEND (`O_APPEND` = every write at the file's current end, atomically)
        and FLUSH PER ROW. The flush is not tidiness: `clock_watchdog.py` polls
        this file once a second as the run's liveness signal and excludes the
        run once the newest arrival stamp ages past 5 s, so a block-buffered
        writer looks exactly like a frozen sim -- the same reasoning
        `bench_observer.cpp` gives for flushing clock.csv and nothing else.
      * SIZE SHRANK -> the observer truncated the file when it opened it at
        run.sh step 6. Re-assert the header (byte-identical to the observer's
        own, so its buffered copy landing at offset 0 at teardown is a no-op)
        and carry on. Without this the file is headerless for the whole run and
        the watchdog KeyErrors its way to a `stall:clock` exclusion.
      * SIZE GREW BEYOND WHAT WE WROTE -> another process is extending the
        file. STAND DOWN permanently rather than interleave two byte streams:
        the only writer that can do this is the observer with a live `/clock`,
        whose series is strictly better than ours anyway.
      * SIZE SHRANK *WHILE THE ROW WAS BEING WRITTEN* -- the fourth rule, added
        2026-08-03, because the three above have a TOCTOU window between them.
        `write()` stats, decides, then appends, and `O_APPEND` resolves the
        offset at WRITE time rather than at decision time; a truncation landing
        in that interval puts a data row at offset 0 with no header above it,
        and the shrink rule then re-asserts the header AFTER that orphan. The
        file's first line is then a data row, `csv.DictReader` takes it as the
        field NAMES, and every consumer KeyErrors: the watchdog's
        `newest_arrival_ns` is permanently None, the run is excluded
        `stall:clock`, and rtf stays at the -1 sentinel so `sweep_verdict`
        raises "no valid rtf samples". That is the exact failure the three
        rules above exist to prevent, reached through a narrower door. So the
        size is re-checked AFTER the row lands, and a file that shrank
        underneath is rebuilt (header + row) rather than appended to. Rare
        (~1e-4 per run) and it costs a LOST run, never a wrong number -- which
        is why it is repaired rather than stood down for.

    `rows`, `header_reasserts`, `toctou_repairs` and
    `stood_down`/`stand_down_reason` are reported in `raycast_baseline.json` so
    a run's own file records which of these happened instead of it having to be
    inferred later.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.rows = 0
        self.header_reasserts = 0
        self.toctou_repairs = 0
        self.stood_down = False
        self.stand_down_reason = ""
        self._expected_size = 0
        self._f = None

    def __enter__(self) -> ClockCsvWriter:
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = open(self.path, "a", newline="")
        # Whatever is already there is somebody else's (nothing writes this
        # file before step 5 in practice); count it as ours only so far as the
        # size bookkeeping is concerned, and add the header if the file is new.
        self._expected_size = self._observed_size() or 0
        if self._expected_size == 0:
            self._emit(CLOCK_HEADER)

    def _observed_size(self) -> int | None:
        try:
            return self.path.stat().st_size
        except OSError:
            return None

    def _emit(self, text: str) -> None:
        self._f.write(text)
        self._f.flush()
        self._expected_size += len(text)

    def _stand_down(self, reason: str) -> None:
        self.stood_down = True
        self.stand_down_reason = reason
        print(
            f"raycast_baseline: STANDING DOWN from {self.path}: {reason}. "
            "Another process is writing this file (a live /clock through "
            "bench_observer is the only candidate), and its series is the "
            "authoritative one; this client will keep ticking the world but "
            "will not write another clock row.",
            file=sys.stderr,
        )

    def write(self, clock_ns: int, arrival_system_ns: int) -> None:
        if self.stood_down:
            return
        size = self._observed_size()
        if size is None:
            # The file went away entirely (not something any component of this
            # harness does). Reopen rather than keep writing into an orphaned
            # inode nothing will ever read.
            self.close()
            self.open()
        elif size < self._expected_size:
            # run.sh step 6: bench_observer truncated it. Our rows from before
            # that point are gone -- they are bring-up, outside every scoring
            # window -- and the file needs its header back.
            self._expected_size = size
            self._emit(CLOCK_HEADER)
            self.header_reasserts += 1
        elif size > self._expected_size:
            self._stand_down(f"file is {size} bytes, {self._expected_size} written by this client")
            return
        row = f"{int(clock_ns)},{int(arrival_system_ns)}\n"
        self._emit(row)
        self.rows += 1
        # TOCTOU: the size check above and this append are not atomic, and
        # `O_APPEND` resolves the offset when the write happens rather than when
        # the decision was made. If the observer's one-shot truncation landed in
        # between, `row` is now sitting at offset 0 with no header above it --
        # and re-asserting the header on the NEXT call would put it AFTER a data
        # row, which is worse than the headerless file the shrink rule exists to
        # repair (csv.DictReader would read the orphan as the field names). Both
        # orderings are covered: a truncation that lands after this stat is
        # caught by the pre-write check on the next call, with our row already
        # gone.
        after = self._observed_size()
        if after is not None and after < self._expected_size:
            # Truncate away the orphan rather than append around it: the file is
            # smaller than what this client alone wrote, so there is nothing of
            # anyone else's in it to destroy. Rebuilding keeps the invariant the
            # whole class defends -- the header is always the first line.
            self._f.truncate(0)
            self._expected_size = 0
            self._emit(CLOCK_HEADER)
            self._emit(row)
            self.toctou_repairs += 1

    def close(self) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None


class NullSink:
    """The `sensor.listen` callback: counts and drops.

    The brief's shape is `lambda d: None`; the only addition is the counter,
    and it is deliberate. Publishing is disabled and the GT collector's
    `--count-lidar` is off, so `publisher_counts.json` and `observer.csv` are
    both (correctly) empty -- which leaves NO record anywhere that the rig
    raycast anything at all. One integer increment per cloud is the cheapest
    possible evidence that this run measured a live sensor rather than an idle
    one, and it is reported in `raycast_baseline.json`. It does not touch the
    point data.
    """

    def __init__(self):
        self.count = 0

    def __call__(self, data) -> None:
        self.count += 1


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Publish-disabled LiDAR raycast baseline (M4 sweep, ablation arm)."
    )
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2000)
    p.add_argument(
        "--rig",
        required=True,
        choices=RIGS,
        help="which family's rig to reproduce: extension (cell A) or tier4 (cell B)",
    )
    p.add_argument(
        "--class-id",
        default="",
        help="sweep class id, recorded in raycast_baseline.json for provenance; the "
        "class's ACTUAL effect comes from --channels/--pps, which the cell launcher "
        "derives (cells/extension.sh, cells/tier4-native.sh)",
    )
    # The launchers' Task-6 class mapping emits `--lidar-channels N --lidar-pps
    # N` (the runner's / the tier4 demo's own flag names). Accepting those
    # spellings as aliases is what lets each ablation branch pass
    # $BENCH_RUNNER_SWEEP_ARGS / $BENCH_TIER4_SWEEP_ARGS through VERBATIM,
    # instead of re-deriving the class mapping a third time.
    p.add_argument("--channels", "--lidar-channels", dest="channels", type=int, default=None)
    p.add_argument("--pps", "--lidar-pps", dest="pps", type=int, default=None)
    p.add_argument(
        "--tick-hz",
        type=float,
        required=True,
        help="sync fixed-delta target = 1/HZ. The cell's REGISTERED metrics.tick_hz "
        "(cells.yaml, via cell_info.metrics_for): sweep_verdict.py scores paced and "
        "ablation at the same paced target, so this must not be a literal",
    )
    p.add_argument("--duration-s", type=float, default=DEFAULT_DURATION_S)
    p.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="the run directory: clock.csv and raycast_baseline.json are written here",
    )
    p.add_argument(
        "--ego-blueprint",
        default=EGO_BLUEPRINT,
        help=f"the LiDAR's carrier vehicle (default: {EGO_BLUEPRINT})",
    )
    # Same two spellings the two families' launchers already produce for their
    # own clients: cells/extension.sh derives `--initial-pose x y z 0 0 yaw`
    # (run_e2e.sh -> runner) and cells/tier4_autoware.sh derives `--spawn-pose
    # x y z 0 0 yaw` (the patched demo). Accepting both means each ablation
    # branch reuses its family's existing derivation verbatim.
    p.add_argument(
        "--initial-pose",
        "--spawn-pose",
        dest="initial_pose",
        nargs=6,
        type=float,
        default=None,
        metavar=("X_M", "Y_M", "Z_M", "ROLL_DEG", "PITCH_DEG", "YAW_DEG"),
        help="ego spawn pose in CARLA world coordinates (metres, degrees)",
    )
    p.add_argument(
        "--spawn-index",
        type=int,
        default=0,
        help="index into world.get_map().get_spawn_points(); ignored when a pose is given",
    )
    p.add_argument(
        "--mount",
        nargs=6,
        type=float,
        default=None,
        metavar=("X_M", "Y_M", "Z_M", "ROLL_DEG", "PITCH_DEG", "YAW_DEG"),
        help="override the LiDAR's attach pose on the ego (default: the committed "
        "sensor-kit pose; see default_mount() for why that is exact for --rig "
        "extension and an approximation for --rig tier4)",
    )
    return p


def _summary_path(out_dir: Path) -> Path:
    return Path(out_dir) / "raycast_baseline.json"


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    # 1/tick_hz is the sync fixed delta, so a non-positive value is a
    # ZeroDivisionError or a negative delta several lines below, after the
    # connect. Refused here, by name, in the style the rest of this harness
    # refuses things -- unreachable through the launchers (both read the value
    # from the registry, which refuses a null) but reachable by hand.
    if args.tick_hz <= 0:
        parser.error(
            f"--tick-hz must be > 0 (got {args.tick_hz}): it is inverted into the "
            "world's fixed_delta_seconds"
        )

    # Everything above is argument resolution and must stay CARLA-free: the
    # `--help` path is exercised offline by the unit tests and by the operator
    # on a machine with no wheel installed.
    import carla

    attrs = rig_attributes(args.rig, args.channels, args.pps)
    if args.mount:
        location = tuple(args.mount[:3])
        rotation = tuple(args.mount[3:])
    else:
        location, rotation = default_mount()

    fixed_delta = 1.0 / args.tick_hz
    print(f"raycast_baseline: rig={args.rig} class={args.class_id or '-'} attrs={attrs}")
    print(
        f"raycast_baseline: tick {args.tick_hz} Hz (fixed_delta {fixed_delta:.6f} s), "
        f"duration cap {args.duration_s} s, mount {location} {rotation}"
    )

    stop = {"stop": False}

    def _handle_signal(signum, frame):
        # Teardown SIGTERMs this client BEFORE it stops CARLA, so the loop must
        # exit through run_sync_loop's `finally` (which restores the world's
        # prior settings) and through this function's own actor destroy, while
        # the server is still alive. A client left ticking a dead server hangs
        # on actor destroy -- this repo's documented teardown gotcha.
        stop["stop"] = True

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    client = carla.Client(args.host, args.port)
    client.set_timeout(20.0)
    world = client.get_world()

    if args.initial_pose:
        x, y, z, roll, pitch, yaw = args.initial_pose
        spawn = carla.Transform(
            carla.Location(x=x, y=y, z=z), carla.Rotation(roll=roll, pitch=pitch, yaw=yaw)
        )
    else:
        spawn_points = world.get_map().get_spawn_points()
        if not 0 <= args.spawn_index < len(spawn_points):
            raise IndexError(
                f"--spawn-index {args.spawn_index} out of range; the map has "
                f"{len(spawn_points)} spawn points"
            )
        spawn = spawn_points[args.spawn_index]

    blueprints = world.get_blueprint_library()
    ego_bp = blueprints.find(args.ego_blueprint)
    # role_name only: NOT `ros2_ackermann_control` (the ego is a stationary
    # carrier here, and opting into a native control sink would be one more
    # ROS path in a run whose whole point is that none are active).
    ego_bp.set_attribute("role_name", "ego")
    ego = world.spawn_actor(ego_bp, spawn)

    lidar_bp = blueprints.find(TOP_LIDAR_BLUEPRINT)
    for key, value in attrs.items():
        # Unconditional, no has_attribute() skip: every attribute in both rigs
        # is stock LiDAR geometry (the native-ROS2 discriminators are exactly
        # what _ros_free removed), so a missing one is a real blueprint
        # mismatch and must surface as CARLA's own named set_attribute error
        # rather than being silently dropped from the workload.
        lidar_bp.set_attribute(key, value)
    lidar = world.spawn_actor(
        lidar_bp,
        carla.Transform(
            carla.Location(x=location[0], y=location[1], z=location[2]),
            carla.Rotation(roll=rotation[0], pitch=rotation[1], yaw=rotation[2]),
        ),
        attach_to=ego,
    )

    sink = NullSink()
    # THE RPC HOP (see the module docstring's disclosed limitation): a CARLA
    # sensor only raycasts while a client is subscribed to its stream, so this
    # subscription is what makes the baseline measure anything at all -- and it
    # ships every cloud to this process, which the native in-process publisher
    # does not do.
    lidar.listen(sink)

    clock = ClockCsvWriter(Path(args.out_dir) / "clock.csv")
    clock.open()
    started_ns = time.time_ns()
    deadline = time.monotonic() + args.duration_s
    ticks = 0
    sim_ns: list[int] = []

    def _on_tick() -> None:
        nonlocal ticks
        ticks += 1
        snapshot = world.get_snapshot()
        clock_ns = int(snapshot.timestamp.elapsed_seconds * 1e9)
        sim_ns.append(clock_ns)
        clock.write(clock_ns, time.time_ns())

    def _should_continue() -> bool:
        return not stop["stop"] and time.monotonic() < deadline

    try:
        run_sync_loop(
            world,
            fixed_delta=fixed_delta,
            on_tick=_on_tick,
            should_continue=_should_continue,
            paced=True,
        )
    finally:
        clock.close()
        # Best effort, in this order, and never allowed to mask the original
        # failure: stop the stream, destroy the sensor, destroy the ego.
        for label, fn in (
            ("lidar.stop", lidar.stop),
            ("lidar.destroy", lidar.destroy),
            ("ego.destroy", ego.destroy),
        ):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 - teardown must not raise
                print(f"raycast_baseline: {label} failed during teardown: {exc}", file=sys.stderr)
        summary = {
            "rig": args.rig,
            "class_id": args.class_id,
            "attributes": attrs,
            "ego_blueprint": args.ego_blueprint,
            "lidar_blueprint": TOP_LIDAR_BLUEPRINT,
            "mount_location_m": list(location),
            "mount_rotation_deg": list(rotation),
            "tick_hz": args.tick_hz,
            "fixed_delta_s": fixed_delta,
            "duration_cap_s": args.duration_s,
            "ticks": ticks,
            "clock_rows_written": clock.rows,
            # The clock.csv contention record (see ClockCsvWriter): one
            # re-assert is the NORMAL case (bench_observer truncating the file
            # at run.sh step 6), and `clock_stood_down` true means /clock was
            # flowing after all and the observer's series -- not this one -- is
            # what the run was scored from.
            "clock_header_reasserts": clock.header_reasserts,
            # Non-zero means a truncation landed inside write()'s check/append
            # window and the file was rebuilt (see ClockCsvWriter's fourth
            # rule). Expected to be 0 on essentially every run; a run that
            # reports one is not damaged, but it is the ~1e-4 race actually
            # occurring and is worth knowing when reading that run's clock.csv.
            "clock_toctou_repairs": clock.toctou_repairs,
            "clock_stood_down": clock.stood_down,
            "clock_stand_down_reason": clock.stand_down_reason,
            "sensor_callbacks": sink.count,
            "started_system_ns": started_ns,
            "ended_system_ns": time.time_ns(),
            "sim_span_ns": (max(sim_ns) - min(sim_ns)) if sim_ns else 0,
            "stopped_by_signal": stop["stop"],
        }
        _summary_path(args.out_dir).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        print(
            f"raycast_baseline: {ticks} ticks, {sink.count} sensor callbacks, "
            f"{clock.rows} clock rows"
            + (f" (STOOD DOWN: {clock.stand_down_reason})" if clock.stood_down else "")
            + f" -> {_summary_path(args.out_dir)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
