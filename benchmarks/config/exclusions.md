# Pre-registered run-exclusion criteria

A run may be marked `excluded: true` in its manifest ONLY for:

1. Process crash (CARLA server, bridge, Autoware container, or observer
   exits abnormally) — reason `crash:<process>`.
2. M5 validation-gate failure at bring-up (the cell had not yet passed
   its localization/goal sanity check) — reason `gate:<detail>`.
3. Harness defect discovered and fixed (the run was measured with a
   broken observer/injector) — reason `harness:<commit>`.

Excluded runs remain in `benchmarks/results/` with their data; nothing is
deleted. Any exclusion not matching 1-3 invalidates the campaign for that
cell and requires a fresh cell. These criteria may not be edited after
the first P3 measurement run.
