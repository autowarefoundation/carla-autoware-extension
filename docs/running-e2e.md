# Running the E2E gates (CARLA in-tree Autoware, `ue58-dev`)

This repository does not launch the stack any more — it only measures a stack
started by CARLA's own script. Two commands, from two different trees.

## Prerequisites

- CARLA `ue58-dev` built with `-DENABLE_ROS2=ON` (see CARLA's own
  `PythonAPI/examples/av_stacks/autoware/README.md` for the full build and
  bring-up), and the built client wheel installed somewhere reachable as
  `$CARLA_PYTHON` (e.g. `~/carla-venv/bin/python`).
- Docker with the NVIDIA container runtime — `run_carla_autoware.sh` probes
  `nvidia-smi` on the host and adds `--gpus all` to the containers it starts.
- Kernel UDP buffers raised: `net.core.rmem_max`/`wmem_max` to 64 MB
  (`run_carla_autoware.sh` checks this itself and prints the fix if it is
  too low — required for the LiDAR `PointCloud2` stream over reliable DDS
  writers) and `net.core.rmem_default` to 8 MB (a socket that does not
  explicitly request a larger receive buffer than the default is bounded by
  it regardless of `rmem_max`, which is what capped the LiDAR/camera topics
  at 2-2.6 Hz before the fix; see `docs/ue58/phase0-bringup.md`).

## 1. Start the stack (from the CARLA tree)

```bash
cd PythonAPI/examples/av_stacks/autoware
./run/run_carla_autoware.sh --mode classical --spawn-index 24 \
  --goal "-1.16,28.37,0.16" --log-dir /tmp/run1
```

That spawn/goal pair is the one CARLA's own README documents as reaching
ARRIVED on Town10HD.

## 2. Measure it (from this repository)

```bash
CARLA_PYTHON=~/carla-venv/bin/python bash scripts/e2e/run_gates.sh \
  --log-dir /tmp/run1 --goal "-1.16,28.37,0.16"
```

`--goal` is given in the **same CARLA coordinates** passed to
`run_carla_autoware.sh` in step 1 — `run_gates.sh` converts it internally
with `scripts/e2e/map_frame.py` (the same affine `run_carla_autoware.sh`
itself uses), so the two scripts can never disagree on the frame.

### Flags

| Flag                   | Default                               | Meaning                                                                                                                                                                                                                                                                                                  |
| ---------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--log-dir DIR`        | (required)                            | Same `--log-dir` given to `run_carla_autoware.sh`; `run_gates.sh` reads the running container's name from `DIR/carla_autoware.containers`                                                                                                                                                                |
| `--goal "X,Y,YAW"`     | (required)                            | CARLA coordinates, exactly as passed to `run_carla_autoware.sh`                                                                                                                                                                                                                                          |
| `--map-origin "X,Y,Z"` | none (Local-projector origin `0,0,0`) | Omit for Local-projector maps (e.g. Town10HD); Nishi-Shinjuku needs `81655.73,50137.43,42.49998` (see [nishishinjuku-map.md](nishishinjuku-map.md))                                                                                                                                                      |
| `--rpc-port N`         | `2000`                                | CARLA RPC port                                                                                                                                                                                                                                                                                           |
| `--domain-id N`        | `42`                                  | `ROS_DOMAIN_ID` used inside the Autoware container. This is `run_gates.sh`'s own default, not read from the shell environment — a developer's interactive shell may default `ROS_DOMAIN_ID` to something else (e.g. `123`), which is why every gate command sets it explicitly rather than inheriting it |
| `--lidar-hz N`         | `10`                                  | Expected `/sensing/lidar/top/pointcloud_raw_ex` rate (the sensor kit is configured `sensor_tick 0.1`)                                                                                                                                                                                                    |
| `--g2-window S`        | `300`                                 | G2 sampling window, seconds                                                                                                                                                                                                                                                                              |
| `--out DIR`            | `DIR/gates`                           | Output directory                                                                                                                                                                                                                                                                                         |

`CARLA_PYTHON` is an environment variable, not a flag: the gates that spawn
`scripts/e2e/collect_gt.py` (a CARLA PythonAPI client) run it as
`${CARLA_PYTHON:-python3}`, so set it to a Python with the CARLA wheel
installed unless that wheel is already on the default `python3`.

## Gate criteria

- **G1** (NDT localization): max NDT-vs-ground-truth XY error over the
  window < 1.0 m.
- **G2** (closed loop): closest approach to the goal < 1.0 m, measured on
  the `base_link` basis — the rear axle, i.e. the CARLA actor origin shifted
  back 1.425 m along the vehicle heading (the same constant
  `run_carla_autoware.sh`'s own GATE1 uses).
- **G3** (rates): `/control/command/control_cmd` at 20 ± 5 Hz and
  `/sensing/lidar/top/pointcloud_raw_ex` at 10 ± 1 Hz.

## Outputs

`run_gates.sh` writes into `--out` (default `<log-dir>/gates`):

- `g1_ndt.txt`, `g1_gt.txt` — G1's NDT pose and ground-truth series
- `g2_dist.txt` — G2's ego-to-goal distance series
- `g3_lidar_hz.txt`, `g3_control_hz.txt` — G3's raw `ros2 topic hz` output
- `gates.txt` — verdict lines only (e.g. `G1 ... -> PASS`)

`run_gates.sh` exits 0 only if every one of G1/G2/G3 produced at least one
verdict line in `gates.txt` and none of them reads `FAIL`. A gate that
crashed before it could score is named on stderr and counted as a failure —
it can never read as a silent pass.

## Teardown

From the CARLA tree, with the same `--log-dir`:

```bash
./run/stop_all.sh --log-dir /tmp/run1
```
