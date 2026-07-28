#!/usr/bin/env python3
"""Sim-clock stall watchdog: pure file polling over the observer's clock.csv.

Pre-registered exclusion criterion 4 (benchmarks/config/exclusions.md) says a
run whose sim clock stops advancing for > 5 s while armed is excluded with
reason `stall:<detail>`. Detecting that needs a monitor that keeps working
when the very thing it is watching has wedged, which rules out anything that
subscribes to `/clock` itself: the python-bridge tick stall (P1 Verdict 1)
freezes every `use_sim_time` node in the graph, so a ROS-based watchdog would
freeze alongside the run it is meant to indict.

So this watches the FILE. `clock.csv` gains one row per `/clock` receipt with
a SYSTEM-clock arrival stamp (benchmarks/README.md), which keeps advancing
whatever the sim does. Two failures collapse into one check against that
stamp:

* the sim clock froze -- the observer stops receiving, no new rows, the
  newest arrival ages past `--stall-s`;
* the observer died -- the file stops growing, same signal.

Being RMW-free also means one implementation covers every cell, including the
python-bridge cells whose RMW is not the harness's.

On a stall it writes `--marker` (one line of detail, kept in the run
directory as the evidence behind the exclusion) and exits 3. It never exits 0
on its own: run.sh kills it at teardown, and a clean SIGTERM exit is a
successful watch.
"""

from __future__ import annotations

import argparse
import csv
import signal
import sys
import time
from pathlib import Path

EXIT_STALLED = 3
EXIT_TERMINATED = 0

ARRIVAL_COLUMN = "arrival_system_ns"


def newest_arrival_ns(path: Path | str) -> int | None:
    """Newest parsable `arrival_system_ns` in clock.csv, or None.

    None covers "file not created yet", "header only" and "the last row is a
    partial write" identically: in every case nothing has been confirmed to
    arrive, which is what the caller acts on. Rows are scanned rather than
    tail-seeked because clock.csv is one short row per /clock receipt and the
    poll period is seconds -- correctness over cleverness on a file that only
    ever grows.
    """
    try:
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
    except (FileNotFoundError, OSError):
        return None
    for row in reversed(rows):
        try:
            return int(row[ARRIVAL_COLUMN])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def stall_reason(
    newest_ns: int | None, now_ns: int, started_ns: int, stall_s: float, grace_s: float
) -> str | None:
    """The stall detail to record, or None while the run is still healthy.

    The grace period covers bring-up: the observer container, the sim and the
    first `/clock` publication are all still starting, so "no rows yet" is
    normal for tens of seconds and must not be reported as a stall.
    """
    if (now_ns - started_ns) < grace_s * 1e9:
        return None
    if newest_ns is None:
        return f"no /clock rows at all after {grace_s:.0f} s grace"
    age_s = (now_ns - newest_ns) / 1e9
    if age_s > stall_s:
        return f"newest /clock arrival is {age_s:.1f} s old (limit {stall_s:.1f} s)"
    return None


def watch(
    clock_csv: Path | str,
    marker: Path | str,
    stall_s: float,
    grace_s: float,
    poll_s: float = 1.0,
    now_ns=time.time_ns,
    sleep=time.sleep,
    max_polls: int | None = None,
    should_stop=lambda: False,
) -> int:
    """Poll until a stall is detected (writes `marker`, returns 3) or the
    caller stops us (returns 0). `now_ns`/`sleep`/`max_polls` are injected so
    the stall rule is testable in milliseconds instead of in real seconds."""
    started_ns = now_ns()
    polls = 0
    while not should_stop():
        detail = stall_reason(newest_arrival_ns(clock_csv), now_ns(), started_ns, stall_s, grace_s)
        if detail is not None:
            marker_path = Path(marker)
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text(detail + "\n")
            print(f"CLOCK STALL: {detail}", file=sys.stderr)
            return EXIT_STALLED
        polls += 1
        if max_polls is not None and polls >= max_polls:
            return EXIT_TERMINATED
        sleep(poll_s)
    return EXIT_TERMINATED


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--clock-csv", required=True, help="the run's clock.csv")
    p.add_argument("--marker", required=True, help="file written on a stall")
    p.add_argument("--stall-s", type=float, default=5.0, help="max /clock gap")
    p.add_argument("--grace-s", type=float, default=30.0, help="bring-up grace")
    p.add_argument("--poll-s", type=float, default=1.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    stopping = {"stop": False}

    def _stop(_signum, _frame):
        stopping["stop"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    return watch(
        args.clock_csv,
        args.marker,
        args.stall_s,
        args.grace_s,
        args.poll_s,
        should_stop=lambda: stopping["stop"],
    )


if __name__ == "__main__":
    sys.exit(main())
