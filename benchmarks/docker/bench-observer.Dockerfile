# Observer image: the pinned Autoware base + rmw_cyclonedds + the
# bench_observer package built against that base's message set.
# Build (context = benchmarks/):
#   docker build -f docker/bench-observer.Dockerfile \
#     --build-arg BASE=<pins.yaml digest> -t bench-observer:<label> .
ARG BASE
FROM ${BASE}
RUN apt-get update && apt-get install -y --no-install-recommends \
      ros-humble-rmw-cyclonedds-cpp && rm -rf /var/lib/apt/lists/*
COPY observer /ws/src/bench_observer
RUN . /opt/ros/humble/setup.sh && \
    if [ -f /opt/autoware/setup.bash ]; then . /opt/autoware/setup.bash; fi && \
    cd /ws && colcon build --packages-select bench_observer
