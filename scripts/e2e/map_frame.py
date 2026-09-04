"""CARLA <-> Autoware map-frame conversion used by the gates.

Upstream's run_carla_autoware.sh converts CARLA poses to the Autoware map
frame as x_map = x, y_map = -y, yaw_map = -yaw (a single Y flip between the
left-handed CARLA world and the right-handed lanelet2 map), and treats
Autoware's base_link as the rear axle, 1.425 m behind the CARLA actor origin.
Maps with a Local projector have origin (0, 0, 0); MGRS maps add the
converter offset (Nishi-Shinjuku: autoware_lanelet2_to_opendrive
conf/map/nishishinjuku.yaml).
"""

from __future__ import annotations

import math

NISHISHINJUKU_ORIGIN = (81655.73, 50137.43, 42.49998)  # metres, MGRS 54SUE local frame
REAR_AXLE_OFFSET_M = 1.425  # sample_vehicle, same constant as run_carla_autoware.sh GATE1


def carla_to_map(
    x_m: float, y_m: float, z_m: float = 0.0, origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
) -> tuple[float, float, float]:
    ox, oy, oz = origin
    return (ox + x_m, oy - y_m, oz + z_m)


def carla_yaw_to_map(yaw_deg: float) -> float:
    return -yaw_deg


def rear_axle(
    x_m: float, y_m: float, yaw_deg: float, offset_m: float = REAR_AXLE_OFFSET_M
) -> tuple[float, float]:
    """CARLA-frame position of Autoware's base_link (rear axle) for an actor at (x, y, yaw)."""
    r = math.radians(yaw_deg)
    return (x_m - offset_m * math.cos(r), y_m - offset_m * math.sin(r))


def parse_origin(text: str) -> tuple[float, float, float]:
    if not text:
        return (0.0, 0.0, 0.0)
    ox, oy, oz = (float(v) for v in text.split(","))
    return (ox, oy, oz)
