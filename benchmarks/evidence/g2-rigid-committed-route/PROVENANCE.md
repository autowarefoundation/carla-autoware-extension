# G2 on the rigid bundles — what is retained, and what is NOT

The two rigid-bundle G2 runs on the original 438.9 m Town10 route are the
measurements that established the closed-loop arm was not viable there. Their
retention is UNEVEN, and this file states which is which so no reader has to
guess.

| Run | Bundle | Closest approach | Retained here? |
| --- | --- | --- | --- |
| `dy = -0.475` | `town10_pcd_shifted` | **142.599 m** | The gate's own output, `g2_gate_output.log` — the number and `dist_rows=1198`, but NOT the distance series |
| `dy = -0.607` | `town10_pcd_refit` | **142.398 m** | **NOT RETAINED** |

## Why, precisely

Both runs predate `gate_g2_closed_loop.sh`'s per-run retention, when the gate
wrote a fixed `/tmp/g2_dist.txt` that the next invocation overwrote. So:

- **142.599 m is attributable but not recomputable.** `g2_gate_output.log` is
  the gate's verbatim stdout, including the engage step, the gated-control
  liveness capture at 19.96–19.97 Hz, `dist_rows=1198` and the
  `closest_approach=142.599 m tol=1.0 m -> FAIL` verdict line. What it does not
  contain is the 1198-sample series behind that minimum, so the number can be
  read back but not re-derived.
- **142.398 m is not recomputable at all.** It came from an ad-hoc host-side
  monitoring loop written during the session, whose output went to the
  transcript and was never written to a file. Nothing is reconstructed to cover
  the gap.

Neither figure should be cited as recomputable from this tree. The claim they
support — that the ego halts ~292 m along the route at the same place on BOTH
rigid registrations, ~0.2 m apart in closest approach — rests on these two
numbers and therefore inherits their status.

The equivalent runs on the regenerated bundle DO have full series, because they
were taken after the retention fix: see `../g2-regen-committed-route/` (1.929 m)
and `../g2-regen-repicked-route/` (0.244 m).

## The NDT-score mechanism is also not retained

The score-threshold chain observed live on these runs (`ndt_scan_matcher`
scoring below its 2.3 acceptance threshold, the EKF rejecting the pose, MRM
stopping the vehicle) came from container-side launch logs. Those containers
have been removed and the logs went with them, so the mechanism is recorded in
`benchmarks/README.md` as the observed explanation and explicitly not as
evidence. An earlier revision of the record cited a breach count from those
logs; it was withdrawn for exactly this reason.
