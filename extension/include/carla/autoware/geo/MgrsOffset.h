#pragma once

// CARLA world (left-handed, centimetres) <-> MGRS-local (right-handed, metres)
// transforms for GNSS pose synthesis. This is the C++ mirror of the verified
// scripts/e2e/verify_mgrs_handedness.py -- the affine map is
// BYTE-IDENTICAL to world_to_mgrs_local there, pinned against the
// Nishi-Shinjuku lanelet2 map (docs/mgrs-handedness.md: median residual 0.009 m
// across the map, single Y negation, X/Z not flipped). Kept as a reusable
// public transform (under include/, like messages/) because the extension
// publisher AND any future consumer share exactly one definition.
//
// UNITS: the extension .so observes a UE FTransform, which is native
// CENTIMETRES, so the /100 below is correct at this layer. (The CARLA PythonAPI
// instead reports metres -- a different layer; do NOT reuse this for PythonAPI
// values without an x100. See the verifier's docstring.)
//
// PER-MAP OFFSET. Only the TRANSLATION is map-specific; the Y flip and the
// quaternion sign rule below are properties of the CARLA<->OpenDRIVE handedness
// boundary and are therefore the SAME for every map. The offset is selected at
// extension-load time from $CARLA_AUTOWARE_MAP (ExtensionInit.cpp); the frozen
// C ABI carries no map name, so an environment variable is the only channel.
// Unset selects Nishi-Shinjuku, so every pre-existing invocation is unchanged.

#include <cstring>
#include <tuple>

namespace carla {
namespace autoware {

// Converter offset, metres, in the Autoware `map` frame. Named "MGRS" for the
// Nishi-Shinjuku lineage, but the frame is whatever the map's
// map_projector_info.yaml declares -- MGRS-local for Nishi-Shinjuku, a plain
// Local frame for the CARLA town maps.
struct MapOffset {
  double x, y, z;
};

// Nishi-Shinjuku: MGRS 54SUE local frame, from autoware_lanelet2_to_opendrive
// conf/map/nishishinjuku.yaml `offset:`. Verified live (docs/mgrs-handedness.md:
// median residual 0.009 m across the map).
inline constexpr MapOffset kNishishinjukuOffset{81655.73, 50137.43, 42.49998};

// Town10HD_Opt: the autoware-contents Town10 lanelet2/pcd pair declares
// `projector_type: Local` and was exported from the SAME CARLA town, so the map
// frame IS the CARLA world frame up to the handedness flip -- the translation is
// exactly zero. Measured offline, not assumed: scripts/e2e/fit_map_offset.py
// fits the translation against the lanelet2 boundary polylines over 12084
// CARLA lane-boundary probes and reports (0,0) with a median residual of
// 0.000 m (mean 0.002 m, max 0.019 m); the no-flip hypothesis lands at 4.30 m.
inline constexpr MapOffset kTown10HdOptOffset{0.0, 0.0, 0.0};

// Historical default: an unset $CARLA_AUTOWARE_MAP keeps the Nishi-Shinjuku
// behaviour byte-identical.
inline constexpr MapOffset kDefaultMapOffset = kNishishinjukuOffset;

// Environment variable naming the active map. Its accepted values are the same
// map names scripts/e2e/run_e2e.sh passes to CARLA and to `runner --map`.
inline constexpr char kMapEnvVar[] = "CARLA_AUTOWARE_MAP";

struct NamedMapOffset {
  const char* name;
  MapOffset offset;
};

// THE table. Both the lookup below and the load-failure diagnostic in
// ExtensionInit.cpp iterate this one array, so adding a map is a single edit and
// the "known maps" the error lists can never drift from what actually resolves.
inline constexpr NamedMapOffset kMapOffsets[] = {
    {"NishishinjukuMap", kNishishinjukuOffset},
    {"Town10HD_Opt", kTown10HdOptOffset},
};

// Resolve a map name to its converter offset.
//
// A null or empty name selects kDefaultMapOffset (Nishi-Shinjuku). An UNKNOWN
// name returns false and leaves *out untouched -- the caller must fail the load
// rather than fall back, because silently publishing one map's offset on
// another map is exactly the failure this table exists to prevent (it would
// surface far downstream as NDT never converging, not as a config error).
inline bool map_offset_for(const char* map_name, MapOffset* out) {
  if (out == nullptr) {
    return false;
  }
  if (map_name == nullptr || map_name[0] == '\0') {
    *out = kDefaultMapOffset;
    return true;
  }
  for (const NamedMapOffset& entry : kMapOffsets) {
    if (std::strcmp(map_name, entry.name) == 0) {
      *out = entry.offset;
      return true;
    }
  }
  return false;
}

// CARLA world transform (cm, left-handed) -> map-local pose (m, right-handed).
// The ONLY flipped axis is Y (left-handed -> right-handed); X and Z are pure
// translations by the converter offset.
inline std::tuple<double, double, double> world_to_mgrs_local(
    double x_cm, double y_cm, double z_cm, const MapOffset& offset = kDefaultMapOffset) {
  return {offset.x + x_cm / 100.0,
          offset.y - y_cm / 100.0,  // Y flip: left-handed -> right-handed
          offset.z + z_cm / 100.0};
}

// Ego orientation quaternion: CARLA (left-handed) -> MGRS-local (right-handed).
//
// The position map is a mirror M = diag(1, -1, 1) (the Y flip above). A rotation
// R expressed in the CARLA frame becomes R' = M R M^-1 = M R M in the mirrored
// frame (M is an involution, M^2 = I). Because M is a reflection (det M = -1),
// conjugating a proper rotation by it keeps it proper (det R' = 1) but negates
// the rotation angle about the mirrored axis. Working that through for a unit
// quaternion q = (sin(t/2)*n, cos(t/2)):
//
//   R' = M R M  rotates by angle t about axis (det M) * M n = -M n
//              = -(nx, -ny, nz) = (-nx, ny, -nz),
//   so q' = (sin(t/2)*(-nx), sin(t/2)*ny, sin(t/2)*(-nz), cos(t/2))
//         = (-qx, qy, -qz, qw).
//
// Interpretation on the aircraft axes: roll (about X) and yaw (about Z) NEGATE,
// pitch (about Y, the mirror axis) is PRESERVED, w is unchanged. This is exactly
// the conjugation of the same Y-flip that the position transform applies, so the
// pose stays self-consistent. The sign rule is OWNED here and PINNED by the
// `quat.*` tests in test/test_gnss_pose.cpp (identity->identity, CARLA yaw +90
// -> MGRS yaw -90, pure pitch unchanged, pure roll negated); do not inline
// anonymous negations at the call site -- change the rule here or the tests
// catch it.
//
// NOTE: the live verification covered POSITION handedness only; this
// rotation mapping is pinned by the math tests above, not by a live measurement.
inline std::tuple<double, double, double, double> carla_quat_to_mgrs(double qx, double qy,
                                                                    double qz, double qw) {
  return {-qx, qy, -qz, qw};
}

}  // namespace autoware
}  // namespace carla
