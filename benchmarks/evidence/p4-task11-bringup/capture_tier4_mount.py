"""Read-only capture of cell B-cyc's LiDAR attach pose, for raycast_baseline --mount.

Attaches a SECOND, read-only CARLA client while the measured run is live: it only
calls world.get_actors() and reads transforms. It NEVER ticks and NEVER calls
apply_settings, so it cannot perturb the sync-mode run that owns the world.

Emits the six numbers `raycast_baseline.py --mount X_M Y_M Z_M ROLL_DEG PITCH_DEG
YAW_DEG` expects: the LiDAR's attach pose ON THE EGO, i.e. lidar-world composed
through the inverse of the EGO actor's world transform. The tier4 rig attaches as
ego -> base_link -> sensor_kit -> lidar (collect_gt.is_descendant_of), so the whole
chain is printed too.
"""

import math
import sys

import carla

MAX_ATTACH_DEPTH = 8


def chain_to_root(actor):
    chain = [actor]
    node = getattr(actor, "parent", None)
    for _ in range(MAX_ATTACH_DEPTH):
        if node is None:
            break
        chain.append(node)
        node = getattr(node, "parent", None)
    return chain


def is_descendant_of(actor, ancestor_id, max_depth=MAX_ATTACH_DEPTH):
    node = getattr(actor, "parent", None)
    for _ in range(max_depth):
        if node is None:
            return False
        if node.id == ancestor_id:
            return True
        node = getattr(node, "parent", None)
    return False


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def decompose(m):
    """CARLA-convention (x,y,z) metres and (roll,pitch,yaw) degrees from a 4x4."""
    x, y, z = m[0][3], m[1][3], m[2][3]
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, m[2][0]))))
    yaw = math.degrees(math.atan2(m[1][0], m[0][0]))
    roll = math.degrees(math.atan2(-m[2][1], m[2][2]))
    return (x, y, z), (roll, pitch, yaw)


def recompose(loc, rot):
    """Rebuild the 4x4 from CARLA angles, to prove the decomposition round-trips."""
    roll, pitch, yaw = (math.radians(v) for v in rot)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    return [
        [cp * cy, cy * sp * sr - sy * cr, -cy * sp * cr - sy * sr, loc[0]],
        [cp * sy, sy * sp * sr + cy * cr, -sy * sp * cr + cy * sr, loc[1]],
        [sp, -cp * sr, cp * cr, loc[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def fmt(t):
    return (
        f"loc=({t.location.x:.6f}, {t.location.y:.6f}, {t.location.z:.6f}) "
        f"rot=(roll {t.rotation.roll:.6f}, pitch {t.rotation.pitch:.6f}, yaw {t.rotation.yaw:.6f})"
    )


def main():
    client = carla.Client("localhost", 2000)
    client.set_timeout(30.0)
    world = client.get_world()
    # MEASURED 2026-08-03 on this very run: a freshly-connected client's
    # get_actors() returns an EMPTY list until it has received one episode
    # snapshot. In sync mode nothing arrives on its own, so wait for the tick
    # the run's own 20 Hz driver produces. Passive -- this never ticks.
    snap = world.wait_for_tick(10.0)
    print(f"synced on frame {snap.frame}")
    actors = world.get_actors()

    egos = [
        a
        for a in actors.filter("vehicle.*")
        if a.attributes.get("role_name") in ("ego", "ego_vehicle", "hero")
    ]
    if not egos:
        print("CAPTURE FAIL: no ego vehicle found", file=sys.stderr)
        return 2
    ego = egos[0]
    print(f"ego: id={ego.id} type={ego.type_id} role={ego.attributes.get('role_name')}")
    print(f"ego world transform: {fmt(ego.get_transform())}")

    lidars = [a for a in actors.filter("sensor.lidar.*") if is_descendant_of(a, ego.id)]
    if not lidars:
        print("CAPTURE FAIL: no sensor.lidar.* in the ego's attach tree", file=sys.stderr)
        return 3

    ego_inv = ego.get_transform().get_inverse_matrix()

    for lidar in lidars:
        print("=" * 72)
        print(f"lidar: id={lidar.id} type={lidar.type_id}")
        print("  attributes:")
        for k in sorted(lidar.attributes):
            print(f"    {k} = {lidar.attributes[k]}")
        print("  attach chain (leaf -> root), each actor's WORLD transform:")
        for node in chain_to_root(lidar):
            role = node.attributes.get("role_name", "-")
            print(f"    id={node.id} type={node.type_id} role={role}")
            print(f"      {fmt(node.get_transform())}")

        rel = matmul(ego_inv, lidar.get_transform().get_matrix())
        loc, rot = decompose(rel)
        back = recompose(loc, rot)
        resid = max(abs(back[i][j] - rel[i][j]) for i in range(3) for j in range(4))
        print("  RELATIVE TO THE EGO ACTOR (inverse(ego_world) * lidar_world):")
        print(f"    location_m  = ({loc[0]:.6f}, {loc[1]:.6f}, {loc[2]:.6f})")
        print(f"    rotation_deg= (roll {rot[0]:.6f}, pitch {rot[1]:.6f}, yaw {rot[2]:.6f})")
        print(f"    decomposition round-trip residual = {resid:.3e}")
        print(
            "    --mount "
            f"{loc[0]:.6f} {loc[1]:.6f} {loc[2]:.6f} {rot[0]:.6f} {rot[1]:.6f} {rot[2]:.6f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
