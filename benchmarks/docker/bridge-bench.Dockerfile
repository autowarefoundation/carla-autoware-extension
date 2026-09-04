# Bridge benchmark image: autoware:universe-devel-CUDA (pinned by digest as
# benchmarks/pins.yaml autoware_universe_devel, passed in as BASE) + the gezp
# CARLA 0.9.15 Python client wheel baked in, so runs never depend on GitHub.
# The CUDA base makes this image GPU-dependent: run it with `--gpus all`.
ARG BASE
FROM ${BASE}
COPY vendor/*.whl /tmp/wheels/
RUN pip install --no-deps /tmp/wheels/*.whl && rm -rf /tmp/wheels
