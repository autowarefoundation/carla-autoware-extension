# python-bridge launch recipe (Task 13 bring-up)

This is a launch-recipe writeup, not a source diff. No Autoware source or launch file is edited by
anything here — every fix below is a `ros2 launch` command-line argument choice, made against the
stock `autoware_carla_interface` / `autoware_launch` packages in `bridge-bench:latest`. It exists as a
reviewable artifact for the map-correctness bug found while smoke-testing the stock Python-bridge
approach (Task 13); full findings, evidence, and the still-open drive-gate result live in
`task-13-report.md` (outside this repo, under the plan's `.superpowers/sdd/` tree).

## The stock candidate command — WRONG

```bash
ros2 launch autoware_launch e2e_simulator.launch.xml \
  map_path:=/autoware_map/town10 vehicle_model:=sample_vehicle \
  sensor_model:=carla_sensor_kit simulator_type:=carla rviz:=false
```

This command has two independent bugs.

### Bug 1 — silently drives Town01 instead of Town10HD_Opt

`autoware_carla_interface.launch.xml` declares `carla_map` with `default="Town01"`.
`e2e_simulator.launch.xml`'s `<group ... if="simulator_type == carla">` includes it with
`<include file="$(find-pkg-share autoware_carla_interface)/autoware_carla_interface.launch.xml"/>` —
**zero arguments passed through**. There is no top-level `carla_map` arg on `e2e_simulator.launch.xml`
to forward it with. `carla_autoware.py:82` then unconditionally calls
`client.load_world(self.carla_map)` on startup. The net effect: `map_path:=/autoware_map/town10` is
silently discarded, and the simulator ends up running Town01 while the rest of the launch line makes it
look like Town10HD_Opt is in use — no warning, no error.

Live evidence (this pass, `carla.Client` queried immediately after running the stock command above):

```text
$ python3 -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(10.0); print(c.get_world().get_map().name)"
current map: Carla/Maps/Town01
```

### Bug 2 — crashes on a CPU-only image before perception even starts

`tier4_perception_launch/launch/obstacle_segmentation/ground_segmentation/ground_segmentation.launch.py`
unconditionally declares a launch argument whose _default value_ resolves
`FindPackageShare("autoware_ground_segmentation_cuda")`, regardless of whether the CUDA node is ever
selected (`use_cuda_ground_segmentation` defaults to `false`). `DeclareLaunchArgument.execute()`
resolves that default eagerly, at declare-time — so on a CPU-only image where
`autoware_ground_segmentation_cuda` isn't ament-registered, the whole launch tree aborts immediately:

```text
[ERROR] [launch]: Caught exception in launch (see debug for traceback): "package 'autoware_ground_segmentation_cuda' not found, searching: ['/opt/autoware', '/opt/ros/humble']"
```

Workaround (CPU-only base image): `perception:=false` on `e2e_simulator.launch.xml` skips the whole
perception module and avoids the crash — but this has a downstream consequence (a structural
`autonomous`-mode-availability conflict, superseded below by the pin update, see "What is still
unproven").

**Update:** this bug is now avoided at the root, not worked around, by pinning `bridge-bench` to the
CUDA-enabled Autoware base image instead of switching `perception:=false`. See "Pin update" below.

## Pin update — CUDA-enabled Autoware base required

`benchmarks/pins.yaml`'s `autoware_universe_devel.digest` now points at
`ghcr.io/autowarefoundation/autoware:universe-devel-cuda`
(`sha256:5c22369a312f1cd8a03fb65b30c1ab542919c2c7a2cbd18e799956daef3ae8ee`, the multi-arch manifest-list
digest, same digest kind as the previous pin) instead of the CPU-only `universe-devel` variant. This is
an environment/pin change only — `benchmarks/docker/bridge-bench.Dockerfile` needed no edit, since it
already parameterizes the base image via `ARG BASE`.

With the CUDA base, `autoware_ground_segmentation_cuda` actually resolves:

```text
$ docker run --rm bridge-bench:latest bash -lc \
  "source /opt/autoware/setup.bash 2>/dev/null || source /opt/ros/humble/setup.bash; \
   ros2 pkg prefix autoware_ground_segmentation_cuda"
/opt/autoware
```

...which means `perception:=false` is **no longer required** to avoid Bug 2 — the corrected invocation
below leaves perception at its default (on) and drops the flag. Note this pin makes the image
GPU-dependent: `docker run` needs `--gpus all` (nvidia-container-toolkit) from this point on.

## The corrected invocation

```bash
# stage 1 — bridge only, launched separately so its own carla_map default can be overridden
ros2 launch autoware_carla_interface autoware_carla_interface.launch.xml \
  carla_map:=Town10HD_Opt host:=localhost port:=2000 sensor_kit_name:=carla_sensor_kit_description

# stage 2 — rest of the stack; simulator_type:=awsim so it does not auto-include a second,
# conflicting bridge instance with the wrong default map. perception left at its default (ON) —
# this requires the CUDA-pinned image and --gpus all on the container.
ros2 launch autoware_launch e2e_simulator.launch.xml \
  map_path:=/autoware_map/town10 vehicle_model:=sample_vehicle \
  sensor_model:=carla_sensor_kit simulator_type:=awsim \
  sensing:=true rviz:=false
```

`sensing:=true` is load-bearing: an earlier attempt at this recipe used `sensing:=false` (reasoning
that the bridge already publishes raw sensor topics directly), which broke the
GNSS -> EKF -> `/localization/kinematic_state` chain (EKF never activated, GNSS topic looked silent).
With `sensing:=true`, `/sensing/gnss/pose_with_covariance` publishes at ~20 Hz, EKF activates, and
`/localization/kinematic_state` publishes real fused pose at ~16 Hz — confirmed live, see
`task-13-report.md`.

Live evidence that the corrected recipe stays on the right map (this pass):

```text
$ python3 -c "import carla; c=carla.Client('localhost',2000); c.set_timeout(10.0); print(c.get_world().get_map().name)"
current map: Carla/Maps/Town10HD_Opt
```

## What is still unproven

The drive gate (goal + engage + >=30 s of monotonic ego motion) has still not passed. Two blockers have
now been found and worked past in sequence, each one revealing the next:

1. **(Superseded by the pin update above.)** With `perception:=false`, route planning succeeded
   (`/api/routing/set_route_points` → `success: true`, route reaches `state: SET`), but
   `/api/operation_mode/change_to_autonomous` consistently failed with "The target mode is not
   available" — the `autonomous` operation-mode availability gate unconditionally requires perception
   `objects`/`pointcloud` health checks that `perception:=false` can never satisfy.
2. **(Current blocker, found after the CUDA-base pin.)** With `perception:=true` on the CUDA-pinned
   image, the launch tree now crashes even earlier — before reaching operation-mode diagnostics at all
   — because the `lidar_centerpoint` perception node's launch args reference
   `~/autoware_data/lidar_centerpoint/centerpoint_tiny_ml_package.param.yaml`, and `~/autoware_data`
   (the ML model/weights directory for the full perception stack) does not exist in the `bridge-bench`
   image. It is not baked into any upstream Autoware Docker image; it is fetched separately via a
   documented Ansible playbook (`ansible-playbook autoware.dev_env.download_artifacts`) that downloads
   77 separate model files (yabloc, bevfusion, CenterPoint, traffic-light classifiers, YOLOX, ...) —
   a multi-GB, unbounded-duration operation that was out of scope for this pass (pin change only) and
   was not attempted. See `task-13-report.md`'s "CUDA-base pass" follow-up section for full evidence.

Net effect: the CUDA-base pin genuinely fixes what it was meant to fix (Bug 2, and the
operation-mode-availability conflict it caused), but the drive gate remains blocked one step further
down the chain, on missing perception model data rather than a missing package.
