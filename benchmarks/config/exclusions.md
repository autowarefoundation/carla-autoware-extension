# Pre-registered run-exclusion criteria

A run may be marked `excluded: true` in its manifest ONLY for:

1. Process crash (CARLA server, bridge, Autoware container, or observer
   exits abnormally) — reason `crash:<process>`.
2. M5 validation-gate failure at bring-up (the cell had not yet passed
   its localization/goal sanity check) — reason `gate:<detail>`.
3. Harness defect discovered and fixed (the run was measured with a
   broken observer/injector) — reason `harness:<commit>`.
4. Sim-clock stall: the clock watchdog observed no `/clock` advance for
   > 5 s wall while the run was armed — reason `stall:<detail>`. (The
   python-bridge tick-stall defect, P1 Verdict 1; also covers any
   approach's frozen-clock hang.)
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

Excluded runs remain in `benchmarks/results/` with their data; nothing is
deleted. Any exclusion not matching 1-8 invalidates the campaign for that
cell and requires a fresh cell. These criteria may not be edited after
the first P3 measurement run.
