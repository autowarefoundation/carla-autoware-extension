#!/usr/bin/env python3
"""Report which readiness input `behavior_path_planner` was still missing when
a cell-B run ended, from that run's own launch log.

This is the DIRECT measurement of the planner's map receipt that Task 4b had to
label NOT TESTED. `behavior_path_planner.isDataReady()` emits one throttled
`waiting for <input>` line per cycle for the FIRST input it finds missing, in a
fixed order (scenario_topic -> route -> map -> ... -> operation_mode), so:

  * the planner's LAST such line names the input it was still missing;
  * `waiting for map` appearing at all proves the planner had scenario AND
    route and did NOT have the map -- the node's own report that `map_ptr_` was
    null, not an inference from another endpoint;
  * `waiting for map` count 0 with a LATER line naming something past `map`
    proves the planner DID have the map.

It cannot be run on a static arm: no route is ever set, so the planner stops at
the first check and never evaluates the map. That is exactly why this
measurement needed closed-loop runs.

usage: planner_readiness.py <tier4-autoware.log> [...]
"""

import re
import sys

TS = re.compile(r"\[(1[0-9]{9}\.[0-9]+)\]")
PLANNER = "behavior_planning.behavior_path_planner]:"
PUBLISH = "Succeeded to load lanelet2_map"


def stamp(line):
    m = TS.search(line)
    return float(m.group(1)) if m else None


for path in sys.argv[1:]:
    lines = open(path, errors="ignore").read().split("\n")
    stamps = [t for t in (stamp(x) for x in lines) if t]
    if not stamps:
        print(f"{path}: no timestamps")
        continue
    end = stamps[-1]
    publish = next((stamp(x) for x in lines if PUBLISH in x), None)

    counts = {}
    last_msg = last_t = None
    for line in lines:
        if PLANNER not in line:
            continue
        msg = line.split(PLANNER, 1)[1].strip()
        if not msg.startswith("waiting for "):
            continue
        counts[msg] = counts.get(msg, 0) + 1
        last_msg, last_t = msg, stamp(line)

    blocked_on = last_msg[len("waiting for ") :] if last_msg else "-"
    print(
        "%s\n  publish=%s teardown=%.3f\n  blocked_on=%s last=%s counts=%s"
        % (
            path,
            ("%.3f" % publish) if publish else "-",
            end,
            blocked_on,
            ("%+.1fs vs teardown" % (last_t - end)) if last_t else "-",
            {k[len("waiting for ") :]: v for k, v in counts.items()},
        )
    )
