"""Companion spawn runner for the CARLA/Autoware native ROS 2 interop demo.

Scaffolding placeholder (Task 16 of the M3 extension workstream). The runner
is planned to become a declarative CARLA-client-API spawner that reads
`carla_sensor_kit_description/config/sensor_kit_calibration.yaml` as the
single source of truth for sensor placement, owns the synchronous tick loop,
ego/sensor spawn, and per-map MGRS metadata — see the roadmap design doc
(Phase 3, "Companion runner + map metadata") for the full scope. No runtime
logic lives here yet; later M3 tasks populate this package incrementally.
"""
