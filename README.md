# carla-autoware-extension

E2E gates and Nishi-Shinjuku map assets for CARLA's **in-tree** Autoware layer
(`carla-simulator/carla`, branch `ue58-dev`).

> Status: the out-of-tree extension `.so` and the spawn runner this repository
> used to carry were superseded when upstream ported TIER IV's Autoware layer
> in-tree (2026-08-19..25). Their history is in git; see `docs/ue58/`.

## What is here

| Path                                                                 | Purpose                                                                                                                  |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `scripts/e2e/run_gates.sh`                                           | Runs G1 (NDT localization), G2 (closed-loop goal), G3 (rates) against a stack started by CARLA's `run_carla_autoware.sh` |
| `scripts/e2e/map_frame.py`, `collect_gt.py`, `measure_*.py`          | Unit-tested measurement helpers                                                                                          |
| `docs/ue58/`                                                         | Verification records against `ue58-dev`: bring-up, Town10HD reproduction, gate results, PR candidates                    |
| `docs/nishishinjuku-map.md`                                          | Provenance and frame of the Nishi-Shinjuku assets (not committed)                                                        |
| `docs/e2e-report.md`, `docs/g0-report.md`, `docs/mgrs-handedness.md` | Extension-era records, kept as history                                                                                   |

## Quick start

```bash
# 1. Start the stack with CARLA's own script (from the CARLA tree):
cd PythonAPI/examples/av_stacks/autoware
./run/run_carla_autoware.sh --mode classical --spawn-index 24 --goal "-1.16,28.37,0.16" --log-dir /tmp/run1
# 2. Measure it (from this repository):
CARLA_PYTHON=~/carla-venv/bin/python bash scripts/e2e/run_gates.sh --log-dir /tmp/run1 --goal "-1.16,28.37,0.16"
```

Thresholds: G1 max NDT error < 1.0 m, G2 base_link within 1.0 m of the goal,
G3 LiDAR at its configured rate ± 1 Hz and control_cmd 20 ± 5 Hz.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
