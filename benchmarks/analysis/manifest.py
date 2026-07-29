"""Run manifest: one JSON per run, written before the run starts."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

APPROACHES = ("extension", "python-bridge", "tier4-native", "calibration")
ARMS = ("static", "closed-loop", "ablation", "unpaced", "paced")
TRANSPORT_KEYS = ("rmw", "shm_enabled", "dds_profile_sha256")
PLACEMENT_KEYS = ("run_mode", "container_image", "observer_env")
UE_APPROACHES = ("extension", "tier4-native")

# The pre-registered exclusion vocabulary (benchmarks/config/exclusions.md),
# kept in sync BY HAND: every reason `write_manifest.py --exclude` is asked
# to record must appear here, mapped to the criterion that documents it. This
# closes the gap that let run.sh emit reasons exclusions.md never actually
# registered (`crash:cell-launch`, `gate:injector-failed`, the harness
# recorder crashes, `stall:unpaced-window-cap`) while validate() only checked
# that SOME string was present. A reason missing from this set is exactly
# the drift exclusions.md's own closing sentence calls out: "Any exclusion
# not matching [the criteria] invalidates the campaign for that cell."
#
# Reasons that are a single fixed string -- no free-form detail after the
# prefix -- are matched exactly, not by a "crash:"/"gate:"/"stall:" prefix:
# a prefix would silently admit any future `crash:<anything>` the way the
# `stall:<detail>` wildcard in exclusions.md's old text silently admitted
# `stall:unpaced-window-cap` under the frozen-clock criterion it does not
# describe. That laundering is the bug being fixed here, so it must not be
# reintroduced through the back door of a permissive validator.
EXCLUSION_REASONS: frozenset[str] = frozenset({
    "crash:cell-launch",         # criterion 1
    "crash:observer",            # criterion 1
    "gate:arm-failed",           # criterion 2
    "gate:control_cmd-silent",   # criterion 2
    "gate:injector-failed",      # criterion 2
    "stall:clock",               # criterion 4
    "warmup:nishi",              # criterion 5
    "crash:sampler",             # criterion 9
    "crash:collect_gt",          # criterion 9
    "crash:clock_watchdog",      # criterion 9
    "stall:unpaced-window-cap",  # criterion 10
})
# Reasons that legitimately carry a variable, per-run detail after the
# prefix (a git sha, a loadavg reading, a port number, a tree path) -- the
# prefix alone is what exclusions.md registers for these.
EXCLUSION_REASON_PREFIXES: tuple[str, ...] = (
    "harness:",   # criterion 3
    "hostload:",  # criterion 6
    "port:",      # criterion 7
    "buildid:",   # criterion 8
)


def known_exclusion_reason(reason: str) -> bool:
    """True if `reason` matches a criterion in config/exclusions.md."""
    return reason in EXCLUSION_REASONS or reason.startswith(EXCLUSION_REASON_PREFIXES)


# The pre-registered cell registry. `cell` is validated against it because a
# typo'd id is otherwise SILENT: it files the run under its own
# results/<typo>/, and report.main() walks every directory, so the typo renders
# as a SEPARATE cell -- a duel's runs split across two tables and the
# pre-registered n >= 10 is then met by neither.
CELLS_YAML = Path(__file__).resolve().parent.parent / "config" / "cells.yaml"


@lru_cache(maxsize=None)
def known_cell_ids(cells_yaml: str = "") -> frozenset[str]:
    """Cell ids declared in the pre-registered cells.yaml (default: CELLS_YAML)."""
    doc = yaml.safe_load(Path(cells_yaml or CELLS_YAML).read_text())
    return frozenset(str(c["id"]) for c in doc["cells"])


@dataclass(frozen=True)
class RunManifest:
    cell: str
    approach: str
    map_name: str
    run_index: int
    arm: str
    harness_git_sha: str
    patches_git_sha: str
    transport: dict
    carla_version: str
    autoware_image: str
    started_at_ns: int
    excluded: bool = False
    exclusion_reason: str = ""
    placement: dict = dataclasses.field(default_factory=dict)

    def validate(self) -> list[str]:
        errs = []
        if self.cell not in known_cell_ids():
            errs.append(f"cell {self.cell!r} is not registered in {CELLS_YAML.name}")
        if self.approach not in APPROACHES:
            errs.append(f"approach must be one of {APPROACHES}")
        if self.arm not in ARMS:
            errs.append(f"arm must be one of {ARMS}")
        missing = [k for k in TRANSPORT_KEYS if k not in self.transport]
        if missing:
            errs.append(f"transport missing keys: {missing}")
        if self.excluded and not self.exclusion_reason:
            errs.append("excluded runs require exclusion_reason")
        elif self.excluded and not known_exclusion_reason(self.exclusion_reason):
            errs.append(
                f"exclusion_reason {self.exclusion_reason!r} does not match any "
                "criterion in config/exclusions.md"
            )
        missing_p = [k for k in PLACEMENT_KEYS if k not in self.placement]
        if missing_p:
            errs.append(f"placement missing keys: {missing_p}")
        if self.approach in UE_APPROACHES and "engine_build_id" not in self.placement:
            errs.append("placement.engine_build_id required for UE-based approaches")
        return errs

    def save(self, path: Path) -> None:
        """Write the manifest, REFUSING to write an invalid one.

        The manifest is written BEFORE its run starts, so this is the last
        point at which a bad cell/arm/transport costs nothing to catch. Writing
        it anyway puts the error into a results tree that every downstream
        consumer treats as data.
        """
        errs = self.validate()
        if errs:
            raise ValueError(f"invalid run manifest: {'; '.join(errs)}")
        Path(path).write_text(json.dumps(dataclasses.asdict(self), indent=2))


def load_manifest(path: Path) -> RunManifest:
    return RunManifest(**json.loads(Path(path).read_text()))
