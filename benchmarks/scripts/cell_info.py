#!/usr/bin/env python3
"""Merged cell (+ optional sweep/camera class) descriptor, as JSON.

    python3 -m benchmarks.scripts.cell_info <cell-id> [--class <id>]

`benchmarks/config/cells.yaml` is the pre-registered workload matrix and the
only place a cell id is legitimate. `RunManifest.validate()` already refuses
an unregistered id, but that check fires at step 4 of `run.sh` -- after the
run directory has been named and preflight has run. This module is the same
typo-guard at the TOP of the pipeline: `run.sh` resolves the cell here first,
so `run.sh Q --arm static` dies in milliseconds naming `Q`, rather than after
a preflight that cleared /dev/shm for a cell that does not exist.

The printed object is the cells.yaml entry (`id`, `approach`, `carla`, `map`,
`mandatory`, `arms`) plus `sweep_arms`, and -- when `--class` is given -- the
class entry's own fields merged in at top level (`class_id`, `channels`,
`points_per_second`, or `cameras`/`width`/`height`/`fps`). Merging at top
level rather than nesting keeps the consumer side a single `jq -r .<key>`
in `run.sh`, and makes "did the class actually apply?" answerable by looking
for the key.

Both class lists in cells.yaml are searched (`sweep_classes` for M2's
LiDAR-load sweep, `camera_classes` for M4's camera-load arm): they are two
registrations of the same shape (`id` + `applies_to` + workload fields) and
a caller asking for `cam3` means exactly what a caller asking for `32ch`
means. A class whose `applies_to` does not list the cell is an error, not a
silent no-op -- `run.sh A --class cam1` on a cell the class was never
registered for would otherwise produce a run filed as if it had been.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

CELLS_YAML = Path(__file__).resolve().parent.parent / "config" / "cells.yaml"

# Class registries searched by --class, in order. Both use the same schema.
CLASS_LISTS = ("sweep_classes", "camera_classes")

# Keys consumed by the lookup itself; everything else on a class entry is a
# workload parameter and is merged into the output.
CLASS_META_KEYS = ("id", "applies_to")

EXIT_UNKNOWN_ID = 2


class UnknownIdError(ValueError):
    """An id (cell or class) that is not registered in cells.yaml."""


def load_cells_doc(path: Path | str | None = None) -> dict:
    return yaml.safe_load(Path(path or CELLS_YAML).read_text())


def cell_entry(doc: dict, cell_id: str) -> dict:
    for cell in doc.get("cells", []):
        if str(cell["id"]) == cell_id:
            return dict(cell)
    known = ", ".join(sorted(str(c["id"]) for c in doc.get("cells", [])))
    raise UnknownIdError(f"unknown cell {cell_id!r}; registered cells: {known}")


def class_entry(doc: dict, class_id: str) -> dict:
    for list_name in CLASS_LISTS:
        for entry in doc.get(list_name, []) or []:
            if str(entry["id"]) == class_id:
                return dict(entry)
    known = ", ".join(sorted(str(e["id"]) for n in CLASS_LISTS for e in (doc.get(n) or [])))
    raise UnknownIdError(f"unknown class {class_id!r}; registered classes: {known}")


def merge(doc: dict, cell_id: str, class_id: str | None = None) -> dict:
    """cells.yaml's entry for `cell_id`, with `class_id`'s fields merged in."""
    merged = cell_entry(doc, cell_id)
    merged["sweep_arms"] = list(doc.get("sweep_arms", []) or [])
    # Derived ONCE, here, because three separate places in run.sh need it and
    # a cell that answers it differently in any one of them is a silent
    # campaign defect. Concretely: a `carla: none` cell runs no simulator, so
    # nothing ever publishes /clock and clock.csv stays header-only by design.
    # Step 7 must therefore not start the clock watchdog (it would report "no
    # /clock rows at all" after its grace and mark EVERY run of that cell
    # excluded as stall:clock -- quietly, under a legitimate-looking
    # pre-registered reason), step 13 must not act on such a marker, and step
    # 14 cannot use the sim/wall clock fit the generic renderer needs.
    merged["has_sim_clock"] = str(merged.get("carla", "none")) != "none"
    if class_id:
        cls = class_entry(doc, class_id)
        applies_to = [str(c) for c in cls.get("applies_to", [])]
        if cell_id not in applies_to:
            raise UnknownIdError(
                f"class {class_id!r} is not registered for cell {cell_id!r} "
                f"(applies_to: {', '.join(applies_to) or 'none'})"
            )
        merged["class_id"] = str(cls["id"])
        for key, value in cls.items():
            if key not in CLASS_META_KEYS:
                merged[key] = value
    return merged


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Print a cells.yaml cell as JSON.")
    p.add_argument("cell", help="cell id registered in benchmarks/config/cells.yaml")
    p.add_argument(
        "--class",
        dest="class_id",
        default=None,
        metavar="ID",
        help="sweep_classes/camera_classes id whose fields are merged in",
    )
    p.add_argument("--cells-yaml", default=None, help="override cells.yaml (tests)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        merged = merge(load_cells_doc(args.cells_yaml), args.cell, args.class_id)
    except UnknownIdError as exc:
        print(f"CELL FAIL: {exc}", file=sys.stderr)
        return EXIT_UNKNOWN_ID
    print(json.dumps(merged, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
