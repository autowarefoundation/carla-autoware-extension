# Bridge benchmark image: universe-devel (pinned digest) + the gezp CARLA
# 0.9.15 Python client wheel baked in, so runs never depend on GitHub.
ARG BASE
FROM ${BASE}
COPY vendor/*.whl /tmp/wheels/
RUN pip install --no-deps /tmp/wheels/*.whl && rm -rf /tmp/wheels
