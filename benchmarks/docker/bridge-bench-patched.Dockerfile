# Cells E and E-opt: the pinned `bridge-bench` image plus the two committed
# python-bridge patches. Cell E0 does NOT use this image -- it measures the
# as-shipped bridge, so it keeps `bridge-bench:latest` (pins.yaml
# bridge_bench). Building the patched variant as a separate tag, rather than
# patching in place, is what keeps that distinction auditable.
#
# The base is CUDA-dependent (pins.yaml autoware_universe_devel is the
# universe-devel-CUDA variant), so every `docker run` of THIS image needs
# `--gpus all` and nvidia-container-toolkit too.
#
# Build (context = benchmarks/, so the patch directory is reachable):
#
#   docker build -f benchmarks/docker/bridge-bench-patched.Dockerfile \
#     -t bridge-bench-patched:latest benchmarks/
#
# The patches carry container-ABSOLUTE paths in their headers and are applied
# with `patch -p0` from `/`, so the same files are addressed no matter what
# the build's working directory is.
FROM bridge-bench:latest
COPY patches/python-bridge/0001-lidar-is-dense.patch /tmp/patches/
COPY patches/python-bridge/0002-sensor-config-harmonized.patch /tmp/patches/
# --forward makes an already-applied patch a hard failure rather than an
# interactive reverse-apply prompt, so a rebuild on top of an already-patched
# base fails loudly instead of quietly un-patching the image.
RUN cd / \
  && patch -p0 --batch --forward </tmp/patches/0001-lidar-is-dense.patch \
  && patch -p0 --batch --forward </tmp/patches/0002-sensor-config-harmonized.patch \
  && rm -rf /tmp/patches
# Byte-compiled copies of the patched module. `patch` rewrites the source with
# a fresh mtime, so CPython would invalidate and recompile them on import
# anyway; purging them removes any dependence on that being true (a container
# whose clock or filesystem timestamps behave unexpectedly must not silently
# import the UNPATCHED create_cloud).
RUN find /opt/autoware/lib/python3.10/site-packages/autoware_carla_interface \
  -type d -name __pycache__ -prune -exec rm -rf {} +
# Fail the BUILD, not the run, if either patch did not take effect. Both greps
# are on the substantive lines, not on the patch files.
RUN grep -q 'is_dense=True' \
  /opt/autoware/lib/python3.10/site-packages/autoware_carla_interface/modules/carla_utils.py \
  && grep -q 'topic_suffix: /pointcloud_raw_ex' \
  /opt/autoware/share/autoware_carla_interface/config/sensor_mapping.yaml \
  && grep -q '"/sensing/lidar/top/pointcloud_raw_ex"' \
  /opt/autoware/share/carla_sensor_kit_launch/launch/pointcloud_preprocessor.launch.py
