"""Companion spawn runner for the CARLA/Autoware native ROS 2 interop demo.

A declarative CARLA-client-API spawner that reads the sensor-kit calibration
YAML (``sensor_kit_calibration.yaml`` / ``sensors_calibration.yaml`` under
``runner/config``) as the single source of truth for sensor placement, and owns
ego/sensor spawn, the per-map MGRS metadata, and the synchronous tick loop. The
submodules are ``kit`` (kit YAML + frame math), ``spawn`` (blueprint/attribute
construction + attach), and ``loop`` (the tick loop); ``__main__`` wires them
into the CLI.
"""
