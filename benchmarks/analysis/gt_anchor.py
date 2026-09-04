"""Per-approach `base_link` anchor: where each approach puts `base_link`
relative to the CARLA actor origin, and how to convert between them.

WHY THIS EXISTS (Task 13). `Actor.get_transform()` -- the only ground truth the
harness has -- reports the CARLA actor's own pivot. Every Autoware pose it is
compared against (`/localization/pose_estimator/pose`,
`/localization/kinematic_state`) is `base_link`. Those two are the same point
only when the approach ATTACHES ITS SENSORS at raw `base_link` coordinates
relative to the actor, because Autoware's TF chain carries no vehicle term and
NDT therefore back-solves

    base_link = sensor_world - TF(base_link -> sensor)

which lands on whatever reference the sensors were attached to. So each approach
DEFINES where `base_link` sits, and the raw actor pose is a correct `base_link`
ground truth EXACTLY when the approach pins `base_link` to the actor origin.

There is no single "actor origin -> base_link" transform to apply campaign-wide.
The offset is a property of the APPROACH's spawn code, and it is 0 for one of
them. Applying a uniform ~1.4 m correction would silently BREAK the approach
that is already correct -- measured: it would turn cell A's G1 from 0.089 m into
~1.4 m and invalidate promoted G1/G2 evidence.

MEASURED CONSEQUENCE, and why this module is not a theory. Cell B seeds and
scores against an actor-origin pose while its NDT solves for a rear-axle
`base_link`, so `benchmarks/results/B/run-006` recorded
`/localization/initialize` SUCCEEDING and NDT locking, then failed the seed's
1.0 m convergence check at 1.4879 m -- a frame gap, not a localization error.

THE COUNTERINTUITIVE DIRECTION, recorded so nobody "fixes" the wrong side:
**cell B follows Autoware's real URDF convention** (`base_link` at the rear-axle
ground projection) and **cell A deliberately deviates** from it, pinning
`base_link` to the CARLA vehicle origin (`runner/kit.py`'s module docstring says
so outright). A's ground truth is correct because of that deviation, not in
spite of it. The extension REMOVED an earlier `+wheelbase/2` shift --
`base_link_to_vehicle_center`, `SAMPLE_VEHICLE_WHEELBASE`, `ego_wheelbase()`
were all deleted -- after it caused a **1.44 m G1 near-miss**
(`docs/e2e-report.md` issue #6). Cell B is reproducing that same defect class
inside the fork, on the other side of the comparison.

NOT DERIVED FROM THE VEHICLE MODEL, on purpose. An earlier plan was to compute
the offset from the wheelbase. That is wrong for BOTH non-zero approaches:

    approach        offset used      its source                       2.79/2
    extension        0.0             no shift at all                  n/a
    tier4-native    -1.39706787      a hardcoded literal, "as         1.395
                                     measured in Unreal Editor"
    python-bridge   -1.425           bridge DEFAULT_WHEELBASE 2.850/2 1.395

Neither matches `sample_vehicle`'s 2.79 m wheelbase, and the bridge's 2.850
disagreement with 2.79 is itself a registered E-family confound
(benchmarks/README.md) -- a real sensor-placement inconsistency, NOT an
arithmetic error to round away. The offset must come from each approach's own
spawn code, which is what the constants below cite and what
`verify_registered_offset` re-checks against that source.
"""

from __future__ import annotations

import math
import re

# Per-approach longitudinal offset, in the ego BODY frame (+X forward), from the
# CARLA actor origin to where that approach puts `base_link`. Keyed by
# benchmarks/config/cells.yaml's `approach`.
#
# Each value is quoted from the approach's own source of truth, and
# verify_registered_offset() re-reads that source so a drifting literal fails
# loudly instead of reintroducing a silent ~1.4 m bias.
GT_ANCHOR_OFFSET_M: dict[str, float] = {
    # runner/spawn.py attaches every sensor directly to the ego at
    # sensor_in_base_link() coordinates with NO vehicle term, so base_link IS
    # the actor origin. runner/kit.py: "for THIS integration base_link is
    # pinned to the CARLA vehicle ORIGIN ... with NO longitudinal shift ...
    # the offset cancels in the NDT<->GT comparison".
    "extension": 0.0,
    # PythonAPI/examples/autoware_demo.py spawns a `util.actor.empty` at
    # ROS2.Transform(x=-1.39706787) attached to the ego and hangs the whole
    # sensor rig off THAT: "Transformation between vehicle pivot and projection
    # of the rear axis on the ground (base link) as measured in Unreal Editor".
    "tier4-native": -1.39706787,
    # The bridge's CoordinateTransformer subtracts DEFAULT_WHEELBASE / 2 =
    # 2.850 / 2 when it places sensors. benchmarks/README.md measured the
    # resulting GT gap at -1.4045 m over 1179 static pairs on results/E/run-006;
    # -1.425 is where the bridge PUTS base_link, which is what NDT solves for,
    # so it is the correct anchor and the 0.021 m residual is the actor pivot's
    # real placement versus mid-wheelbase.
    "python-bridge": -1.425,
    # Calibration cells run no Autoware stack and compute no pose_error.
    "calibration": 0.0,
}

# What verify_registered_offset() greps, per approach. The regex is anchored on
# the ASSIGNMENT rather than the bare number so a coincidental match elsewhere
# in the file cannot satisfy it.
_DEMO_OFFSET_RE = re.compile(
    r"pivot_to_base_link_transform\s*=\s*ROS2\.Transform\(\s*x\s*=\s*(-?\d+(?:\.\d+)?)"
)
_BRIDGE_WHEELBASE_RE = re.compile(r"DEFAULT_WHEELBASE\s*[:=]\s*(-?\d+(?:\.\d+)?)")
# The symbols whose REMOVAL is what makes the extension's 0.0 correct. If any
# comes back, base_link stops being the actor origin and A's ground truth is
# silently biased again -- docs/e2e-report.md issue #6, the 1.44 m near-miss.
EXTENSION_FORBIDDEN_SYMBOLS = (
    "base_link_to_vehicle_center",
    "SAMPLE_VEHICLE_WHEELBASE",
    "ego_wheelbase",
)

# Floating-point tolerance for the source-vs-registry comparison. Tight enough
# that a real edit fails, loose enough to survive decimal reformatting.
OFFSET_MATCH_TOL_M = 1e-9


def offset_for_approach(approach: str) -> float:
    """Registered body-frame offset for `approach`.

    Raises rather than defaulting to 0.0: an unknown approach silently
    anchored at the actor origin is exactly the ~1.4 m bias this module
    exists to prevent, and it would look like a localization result.
    """
    try:
        return GT_ANCHOR_OFFSET_M[approach]
    except KeyError:
        raise KeyError(
            f"no registered base_link anchor offset for approach {approach!r}; "
            f"known: {sorted(GT_ANCHOR_OFFSET_M)}. Register it from that "
            "approach's own spawn code (see this module's docstring) -- do NOT "
            "default it to 0.0, which would anchor its ground truth at the "
            "CARLA actor origin and bias every pose_error by the difference."
        ) from None


def base_link_from_actor_origin(
    x_m: float, y_m: float, yaw_rad: float, offset_m: float
) -> tuple[float, float]:
    """Map-frame actor-origin XY -> map-frame `base_link` XY.

    `offset_m` is a BODY-frame longitudinal offset, so it must be ROTATED into
    the map frame, not subtracted as a map-frame constant. That is the whole
    reason "just state the offset beside every number" was rejected: the term
    is constant in the body frame and rotates with yaw in the map frame, so a
    stated constant is correct at exactly one heading and wrong everywhere else
    -- and the committed Town10 route turns 169.4 degrees.

    `yaw_rad` is the MAP-frame yaw (`carla_to_map_yaw`, i.e. -yaw_carla). Body
    +X is forward in both frames -- the CARLA/map relation is a Y flip, which
    leaves the longitudinal axis alone -- so forward in the map frame is
    (cos yaw, sin yaw).

    Pure, and an exact identity when `offset_m` is 0.0, which is what makes the
    extension cells a provable no-op.
    """
    if offset_m == 0.0:
        return x_m, y_m
    return x_m + offset_m * math.cos(yaw_rad), y_m + offset_m * math.sin(yaw_rad)


def offset_from_demo_source(text: str) -> float:
    """The tier4 demo's own pivot->base_link literal, read from its source."""
    match = _DEMO_OFFSET_RE.search(text)
    if match is None:
        raise ValueError(
            "autoware_demo.py has no `pivot_to_base_link_transform = "
            "ROS2.Transform(x=...)` assignment. Either the demo no longer "
            "shifts base_link (in which case tier4-native's registered offset "
            "must become 0.0) or the spawn code was restructured; do not guess."
        )
    return float(match.group(1))


def offset_from_bridge_source(text: str) -> float:
    """The bridge's base_link offset, derived from its DEFAULT_WHEELBASE.

    Halved here because the bridge itself applies wheelbase/2, and negated
    because the shift moves base_link BACKWARDS from the vehicle centre.
    """
    match = _BRIDGE_WHEELBASE_RE.search(text)
    if match is None:
        raise ValueError(
            "no DEFAULT_WHEELBASE assignment found in the bridge source; the "
            "python-bridge anchor cannot be verified against it."
        )
    return -float(match.group(1)) / 2.0


def verify_registered_offset(approach: str, source_text: str) -> None:
    """Assert the registry still matches the approach's own source.

    Called from the cell launchers at bring-up so a fork edit, a new patch that
    parameterizes the spawn offset, or a bridge wheelbase change ABORTS the run
    instead of silently re-biasing every pose_error by the difference.
    """
    registered = offset_for_approach(approach)
    if approach == "extension":
        found = [s for s in EXTENSION_FORBIDDEN_SYMBOLS if s in source_text]
        if found:
            raise ValueError(
                f"the extension's base_link anchor is registered as 0.0 because "
                f"runner/ applies NO vehicle-frame shift, but {found} is back in "
                "the source. That is docs/e2e-report.md issue #6 -- it biased "
                "NDT's base_link by wheelbase/2 and cost a 1.44 m G1 near-miss. "
                "Either the shift is compensated in Autoware's TF (then register "
                "the new offset here) or it must be removed again."
            )
        return
    if approach == "tier4-native":
        actual = offset_from_demo_source(source_text)
    elif approach == "python-bridge":
        actual = offset_from_bridge_source(source_text)
    else:
        return
    if abs(actual - registered) > OFFSET_MATCH_TOL_M:
        raise ValueError(
            f"approach {approach!r} registers a base_link anchor offset of "
            f"{registered!r} m but its own source now says {actual!r} m. A run "
            "on a stale value biases every pose_error AND the localization seed "
            "by the difference, which reads as a localization result rather than "
            "a harness error. Update GT_ANCHOR_OFFSET_M deliberately, with the "
            "new source line quoted."
        )
