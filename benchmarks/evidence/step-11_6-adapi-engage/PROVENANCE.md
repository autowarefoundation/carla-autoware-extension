# Step 11.6 — the AD-API vs legacy engage discriminator

Captures for the finding that AD-API `change_to_autonomous` fails on cell A —
a cell that demonstrably drives — while the legacy `/autoware/engage` publish
succeeds in the same state. Promoted because that finding now carries a
consequence in committed code and config: `gate_g2_closed_loop.sh`'s header
states the gated control topic publishes at ~19.9 Hz even in STOP mode, and
cell E's closed-loop degradation rests on the verdict being a harness defect
rather than a property of the bridge.

All three captures are from one stack, in this order, with no reboot between:
localization reseeded to 0.03 m, trajectory live at 10 Hz, dummy perception
injected, MRM suppressed, route SET via the same AD-API.

| File | What it shows |
| --- | --- |
| `adapi_change_to_autonomous.log` | `arm_and_goal.py` on the AD-API path: `set_route_points` succeeds, then `change_to_autonomous` **refuses for 60 s**, ~30 retries, every one "The target mode is not available. Please check the diagnostics." Exit 2. |
| `legacy_autoware_engage.log` | The legacy `/autoware/engage` publish **seconds later, same state**: `mode: 2` (AUTONOMOUS), `is_autoware_control_enabled: true` — and `is_autonomous_mode_available: false` **while it is driving**, which is the decisive detail: the difference is which interface consults that flag, not the state. |
| `gated_control_cmd.log` | The gated output under the legacy path: `msgs=281 rate=20.07 Hz`, velocity command `+4.170` m/s on **281/281** samples. |

## Why the rate alone was not sufficient

Measured pre-engage in the same session, the gated
`/control/command/control_cmd` publishes at **19.93 Hz carrying zero-velocity
commands** while operation mode is STOP. So a ~20 Hz rate does not demonstrate
command authority — only the content does, which is why
`gated_control_cmd.log` records the velocity distribution and not just the
rate. That is the claim `gate_g2_closed_loop.sh`'s header now carries.

## What is NOT here

- **The pre-engage 19.93 Hz measurement itself.** It was an interactive rclpy
  probe whose output went to the session transcript only. The 20.07 Hz
  post-engage figure beside it IS retained, above.
- **The root cause's own capture.** `/vehicle/status/control_mode` reporting
  `4` (MANUAL) — the reason the transition manager never marks autonomous
  available — was read interactively and not written to a file.
- **Ground-truth motion.** The ego's 4.12–4.32 m/s progress was printed by an
  ad-hoc host-side loop, not retained. `gated_control_cmd.log`'s commanded
  +4.170 m/s is the retained half.

None of these gaps is reconstructed. Where the record cites them it says so.
