#!/usr/bin/env python3
"""Recompute, from a filed cell-B run's launch log, how long the in-stack
component_state_monitor took to receive /map/vector_map.

The monitor (`/system/topic_state_monitor_vector_map`) is an EARLY-JOINING
transient_local subscriber: it is loaded before `map.lanelet2_map_loader`
publishes. `logging_diag_graph` prints the not-OK subtree every ~3 s, so the
first printed block that does NOT list `/autoware/map/topic_rate_check/
vector_map` is the first evidence that the monitor has the map. The number
reported is therefore an upper bound with ~3 s granularity, not a receipt
timestamp -- stated because this campaign has been bitten by a bound quoted as
a measurement.

usage: monitor_convergence.py <tier4-autoware.log> [...]
"""
import re
import sys

TS = re.compile(r"\[(1[0-9]{9}\.[0-9]+)\]")
BLOCK = "The target mode is not available for the following reasons"
ENTRY = "topic_rate_check/vector_map"
PUBLISH = "Succeeded to load lanelet2_map"

for path in sys.argv[1:]:
    lines = open(path, errors="ignore").read().split("\n")
    publish = None
    for line in lines:
        if PUBLISH in line:
            m = TS.search(line)
            if m:
                publish = float(m.group(1))
            break
    blocks, cur = [], None
    for line in lines:
        if BLOCK in line:
            m = TS.search(line)
            cur = [float(m.group(1)) if m else None, None]
            blocks.append(cur)
        elif cur is not None and ENTRY in line:
            cur[1] = line.strip().split()[-1]
    not_ok = [b for b in blocks if b[1]]
    ok = [b for b in blocks if not b[1]]
    print(
        "%s publish=%.3f diag_blocks=%d not_ok_blocks=%d "
        "last_not_ok=%s first_ok=%s"
        % (
            path,
            publish if publish else float("nan"),
            len(blocks),
            len(not_ok),
            ("+%.1fs" % (not_ok[-1][0] - publish)) if not_ok and publish else "-",
            ("+%.1fs" % (ok[0][0] - publish)) if ok and publish else "NEVER",
        )
    )
