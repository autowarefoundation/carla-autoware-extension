# benchmarks

## Purpose

This directory holds the reproducible measurement harness for the
three-approach CARLA↔Autoware integration evaluation described in the
project's design spec, "Three-Approach CARLA↔Autoware Integration
Evaluation Design". It exists to turn that spec's claims (C1–C3) into
pre-registered, regenerable evidence rather than one-off numbers.

## Data contract

A future `bench_observer` must emit the following files for every run:

| File                 | Columns / schema                                                                | Notes                                                                                             |
| -------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `observer.csv`       | `topic,header_stamp_ns,arrival_system_ns,arrival_steady_ns,clock_ns,size_bytes` | `clock_ns` is the latest `/clock` value seen at arrival; `-1` before the first clock is received. |
| `clock.csv`          | `clock_ns,arrival_system_ns`                                                    | One row per `/clock` receipt.                                                                     |
| `published_time.csv` | `topic,source_header_ns,published_ns`                                           |                                                                                                   |
| `resources.csv`      | `sample_system_ns,process,cpu_pct,rss_bytes`                                    |                                                                                                   |
| `manifest.json`      | the `RunManifest` schema implemented in `benchmarks/analysis/manifest.py`       |                                                                                                   |

Results are laid out on disk as:

```text
benchmarks/results/<cell>/run-<NNN>/{manifest.json,observer.csv,clock.csv,published_time.csv,resources.csv}
```

## Patch policy

> No changes to any approach's data-path, conversion, or transport code.
> Sensor-parameter, launch-parameter, and scenario-script edits are
> permitted, are the minimum possible, and are committed as reviewable
> patches under `benchmarks/patches/<approach>/` with full diffs
> reproduced in the report appendix.

## Cell matrix

`benchmarks/config/cells.yaml` is the pre-registered workload matrix. Each
entry's `id` (e.g. `A`, `B`, `E0`, `CAL-rmw`) is the label a measurement run
is filed under — it is what `run.sh <cell>` takes as its argument and what
`benchmarks/results/<cell>/` is named after.

`benchmarks/config/exclusions.md` is the pre-registered set of criteria
under which a run may be marked `excluded: true`; it may not be edited
after the first P3 measurement run.

## Pre-registration

The git history of this directory is the pre-registration record: metric
definitions (`benchmarks/analysis/`), equivalence margins
(`benchmarks/config/margins.yaml`), and the exclusion criteria above are
all committed before the first measurement run. Each result's
`manifest.json` records `harness_git_sha`, so any result can be tied back
to the exact analysis code that scored it.

## How to run

The analysis modules live in `benchmarks/analysis/` (manifest schema,
clock fit, CSV loading, cadence, latency, stats/margins, ceiling
evaluation). The intended entry point for rendering a per-cell report is
`python3 -m benchmarks.report <results_dir>`.
