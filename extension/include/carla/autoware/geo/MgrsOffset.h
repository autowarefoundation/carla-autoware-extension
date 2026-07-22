#pragma once

// CARLA world (left-handed, centimetres) <-> MGRS-local (right-handed, metres)
// transforms for GNSS pose synthesis. This is the C++ mirror of the verified
// scripts/phase_b/verify_mgrs_handedness.py -- the affine map is
// BYTE-IDENTICAL to world_to_mgrs_local there, pinned against the
// Nishi-Shinjuku lanelet2 map (docs/mgrs-handedness.md: median residual 0.009 m
// across the map, single Y negation, X/Z not flipped). Kept as a reusable
// public transform (under include/, like messages/) because the extension
// publisher AND any future consumer share exactly one definition.
//
// CONVERTER_OFFSET = (81655.73, 50137.43, 42.49998) m -- MGRS 54SUE local frame,
// from autoware_lanelet2_to_opendrive conf/map/nishishinjuku.yaml `offset:`.
//
// UNITS: the extension .so observes a UE FTransform, which is native
// CENTIMETRES, so the /100 below is correct at this layer. (The CARLA PythonAPI
// instead reports metres -- a different layer; do NOT reuse this for PythonAPI
// values without an x100. See the verifier's docstring.)

#include <tuple>

namespace carla {
namespace autoware {

// CARLA world transform (cm, left-handed) -> MGRS-local pose (m, right-handed).
// The ONLY flipped axis is Y (left-handed -> right-handed); X and Z are pure
// translations by the converter offset.
inline std::tuple<double, double, double> world_to_mgrs_local(double x_cm, double y_cm,
                                                              double z_cm) {
  constexpr double kOffsetX = 81655.73;
  constexpr double kOffsetY = 50137.43;
  constexpr double kOffsetZ = 42.49998;
  return {kOffsetX + x_cm / 100.0,
          kOffsetY - y_cm / 100.0,  // Y flip: left-handed -> right-handed
          kOffsetZ + z_cm / 100.0};
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
