# Pre-registered run-exclusion criteria

A run may be marked `excluded: true` in its manifest ONLY for:

1. Process crash, or the cell failing to come up at all (CARLA server,
   bridge, Autoware container, or observer exits abnormally; or
   `cells/<approach>.sh up` itself fails — a readiness-probe timeout or a
   launcher prerequisite refusal, neither of which is necessarily an
   abnormal exit) — reason `crash:<process>`, with `crash:cell-launch`
   for the launcher case.
2. Bring-up gate failure: a pre-registered readiness check that must pass
   before the scoring window starts did not — the M5 localization/goal
   sanity check (`gate:arm-failed`), the gated control command never
   flowing after a successful engage (`gate:control_cmd-silent`), or a
   required bring-up helper failing to start, e.g. the clear-road
   perception injector (`gate:injector-failed`) — reason `gate:<detail>`.
3. Harness defect discovered and fixed (the run was measured with a
   broken observer/injector) — reason `harness:<commit>`.
4. Sim-clock stall: the clock watchdog observed no `/clock` advance for
   > 5 s wall while the run was armed — reason `stall:clock`. (The
   > python-bridge tick-stall defect, P1 Verdict 1; also covers any
   > approach's frozen-clock hang.) This is a FROZEN clock; a clock that
   > keeps advancing, only slowly, is criterion 10, not this one.
5. Nishi-Shinjuku first run after a CARLA boot is a warm-up and is
   ALWAYS discarded (cold-start lag spikes to 107 s, P1 Verdict 5) —
   reason `warmup:nishi`. The warm-up run spawns the exact sensor suite.
6. Host 1-min loadavg ≥ 8 at preflight (localization degrades under
   load, P1 Verdict 1) — the run is not started; if discovered mid-run,
   reason `hostload:<loadavg>`.
7. CARLA RPC port collision (surfaces as SIGABRT in LoadMap, not a bind
   error) — reason `port:<port>`.
8. Engine BuildId mismatch against pins.yaml `engine.build_id`
   discovered after run start (an engine relink invalidates every
   sharing tree) — reason `buildid:<tree>`.
9. Harness recorder crash: one of the harness's own background
   recorders (the resource sampler, GT collector, or clock watchdog —
   not the simulator or the stack under test) exits during start-up,
   before it has recorded anything usable — reason `crash:<recorder>`
   (`crash:sampler`, `crash:collect_gt`, `crash:clock_watchdog`). Kept
   distinct from criterion 1: a harness recorder dying says nothing
   about whether the approach under test crashed.
10. Unpaced scoring window capped: the unpaced arm's sim clock advanced
    throughout the run but did not reach the pre-registered window
    length within the wall-clock budget (`UNPACED_WALL_CAP` × the
    window) — the sim was merely slow, not frozen, which is exactly the
    case criterion 4's watchdog is designed to never fire on (a
    clock-less cell would otherwise be excluded every run, silently) —
    reason `stall:unpaced-window-cap`.

Excluded runs remain in `benchmarks/results/` with their data; nothing is
deleted. Any exclusion not matching 1-10 invalidates the campaign for that
cell and requires a fresh cell. These criteria may not be edited after
the first P3 measurement run.
