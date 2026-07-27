"""Run manifest: one JSON per run, written before the run starts."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

APPROACHES = ("extension", "python-bridge", "tier4-native", "calibration")
ARMS = ("static", "closed-loop", "ablation", "unpaced")
TRANSPORT_KEYS = ("rmw", "shm_enabled", "dds_profile_sha256")


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
        path.write_text(json.dumps(dataclasses.asdict(self), indent=2))


def load_manifest(path: Path) -> RunManifest:
    return RunManifest(**json.loads(Path(path).read_text()))
