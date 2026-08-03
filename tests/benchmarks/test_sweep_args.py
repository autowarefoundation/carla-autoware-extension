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
"""

from __future__ import annotations

import os
import re
import subprocess
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
