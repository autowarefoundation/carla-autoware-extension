# The Town10 route as it stood BEFORE the 2026-07-29 re-pick

`Town10HD_Opt.yaml` here is the committed Town10 route as it was before Task 11
re-picked it: goal `(-101.021, 55.014)` at station 438.9 m, 211 polyline nodes.
The live tree's `benchmarks/config/routes/Town10HD_Opt.yaml` is now the
re-picked 258.9 m route, so without this copy the pre-re-pick route's geometry
is not in the tree at any commit a reader is looking at.

## Why it is retained

`benchmarks/README.md`'s route-difficulty confound table compares the two
routes, and its "previously read 438.9 m / 250.9 m (57.2%) / 233.0° / 33.5 m"
row is a quantitative claim. It was originally cited to
`reports/task-15-town10/pick_route.log`, which is **`.gitignore`d** — the same
defect that made the rung-2 G1 summary unverifiable, one directory over. With
this file the old row is recomputable from the tree instead.

## Recomputing the old row

```bash
python3 - <<'PY'
import math, yaml
from benchmarks.scripts.pick_route import APPROACH_SKIP_NODES
d = yaml.safe_load(open(
    "benchmarks/evidence/route-town10-pre-repick/Town10HD_Opt.yaml"))
poly, g = d["polyline"], (d["goal"]["x"], d["goal"]["y"])
cum = [0.0]
for a, b in zip(poly, poly[1:]):
    cum.append(cum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
turn = 0.0
for a, b, c in zip(poly, poly[1:], poly[2:]):
    h1 = math.atan2(b[1] - a[1], b[0] - a[0])
    h2 = math.atan2(c[1] - b[1], c[0] - b[0])
    turn += abs(math.degrees((h2 - h1 + math.pi) % (2 * math.pi) - math.pi))
sep = math.hypot(poly[0][0] - g[0], poly[0][1] - g[1])
appr = min(math.hypot(x - g[0], y - g[1]) for x, y in poly[:-APPROACH_SKIP_NODES])
print(f"length {cum[-1]:.1f} m  turn {turn:.1f} deg  sep {sep:.1f} m "
      f"({100 * sep / cum[-1]:.1f}%)  closest prior approach {appr:.3f} m")
PY
```

Verified before promotion to print `length 438.9 m  turn 233.0 deg  sep 250.9 m
(57.2%)  closest prior approach 33.468 m` — which is where the table's 33.5 m
comes from, and which confirms the tool's own
`APPROACH_SKIP_NODES = 15` rule rather than the 5-node variant that briefly
produced a non-comparable 11.3 m for the re-picked row.

## What this is NOT

It is not the route any current run drives, and nothing reads it. It is retained
purely so a superseded quantitative claim stays checkable. Do not point
`ROUTE_FILE` at it.
