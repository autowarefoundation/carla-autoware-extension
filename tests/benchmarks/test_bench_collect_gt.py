"""benchmarks/scripts/collect_gt.py: gt.csv is written in the MAP frame.

Not in the task brief's test list, but the map-frame conversion is the one
detail in Task 8 whose failure is silent and campaign-wide: raw CARLA
coordinates in gt.csv make every `pose_error` in
`benchmarks/analysis/quality.evaluate_quality` wrong by the map offset --
plausible-looking on Town10 (offset zero, Y flip only) and nonsense on
Nishi-Shinjuku. These tests pin that the conversion is the SHARED pinned one,
not a re-derivation.

Pure-Python: `collect_gt.main()` lazy-imports `carla`, so this module (and
its transitive imports) collect under bare pytest with no CARLA egg.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path

import pytest

from benchmarks.analysis.publisher_counts import publisher_counts_doc, read_publisher_counts
from benchmarks.scripts import collect_gt
from benchmarks.scripts.cell_info import load_cells_doc, metrics_for
from scripts.e2e.collect_gt import ego_map_xy
from scripts.e2e.verify_mgrs_handedness import MAP_OFFSETS, offset_for_map

REPO_ROOT = Path(__file__).resolve().parents[2]
CELLS_DIR = REPO_ROOT / "benchmarks" / "cells"

NISHI = MAP_OFFSETS["NishishinjukuMap"]
TOWN10 = MAP_OFFSETS["Town10HD_Opt"]


@pytest.mark.parametrize("offset", [NISHI, TOWN10])
def test_map_pose_xy_agrees_with_the_gates_ego_map_xy(offset):
    """The load-bearing equivalence: this module's x/y is byte-for-byte what
    `scripts/e2e/collect_gt.ego_map_xy` -- the function the live gates and
    `arm_closed_loop.sh` already use -- returns for the same input."""
    x, y, _z, _yaw = collect_gt.map_pose(-278.39, 220.54, 3.5, 12.0, offset)
    assert (x, y) == ego_map_xy(-278.39, 220.54, offset)


def test_map_pose_applies_the_offset_and_the_single_y_flip():
    ox, oy, oz = NISHI
    x, y, z, _yaw = collect_gt.map_pose(-278.39, 220.54, 3.5, 0.0, NISHI)
    assert math.isclose(x, ox - 278.39, abs_tol=1e-9)
    assert math.isclose(y, oy - 220.54, abs_tol=1e-9)  # Y flip
    assert math.isclose(z, oz + 3.5, abs_tol=1e-9)  # z is offset, never flipped


def test_map_pose_is_not_the_identity_on_a_nonzero_offset_map():
    """Guards the exact regression this file exists for: a gt.csv written in
    raw CARLA coordinates. On Nishi the two differ by ~81 km."""
    x, y, _z, _yaw = collect_gt.map_pose(-278.39, 220.54, 0.0, 0.0, NISHI)
    assert math.hypot(x - (-278.39), y - 220.54) > 80_000.0


def test_map_pose_on_town10_is_the_y_flip_only():
    """Town10's registered offset is (0, 0, 0), so the frames differ ONLY by
    the Y flip -- the case where a missing conversion looks like a small
    localization error instead of an obvious blunder."""
    x, y, z, _yaw = collect_gt.map_pose(-28.35, -69.72, 1.5, 0.0, TOWN10)
    assert (x, y, z) == (-28.35, 69.72, 1.5)


def test_map_pose_yaw_is_the_negated_carla_yaw_in_radians():
    _x, _y, _z, yaw = collect_gt.map_pose(0.0, 0.0, 0.0, -34.187, NISHI)
    assert math.isclose(yaw, math.radians(34.187), abs_tol=1e-12)


def test_offset_resolution_refuses_an_unknown_map():
    """`main()` resolves the offset before connecting, so a typo'd map name
    costs milliseconds rather than a whole recorded window in a wrong frame."""
    with pytest.raises(ValueError, match="unknown map"):
        offset_for_map("Town42")


def test_gt_columns_match_the_registered_contract():
    from benchmarks.analysis.bench_io import GT_FLOAT_COLS, GT_INT_COLS

    assert collect_gt.GT_COLUMNS == GT_INT_COLS + GT_FLOAT_COLS


def test_sim_ns_rounds_rather_than_truncates():
    # 0.05 s ticks are not exactly representable; truncation would bias every
    # stamp low, and quality.evaluate_quality joins gt to NDT on these.
    assert collect_gt.sim_ns_from_elapsed(0.05) == 50_000_000
    assert collect_gt.sim_ns_from_elapsed(1.15) == 1_150_000_000


def _gt_count_lidar_for_arm(script: Path, bench_arm: str) -> str | None:
    """The value `script`'s launch.env would carry for `GT_COUNT_LIDAR` on
    `bench_arm`, or None when this launcher does not write the key at all.

    Obtained by extracting the REAL decision block and the REAL launch.env
    line out of the launcher and RUNNING them as bash -- the extract-then-
    execute idiom of `test_sweep_args.py` / `test_teardown.py`. This used to
    be a `^GT_COUNT_LIDAR="1"` source match, which stopped being an answer
    the moment P4's ablation arm made the switch conditional
    (`GT_COUNT_LIDAR="$LAUNCH_GT_COUNT_LIDAR"`): the scan then matched
    nothing and reported that NO launcher counts, silently emptying the loop
    below -- one more instance of this suite's binding rule that a text scan
    is not a pin. Evaluating the real chain (BENCH_ARM ->
    BENCH_ARM_IS_ABLATION -> LAUNCH_GT_COUNT_LIDAR -> the launch.env line)
    answers for any arm and cannot be fooled by a spelling change.
    """
    text = script.read_text()
    env_line = re.search(r'^(GT_COUNT_LIDAR="[^"]*")$', text, re.M)
    if not env_line:
        return None
    arm_flag = re.search(
        r'^(BENCH_ARM_IS_ABLATION=0\n\[ "\$BENCH_ARM" = "ablation" \] '
        r"&& BENCH_ARM_IS_ABLATION=1)$",
        text,
        re.M,
    )
    switches = re.search(r"^(LAUNCH_GT_ENABLED=.*?\nfi)$", text, re.M | re.DOTALL)
    # A launcher with no ablation branch at all (calibration.sh,
    # python-bridge.sh) writes the key as a literal, so its env line alone is
    # the whole chain. Nothing is asserted about which shape a launcher has:
    # `set -u` below turns a half-extracted chain into a real non-zero exit,
    # which the returncode check catches with bash's own message rather than
    # this file's guess at one.
    #
    # CORRECTED 2026-08-04 (final whole-branch review). This comment used to
    # explain those two launchers' missing branch with "neither registers a
    # sweep arm". That premise is FALSE, and it was false when written: the
    # sweep arms are a TOP-LEVEL global in cells.yaml
    # (`sweep_arms: [paced, unpaced, ablation]`), not a per-cell key, so
    # `cell_info.merge` hands them to every registered cell and run.sh's arm
    # gate opened `ablation` for all four families. `run.sh E --arm ablation
    # --class vlp16 --check-args` exited 0. run.sh now refuses the arm for any
    # approach whose launcher does not implement it, and
    # `test_every_approach_either_implements_the_ablation_arm_or_refuses_it`
    # below is what keeps the two lists from drifting apart again.
    parts = ["set -euo pipefail", f'BENCH_ARM="{bench_arm}"']
    parts += [m.group(1) for m in (arm_flag, switches) if m]
    parts.append(env_line.group(1))
    parts.append("printf 'RESULT<<%s>>\\n' \"$GT_COUNT_LIDAR\"")
    snippet = "\n".join(parts) + "\n"
    result = subprocess.run(
        ["bash", "-c", snippet], capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == 0, f"{script}: {result.stderr}"
    match = re.search(r"RESULT<<(.*?)>>", result.stdout)
    assert match, f"{script}: snippet printed no RESULT marker: {result.stdout!r}"
    return match.group(1)


def _counting_approaches(bench_arm: str = "static") -> set[str]:
    """The approaches whose launcher turns `--count-lidar` on for `bench_arm`,
    read from the committed launchers themselves (`run.sh`: "cells/<approach>.sh
    is invoked as `plan` or `up`") rather than from a hand-kept list here."""
    return {
        path.stem
        for path in CELLS_DIR.glob("*.sh")
        if _gt_count_lidar_for_arm(path, bench_arm) == "1"
    }


def test_the_ablation_arm_turns_the_publisher_side_count_off():
    """The M4 ablation arm's own half of the contract, on the REAL launchers:
    `publisher_counts.json` must be ABSENT on that arm (publishing is disabled
    by design), and `sweep_verdict._publisher_rate_ratio` reads an absent file
    as "not measurable" while a file-backed 0 would FIRE the ceiling's
    publisher disjunct. `--count-lidar` is what writes the file, so the switch
    that must be off is this one."""
    sweep_launchers = [
        CELLS_DIR / "extension.sh",
        CELLS_DIR / "tier4-native.sh",
    ]
    for script in sweep_launchers:
        assert _gt_count_lidar_for_arm(script, "static") == "1", script
        assert _gt_count_lidar_for_arm(script, "ablation") == "0", script


def _implements_the_ablation_arm(approach: str) -> bool:
    """Does `cells/<approach>.sh` branch on the ablation arm at all?

    Read from the launcher, not from a list kept here -- the whole defect this
    guards was two lists (cells.yaml's arms and the launchers' branches) that
    nothing compared. `BENCH_ARM_IS_ABLATION` is the switch every implementing
    launcher sets; a launcher without it never starts the baseline client.
    """
    return "BENCH_ARM_IS_ABLATION" in (CELLS_DIR / f"{approach}.sh").read_text()


def _one_cell_per_approach() -> dict[str, str]:
    """One reachable (non-`dropped:`) cell id per registered approach."""
    doc = load_cells_doc()
    out: dict[str, str] = {}
    for entry in doc["cells"]:
        if entry.get("dropped"):
            continue
        out.setdefault(str(entry["approach"]), str(entry["id"]))
    return out


@pytest.mark.parametrize("approach", sorted(_one_cell_per_approach()))
def test_every_approach_either_implements_the_ablation_arm_or_refuses_it(approach):
    """No approach may ACCEPT `--arm ablation` without implementing it.

    `sweep_arms: [paced, unpaced, ablation]` is a top-level global in
    cells.yaml, so `cell_info.merge` hands it to every registered cell and
    run.sh's arm gate opened `ablation` for all four families -- while only
    `extension.sh` and `tier4-native.sh` have an ablation branch. Verified
    live before the guard existed: `run.sh E --arm ablation --class vlp16
    --check-args` exited 0, and E is not `dropped:`.

    What such a run FILES is why acceptance is the defect: it boots the full
    publishing stack, never starts `raycast_baseline.py`, and writes
    `manifest.arm = "ablation"`. `publisher_counts.json` is then absent for
    the ordinary reason (`python-bridge.sh` sets `GT_COUNT_LIDAR="0"` as a
    literal), which is exactly the state `sweep_verdict` reads as "publishing
    disabled by design" -- so it renders a clean ablation row for a baseline
    containing the whole transport layer. `T - B ~ 0`, silently.

    Parametrised over the REGISTERED approaches and answered from the
    LAUNCHERS, so a family added later is covered without editing this test:
    it either grows an ablation branch or run.sh must refuse it.
    """
    cell = _one_cell_per_approach()[approach]
    proc = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "benchmarks" / "run.sh"),
            cell,
            "--arm",
            "ablation",
            "--class",
            "vlp16",
            "--check-args",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if _implements_the_ablation_arm(approach):
        # A family that DOES implement it must still be able to run it -- so a
        # refusal that simply blocks `ablation` outright cannot satisfy this.
        assert proc.returncode == 0, (
            f"cells/{approach}.sh implements the ablation arm but run.sh "
            f"refused cell {cell}:\n{proc.stderr}"
        )
    else:
        assert proc.returncode != 0, (
            f"run.sh accepted `--arm ablation` for cell {cell} ({approach}), whose "
            f"launcher cells/{approach}.sh has no ablation branch. That run files "
            f'arm="ablation" for a fully-publishing stack:\n{proc.stdout}'
        )
        # WHICH refusal fires is deliberately not pinned here: the calibration
        # family is refused earlier and for an independent reason (no sweep
        # class lists a CAL-* cell in `applies_to`, so `cell_info.merge` rejects
        # the invocation before the arm gate is reached), and pinning a message
        # would make this test assert the ORDER of run.sh's preflight rather
        # than the property. What must hold for every non-implementing family
        # is only that nothing accepts the arm -- with a NAMED failure, never a
        # bare crash. `test_the_ablation_arm_is_refused_for_the_bridge_family`
        # pins the new refusal's own wording on the one cell that could reach
        # it.
        assert "FAIL:" in proc.stderr, proc.stderr


def test_the_ablation_arm_is_refused_for_the_bridge_family():
    """The one live hole, pinned by its own message.

    Cell E is `approach: python-bridge`, is not `dropped:`, and IS registered
    for `vlp16` -- so it was the one cell that could reach the arm gate with a
    valid class and be ACCEPTED. Verified live before the guard existed:
    `run.sh E --arm ablation --class vlp16 --check-args` exited 0.
    """
    proc = subprocess.run(
        [
            "bash",
            str(REPO_ROOT / "benchmarks" / "run.sh"),
            "E",
            "--arm",
            "ablation",
            "--class",
            "vlp16",
            "--check-args",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode != 0, proc.stdout
    assert "arm 'ablation' is not implemented by the python-bridge family" in proc.stderr, (
        proc.stderr
    )


def test_publisher_counts_key_matches_every_reconciled_cells_registered_topic():
    """`publisher_counts.json`'s key and the key the reconciliation looks
    it up by come from two different places, and they must agree.

    `run.sh` invokes the collector without `--lidar-topic`, so the file is
    keyed by `collect_gt.DEFAULT_LIDAR_TOPIC`; `duel_verdict.py` and
    `sweep_verdict.py` look it up by `cells.yaml`'s registered
    `lidar_topic` for the cell. They agree today for every cell that will
    be reconciled -- a coincidence with nothing pinning it. A divergence
    surfaces in `duel_verdict` as a per-run FAILED note, but
    `sweep_verdict._publisher_rate_ratio` has no guard and aborts the
    whole sweep, and both tools run ONCE, after all data is collected.
    """
    doc = load_cells_doc()
    counting = _counting_approaches()
    assert counting, "no cell launcher sets GT_COUNT_LIDAR=1 -- has the flag been renamed?"

    checked = []
    for entry in doc["cells"]:
        if entry.get("approach") not in counting:
            continue
        topic = metrics_for(doc, entry["id"])["lidar_topic"]
        if topic is None:  # not registered yet; nothing to reconcile against
            continue
        assert topic == collect_gt.DEFAULT_LIDAR_TOPIC, (
            f"cell {entry['id']} registers lidar_topic {topic!r} but its "
            f"launcher counts into {collect_gt.DEFAULT_LIDAR_TOPIC!r}"
        )
        checked.append(entry["id"])
    assert checked, "no counting cell has a registered lidar_topic to check"


def test_run_sh_does_not_override_the_publisher_counts_key():
    """The premise of the test above: `run.sh` passes no `--lidar-topic`,
    so `DEFAULT_LIDAR_TOPIC` is what lands in the file. If it ever starts
    passing one, that value -- not the default -- is what must be checked
    against the registry, and this pin is what says so out loud."""
    run_sh = (REPO_ROOT / "benchmarks" / "run.sh").read_text()
    assert "--lidar-topic" not in run_sh


class _SensorData:
    """The one attribute the counting callback reads off a CARLA
    measurement: `timestamp`, the episode's elapsed SIM seconds."""

    def __init__(self, timestamp):
        self.timestamp = timestamp


def test_lidar_stamp_recorder_records_sim_stamps_not_arrival_times():
    """publisher_counts.json's registered domain is SIM time, so the
    duel's windowed publisher count is filtered on the same clock as its
    observed count (observer.csv's header_stamp_ns) and its window
    bounds -- no clock fit in between. Recording a wall stamp here would
    silently make the publisher term a different domain from the other
    two."""
    series: list[int] = []
    record = collect_gt.lidar_stamp_recorder(series)
    record(_SensorData(0.05))
    record(_SensorData(1.15))
    assert series == [50_000_000, 1_150_000_000]


def test_lidar_stamp_recorder_uses_gt_csvs_own_rounding_rule():
    """Same function gt.csv's sim_ns column goes through, so a message
    and the tick that produced it cannot land a nanosecond apart for two
    different rounding rules."""
    series: list[int] = []
    collect_gt.lidar_stamp_recorder(series)(_SensorData(3.3))
    assert series == [collect_gt.sim_ns_from_elapsed(3.3)]


def test_written_publisher_counts_are_readable_by_the_analysis_reader(tmp_path):
    """The writer and the two verdict tools' reader must agree on the
    on-disk shape; this pins that they do, through the real functions
    rather than a restatement of the schema in a fixture."""
    path = tmp_path / "publisher_counts.json"
    stamps = [0, 50_000_000, 100_000_000]
    path.write_text(json.dumps(publisher_counts_doc({collect_gt.DEFAULT_LIDAR_TOPIC: stamps})))
    counts = read_publisher_counts(path)
    assert counts.whole_run_count(collect_gt.DEFAULT_LIDAR_TOPIC) == 3
    assert counts.count_in_window(collect_gt.DEFAULT_LIDAR_TOPIC, 50_000_000, 100_000_000) == 2


def test_count_lidar_is_refused_for_the_bridge_approach(capsys):
    """The bridge publishes FROM a sensor.listen callback and CARLA keeps one
    callback per sensor, so attaching a counter there would silence the run's
    pointcloud. Refused, not documented-and-hoped."""
    rc = collect_gt.main(
        ["--out", "/tmp/unused-gt.csv", "--count-lidar", "--approach", "python-bridge"]
    )
    assert rc == collect_gt.EXIT_BAD_ARGS
    assert "sensor.listen" in capsys.readouterr().err


def test_unknown_map_exits_before_connecting(capsys):
    """No CARLA is running in the test environment; reaching the client would
    hang or raise ImportError, so a clean exit 2 also proves the map check
    happens first."""
    rc = collect_gt.main(["--out", "/tmp/unused-gt.csv", "--map", "Town42"])
    assert rc == collect_gt.EXIT_BAD_ARGS
    assert "unknown map" in capsys.readouterr().err


def test_matching_versions_are_accepted():
    assert collect_gt.version_mismatch("0.10.0", "0.10.0") is None


def test_client_server_version_mismatch_is_refused():
    """The campaign's "the client always matches its server" rule was recorded
    but enforced nowhere: a BENCH_GT_PYTHON pointed at the wrong fork's venv
    produced a run that looked entirely valid, with gt.csv -- the M5 ground
    truth -- written by a client never verified against that server. CARLA
    only logs a version warning, which is invisible from a backgrounded
    collector."""
    msg = collect_gt.version_mismatch("0.9.15", "0.10.0")
    assert msg is not None
    # The message must name both sides and the knob that fixes it, or an
    # operator cannot act on it from one log line.
    assert "0.9.15" in msg and "0.10.0" in msg and "BENCH_GT_PYTHON" in msg


class _Sensor:
    def __init__(self, parent):
        self.parent = parent


class _Ego:
    id = 42


class _Actors(list):
    def filter(self, pattern):
        assert pattern == "sensor.lidar.*"
        return self


class _World:
    def __init__(self, actors):
        self._actors = _Actors(actors)

    def get_actors(self):
        return self._actors


def test_ego_lidar_sensors_selects_only_the_egos_children():
    ego = _Ego()
    other = _Ego()
    other.id = 7
    mine, theirs, orphan = _Sensor(ego), _Sensor(other), _Sensor(None)
    found = collect_gt.ego_lidar_sensors(_World([mine, theirs, orphan]), ego.id)
    assert found == [mine]


# --- attach-chain walk (Task 13, results/B/run-007) -------------------------
# The tier4 demo hangs its rig off ego -> base_link -> sensor_kit -> sensor, so
# the ego's LiDAR is a great-grandchild. A direct-parent test found nothing and
# --count-lidar refused a run whose LiDAR was demonstrably on the ego.


class _FakeActor:
    def __init__(self, actor_id, parent=None):
        self.id = actor_id
        self.parent = parent


def test_direct_child_is_a_descendant():
    from benchmarks.scripts.collect_gt import is_descendant_of

    ego = _FakeActor(1)
    assert is_descendant_of(_FakeActor(2, parent=ego), 1)


def test_great_grandchild_is_a_descendant_which_is_the_tier4_demo_layout():
    from benchmarks.scripts.collect_gt import is_descendant_of

    ego = _FakeActor(1)
    base_link = _FakeActor(2, parent=ego)
    sensor_kit = _FakeActor(3, parent=base_link)
    lidar = _FakeActor(4, parent=sensor_kit)
    assert is_descendant_of(lidar, 1)


def test_unparented_actor_is_not_a_descendant():
    from benchmarks.scripts.collect_gt import is_descendant_of

    assert not is_descendant_of(_FakeActor(2), 1)


def test_actor_on_a_different_ego_is_not_a_descendant():
    from benchmarks.scripts.collect_gt import is_descendant_of

    other = _FakeActor(99)
    assert not is_descendant_of(_FakeActor(2, parent=other), 1)


def test_cyclic_parent_chain_terminates_instead_of_hanging():
    """A cycle must be bounded: the collector runs during start-up."""
    from benchmarks.scripts.collect_gt import is_descendant_of

    a = _FakeActor(2)
    b = _FakeActor(3, parent=a)
    a.parent = b
    assert not is_descendant_of(b, 1)


def test_depth_limit_is_respected():
    from benchmarks.scripts.collect_gt import is_descendant_of

    ego = _FakeActor(1)
    node = ego
    for i in range(6):
        node = _FakeActor(10 + i, parent=node)
    assert is_descendant_of(node, 1, max_depth=8)
    assert not is_descendant_of(node, 1, max_depth=3)
