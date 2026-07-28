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
