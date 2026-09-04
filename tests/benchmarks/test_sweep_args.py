"""Behavioural pins for benchmarks/cells/extension.sh's and
benchmarks/cells/tier4-native.sh's sweep class -> sensor-argument derivation
(Task 6, P4 spec 1e -- the residue of struck Task 26, now owned 2026-08-03).

Before this task both launchers refused ANY `--class` unconditionally:
neither derived `--lidar-channels`/`--lidar-pps` from a class id, so an
operator had to supply `BENCH_RUNNER_SWEEP_ARGS` / `BENCH_TIER4_SWEEP_ARGS`
by hand for every sweep run -- including the two pre-registered classes
(`cells.yaml` `sweep_classes`: `vlp16`, `32ch`). This derives the mapping so
`run.sh <cell> --arm paced --class vlp16` works without hand-supplied
environment, while an explicit env var still wins and an unmapped class id
(anything other than `vlp16`/`32ch`, notably the still-struck `128ch`) still
refuses -- an unmapped class would file a run under the WRONG workload
label, which is a false measurement, not an out-of-scope one.

Per this suite's binding rule (tests/benchmarks/test_teardown.py's module
docstring: a bare substring/text-scan assertion is NOT a pin -- six prior
violations, most recently Task 17b finding F5, where two wiring assertions
both still passed with the call site commented out), the properties below
that assert real BEHAVIOUR (a class derives the right flags, an unmapped id
actually refuses, an explicit env var actually survives) are pinned by
extracting the REAL derivation block out of each launcher by regex -- the
same extract-then-execute idiom test_teardown.py's
`_extract_aw_sidecar_snippet` / `_extract_relay_sidecar_snippet` use for
their polling loops -- and running it as REAL bash, with a `fail()` stub
matching each launcher's own (`echo ... >&2; exit 2`), observing REAL
effects: the sweep-args variable's actual post-block value, or the process
actually exiting 2 with the `fail` stub actually invoked. None of that can
pass with the case arms commented out or the guard condition inverted --
there would be nothing to observe.

The two mapping-presence checks (`test_*_literal_mapping_values_in_source`)
and the two removed-text checks (`test_*_old_unconditional_refusal_text_is_gone`)
are the ones this suite's rule explicitly allows as snippet extraction alone:
there is no "behaviour" beyond the literal text for a static case-arm
constant or for a string's absence, so reading the extracted block (for the
former) or the whole file (for the latter, an explicit Step-1 requirement)
is the direct, honest pin -- not a substitute for one.

WHY EVERY TEST ABOVE WAS BLIND TO THE DEFECT THAT COST SIX RUNS (P4 Task 15
review finding C1, fixed 2026-08-04). All of them run the derivation block
and then read the variable back IN THE SAME PROCESS. That is the whole of
what cells/extension.sh needs -- it expands `${BENCH_RUNNER_SWEEP_ARGS:-}`
into `RUNNER_EXTRA_ARGS` in the PARENT (extension.sh:477) -- but it is only
half of what cells/tier4-native.sh needs. There the MEASURED arms spawn
`bash "$TIER4_DEMO"` through an explicit prefix-assignment whitelist, and
`cells/tier4_autoware.sh` expands `${BENCH_TIER4_SWEEP_ARGS:-}` in that
CHILD. The derivation was a plain, unexported shell assignment and the
whitelist did not carry it, so the child expanded it to empty and the
patched demo fell back to its own defaults --
`--lidar-channels 16 --lidar-pps 288000`
(patches/tier4-native/0003-autoware-demo-params.patch), which IS the vlp16
class. Task 15's six B-cyc measured runs at `--class 32ch` therefore booted
a vlp16 rig and were filed under a manifest stamped `class_id: "32ch"`.

It was invisible to every LABEL check for a reason worth keeping: the
extension runner's own default is the 128-channel rig, so a silent fallback
on cell A would have been loud in any size or rate reading, whereas the
tier4 demo's default IS vlp16 -- the very class the sweep had just measured.
Only a per-run MEASURED quantity could have caught it, and the proof that
finally did is the observer's median lidar `size_bytes` on
`/sensing/lidar/top/pointcloud_raw_ex`: cell A stepped 245 144 B -> 1 020 888 B
(x4.164, against the class ratio 1 200 000 / 288 000 = 4.167), cell B-cyc
238 904 B -> 238 840 B (x0.9997, i.e. not at all).

So the two tests at the bottom of this file are SUBPROCESS-level: they run
the real derivation block and then read the value back out of a CHILD
PROCESS, which is the only place the defect was ever observable. Verified by
mutation on the fix commit -- deleting the `export` from tier4-native.sh
makes both of them fail and leaves every other test in this file green.
They are deliberately NOT parametrized over both launchers: cell A's
consumer is in-parent by design, so demanding an export there would pin a
property the extension family does not have and does not need.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXTENSION_SH = REPO / "benchmarks" / "cells" / "extension.sh"
TIER4_SH = REPO / "benchmarks" / "cells" / "tier4-native.sh"

# The registered mapping (cells.yaml `sweep_classes`), load-bearing per the
# task brief: vlp16 -> 16 ch / 288 000 pts/s, 32ch -> 32 ch / 1 200 000 pts/s.
VLP16_FLAGS = "--lidar-channels 16 --lidar-pps 288000"
CH32_FLAGS = "--lidar-channels 32 --lidar-pps 1200000"

CASES = [
    pytest.param(EXTENSION_SH, "BENCH_RUNNER_SWEEP_ARGS", "extension", id="extension"),
    pytest.param(TIER4_SH, "BENCH_TIER4_SWEEP_ARGS", "tier4-native", id="tier4-native"),
]


def _extract_derivation_block(script: Path) -> str:
    """Pulls the REAL `if [ -n "${BENCH_CLASS_ID:-}" ] ... fi` derivation
    block out of `script` by regex -- the same extract-then-execute idiom
    test_teardown.py's `_extract_aw_sidecar_snippet` uses for its polling
    loop, so a change to the real block is what these tests run, not this
    file's own memory of it."""
    text = script.read_text()
    pattern = re.compile(r'(if \[ -n "\$\{BENCH_CLASS_ID:-\}" \].*?\nfi\n)', re.DOTALL)
    m = pattern.search(text)
    assert m, f"sweep-class derivation block not found in {script}"
    return m.group(1)


def _run_derivation(
    snippet: str,
    sweep_var: str,
    *,
    class_id: str | None,
    explicit_value: str | None = None,
) -> subprocess.CompletedProcess:
    """Runs the REAL extracted derivation block as real bash, under the same
    `set -euo pipefail` the launchers themselves run under, with a `fail()`
    stub that reproduces each launcher's own shape (message to stderr, exit
    2) so a `case` arm that actually calls `fail` is observable as a real
    non-zero exit, not an inferred one. Echoes the sweep-args variable's
    post-block value so a passing run can assert on it directly."""
    script = (
        "set -euo pipefail\n"
        'fail() { echo "STUB-FAIL: $*" >&2; exit 2; }\n'
        f"{snippet}\n"
        f"printf 'RESULT<<%s>>\\n' \"${{{sweep_var}:-}}\"\n"
    )
    env = dict(os.environ)
    if class_id is None:
        env.pop("BENCH_CLASS_ID", None)
    else:
        env["BENCH_CLASS_ID"] = class_id
    if explicit_value is None:
        env.pop(sweep_var, None)
    else:
        env[sweep_var] = explicit_value
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )


def _result_value(stdout: str) -> str:
    m = re.search(r"RESULT<<(.*?)>>", stdout, re.DOTALL)
    assert m, f"derivation snippet never printed its RESULT<<...>> marker: {stdout!r}"
    return m.group(1)


# --- (a)/(b): literal mapping values, snippet extraction -------------------
#
# Per the module docstring: there is no "behaviour" beyond the literal text
# for a static case-arm constant, so reading the extracted block is the
# direct pin for THIS property (the two real-execution tests further below
# additionally prove the block, run for real, actually assigns these
# values).


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_literal_mapping_values_are_present_in_source(script, sweep_var, label):
    block = _extract_derivation_block(script)
    assert f'vlp16) {sweep_var}="{VLP16_FLAGS}"' in block, block
    assert f'32ch)  {sweep_var}="{CH32_FLAGS}"' in block, block
    # 128ch is registered in cells.yaml sweep_classes but stays struck on
    # either M4 branch (README, "core-duel scope cut"); it must NOT gain a
    # mapping arm here, or a --class 128ch request would silently stop
    # refusing and file a run under a workload label that was never measured
    # or agreed.
    assert "128ch)" not in block, block


# --- (c): the unknown-id branch still fails, real subprocess ---------------


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_derivation_refuses_an_unmapped_class_id(script, sweep_var, label):
    snippet = _extract_derivation_block(script)
    result = _run_derivation(snippet, sweep_var, class_id="128ch")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "STUB-FAIL" in result.stderr, result.stderr
    assert "no registered sensor-argument" in result.stderr, result.stderr
    # `fail()` exits the whole snippet immediately (real launcher semantics:
    # `set -euo pipefail` plus an explicit `exit 2`), so the `printf
    # 'RESULT<<...>>'` line after the block never runs at all -- a bogus
    # value could not have been assigned AND printed. Confirmed directly:
    # stdout must be empty, not merely non-matching.
    assert result.stdout == ""


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_derivation_refuses_an_arbitrary_unknown_class_id(script, sweep_var, label):
    """Same property as above, for an id that was never registered at all
    (not even as a struck class) -- the `*)` catch-all arm, not a
    128ch-specific one."""
    snippet = _extract_derivation_block(script)
    result = _run_derivation(snippet, sweep_var, class_id="does-not-exist")
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert "STUB-FAIL" in result.stderr, result.stderr


# --- vlp16 / 32ch actually derive the registered flags, real subprocess ----


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_derivation_maps_vlp16_to_the_registered_flags(script, sweep_var, label):
    snippet = _extract_derivation_block(script)
    result = _run_derivation(snippet, sweep_var, class_id="vlp16")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _result_value(result.stdout) == VLP16_FLAGS


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_derivation_maps_32ch_to_the_registered_flags(script, sweep_var, label):
    snippet = _extract_derivation_block(script)
    result = _run_derivation(snippet, sweep_var, class_id="32ch")
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _result_value(result.stdout) == CH32_FLAGS


# --- explicit env var still wins, real subprocess ---------------------------


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_explicit_sweep_args_env_var_still_wins_over_derivation(script, sweep_var, label):
    """An operator-supplied BENCH_RUNNER_SWEEP_ARGS / BENCH_TIER4_SWEEP_ARGS
    must survive untouched even for a registered class id -- the derivation
    is a convenience default, not an override of an explicit value."""
    snippet = _extract_derivation_block(script)
    explicit = "--lidar-channels 999 --lidar-pps 1"
    result = _run_derivation(snippet, sweep_var, class_id="vlp16", explicit_value=explicit)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _result_value(result.stdout) == explicit


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_explicit_sweep_args_env_var_wins_even_for_an_unmapped_class(script, sweep_var, label):
    """An explicit override is enough to run ANY class id, mapped or not --
    the whole point of the escape hatch both launchers' original refusal
    text documented ("Supply ... explicitly to override")."""
    snippet = _extract_derivation_block(script)
    explicit = "--lidar-channels 128 --lidar-pps 4600000"
    result = _run_derivation(snippet, sweep_var, class_id="128ch", explicit_value=explicit)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _result_value(result.stdout) == explicit


@pytest.mark.parametrize("script,sweep_var,label", CASES)
def test_no_class_id_leaves_sweep_args_untouched(script, sweep_var, label):
    """No --class at all (the non-sweep default): the whole block must be a
    no-op, not merely non-fatal."""
    snippet = _extract_derivation_block(script)
    result = _run_derivation(snippet, sweep_var, class_id=None)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert _result_value(result.stdout) == ""


# --- Step 1's explicit requirement: the OLD unconditional refusal is gone --


def test_extension_sh_old_unconditional_refusal_text_is_gone():
    text = EXTENSION_SH.read_text()
    assert "needs the runner sweep parameters from Task 12" not in text, (
        "extension.sh still contains the pre-Task-6 unconditional refusal "
        "text -- the old blanket fail() must be replaced, not merely "
        "supplemented"
    )


def test_tier4_native_sh_old_unconditional_refusal_text_is_gone():
    text = TIER4_SH.read_text()
    assert "needs the tier4-side sensor arguments spelled" not in text, (
        "tier4-native.sh still contains the pre-Task-6 unconditional "
        "refusal text -- the old blanket fail() must be replaced, not "
        "merely supplemented"
    )


# --- both launchers still parse as valid bash -------------------------------


@pytest.mark.parametrize("script", [EXTENSION_SH, TIER4_SH])
def test_launcher_still_parses_as_valid_bash(script):
    result = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, timeout=10, check=False
    )
    assert result.returncode == 0, result.stderr


# --- C1: the derived value must SURVIVE INTO A CHILD PROCESS ---------------
#
# See the module docstring's "why every test above was blind" section. These
# two are the pins for the tier4-native measured arm, and each one FAILS if
# the `export` is removed from the derivation block.

# The spawn statement at the bottom of tier4-native.sh: an explicit
# prefix-assignment whitelist followed by `bash "$TIER4_DEMO"`. The whitelist
# is a deliberate, documented cell-contract surface and the C1 fix does NOT
# widen it -- so this regex must keep matching the real statement, and the
# test below runs it rather than a copy of it.
_SPAWN_BLOCK_RE = re.compile(
    r'(^BENCH_REPO="\$BENCH_REPO" \\\n.*?\n  bash "\$TIER4_DEMO"\n)',
    re.DOTALL | re.MULTILINE,
)

# Everything the extracted spawn statement dereferences, other than the sweep
# args themselves. Dummy values: this test observes WHICH variables cross the
# process boundary, never what they contain.
_SPAWN_BLOCK_STUB_ENV = {
    "BENCH_REPO": "/nonexistent/repo",
    "BENCH_CELL": "B-cyc",
    "BENCH_MAP": "Town10HD_Opt",
    "BENCH_ARM": "paced",
    "BENCH_RPC_PORT": "2000",
    "BENCH_ROUTE_FILE": "/nonexistent/route.yaml",
    "BENCH_CARLA_TREE": "/nonexistent/tree",
    "BENCH_AUTOWARE_IMAGE": "example@sha256:0",
    "AW_CONTAINER": "autoware",
    "BENCH_RUN_DIR": "/nonexistent/run",
    "GT_PYTHON": "/nonexistent/python3",
    "TIER4_DEMO_PID_FILE": "/nonexistent/tier4_demo.pid",
}


def _extract_spawn_block(script: Path) -> str:
    text = script.read_text()
    m = _SPAWN_BLOCK_RE.search(text)
    assert m, f"tier4 demo spawn statement not found in {script}"
    return m.group(1)


def test_tier4_derived_sweep_args_reach_a_plain_child_process():
    """The narrow property, stated without any launcher machinery: after the
    REAL derivation block runs, a child process must see the derived value.

    A plain `bash -c` child inherits exactly the exported environment and
    nothing else, so this observes the export itself rather than any
    particular consumer's spelling of it. Unexported, the child prints an
    empty value -- which is precisely what
    `cells/tier4_autoware.sh`'s `${BENCH_TIER4_SWEEP_ARGS:-}` expanded to on
    Task 15's six B-cyc measured runs.
    """
    snippet = _extract_derivation_block(TIER4_SH)
    script = (
        "set -euo pipefail\n"
        'fail() { echo "STUB-FAIL: $*" >&2; exit 2; }\n'
        f"{snippet}\n"
        # A REAL second process, not a subshell: a subshell would see the
        # value whether it was exported or not, and would pass either way.
        'bash -c \'printf "CHILD<<%s>>\\n" "${BENCH_TIER4_SWEEP_ARGS:-}"\'\n'
    )
    env = dict(os.environ)
    env["BENCH_CLASS_ID"] = "32ch"
    env.pop("BENCH_TIER4_SWEEP_ARGS", None)
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10, check=False
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    m = re.search(r"CHILD<<(.*?)>>", result.stdout, re.DOTALL)
    assert m, f"child never printed its CHILD<<...>> marker: {result.stdout!r}"
    assert m.group(1) == CH32_FLAGS, (
        "the derived sweep args did not cross the process boundary -- "
        "BENCH_TIER4_SWEEP_ARGS is not exported at its derivation site, so "
        "the spawned tier4 demo falls back to its patched vlp16 defaults "
        "while the manifest still stamps the requested class (finding C1)"
    )


def test_tier4_spawned_demo_sees_the_derived_sweep_args():
    """The same property through the REAL spawn statement, whitelist included.

    `TIER4_DEMO` is pointed at a stub that echoes what it received, so this
    runs the launcher's own prefix-assignment list -- the surface finding C1
    ruled must NOT be widened -- and observes the value arriving in the
    process that actually expands it (`cells/tier4_autoware.sh:345`).
    Extracting the real statement means a future edit to that whitelist is
    covered here too, rather than by this file's memory of it.
    """
    snippet = _extract_derivation_block(TIER4_SH)
    spawn = _extract_spawn_block(TIER4_SH)
    with tempfile.TemporaryDirectory() as tmp:
        demo = Path(tmp) / "tier4_demo_stub.sh"
        demo.write_text(
            '#!/usr/bin/env bash\nprintf "DEMO<<%s>>\\n" "${BENCH_TIER4_SWEEP_ARGS:-}"\n'
        )
        assigns = "\n".join(f'{k}="{v}"' for k, v in _SPAWN_BLOCK_STUB_ENV.items())
        script = (
            "set -euo pipefail\n"
            'fail() { echo "STUB-FAIL: $*" >&2; exit 2; }\n'
            f"{snippet}\n"
            f"{assigns}\n"
            f'TIER4_DEMO="{demo}"\n'
            f"{spawn}\n"
        )
        env = dict(os.environ)
        env["BENCH_CLASS_ID"] = "32ch"
        env.pop("BENCH_TIER4_SWEEP_ARGS", None)
        env.pop("BENCH_RMW", None)
        env.pop("BENCH_DDS_PROFILE", None)
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, env=env, timeout=10, check=False
        )
    assert result.returncode == 0, (result.stdout, result.stderr)
    m = re.search(r"DEMO<<(.*?)>>", result.stdout, re.DOTALL)
    assert m, f"the spawned demo never printed its DEMO<<...>> marker: {result.stdout!r}"
    assert m.group(1) == CH32_FLAGS, (
        "the spawned tier4 demo received no sweep arguments: the derivation "
        "resolved them in the parent and they never crossed into the child "
        "(finding C1). The fix is `export` at the derivation site, NOT a new "
        "entry in this spawn statement's whitelist."
    )
