#!/usr/bin/env python3
"""M3 resource sampler. One row per (sample, process); contract in
benchmarks/README.md. Process resolution re-runs every sample so
restarted PIDs are picked up. GPU per-process utilization comes from
`nvidia-smi pmon` when available, else -1; VRAM from
--query-compute-apps. Container entries sample cgroup v2 files.
The rtf column is written as -1 and filled post-run by finalize_rtf.py
(keeps the sampler free of any ROS dependency).

loadavg_1m is the one HOST-WIDE column: read once per sample cycle from
/proc/loadavg and stamped onto every process row of that cycle, so it
repeats across a sample_system_ns exactly as rtf does and is not
attributable to any process. It RECORDS in-run host contention; it does
not bound it (benchmarks/README.md, "Host load during a run is
unbounded")."""

from __future__ import annotations

import argparse
import csv
import os
import signal
import subprocess
import time
from pathlib import Path

import yaml

# resources.csv contract (benchmarks/README.md), also mirrored in
# benchmarks/analysis/bench_io.py's RESOURCE_INT_COLS/RESOURCE_FLOAT_COLS
# (+ RESOURCE_OPTIONAL_FLOAT_COLS for loadavg_1m).
#
# loadavg_1m was APPENDED (2026-07-30). Every run filed before that date
# carries the seven-column header and both readers cope -- but be precise
# about WHY, because the obvious explanation is wrong:
#
#   WHAT MAKES IT WORK IS NAME-BASED ACCESS, NOT POSITION. bench_io's
#   read_resources_csv goes through csv.DictReader, keyed by header NAME; and
#   finalize_rtf.py resolves header.index("sample_system_ns") /
#   header.index("rtf") out of the header it just read, then writes that same
#   header back. Neither depends on where a column sits, and no committed
#   consumer of resources.csv reads it positionally.
#
#   APPENDING LAST IS A LEGIBILITY CONVENTION, NOT A CORRECTNESS MECHANISM.
#   It keeps the pre-2026-07-30 header a strict PREFIX of this tuple, so a
#   diff of an already-filed run against a new one shows one ADDED column
#   rather than a shifted table -- which matters because those runs are
#   retained evidence that has to stay comparable by eye.
#
# So do NOT conclude that position is load-bearing: reordering would not break
# a reader and appending elsewhere would not either. Keep new columns at the
# end for the prefix property, not out of fear of the reader. The
# position-independence is pinned by test_finalize_rtf.py's shuffled-header
# test, so this comment is a checked claim rather than an assurance.
RESOURCE_COLUMNS = (
    "sample_system_ns",
    "process",
    "cpu_pct",
    "rss_bytes",
    "gpu_util_pct",
    "vram_bytes",
    "rtf",
    "loadavg_1m",
)

# Contract sentinel: "no GPU context" / "not yet resolvable". Also what
# this ROS-free sampler always writes for rtf -- finalize_rtf.py fills it --
# and what an unreadable /proc/loadavg writes for loadavg_1m.
NOT_APPLICABLE = -1

# cgroup v2 mount point for docker's systemd cgroup driver (spec: M3).
CGROUP_BASE = "/sys/fs/cgroup/system.slice"


# ---------------------------------------------------------------------------
# /proc CPU + RSS math -- pure, unit-tested against a fake --proc-root.
# ---------------------------------------------------------------------------


def read_pid_cpu_ticks(pid: int, proc_root: str) -> int:
    """utime+stime (clock ticks) for one PID from <proc_root>/<pid>/stat.

    The comm field (2nd, in parens) can itself contain spaces or
    parens, so the tail is split from the LAST ')' rather than by a
    naive whitespace split of the whole line.
    """
    with open(os.path.join(proc_root, str(pid), "stat")) as f:
        content = f.read()
    tail = content[content.rindex(")") + 1 :].split()
    # tail[0] = state (stat field 3); utime is field 14, stime field 15,
    # i.e. tail indices 11 and 12 once state/ppid/.../cmajflt occupy 0..10.
    return int(tail[11]) + int(tail[12])


def read_pid_rss_bytes(pid: int, proc_root: str, page_size: int) -> int:
    """Resident set size for one PID from <proc_root>/<pid>/statm."""
    with open(os.path.join(proc_root, str(pid), "statm")) as f:
        fields = f.read().split()
    return int(fields[1]) * page_size


def read_loadavg_1m(proc_root: str) -> float:
    """Host-wide 1-minute load average from <proc_root>/loadavg.

    FIELD 1, deliberately. `benchmarks/scripts/preflight.sh` gates on
    exactly this field (`awk '{print $1}' /proc/loadavg`, abort at >= 8),
    so the in-run series is on the same basis as the pre-run gate and the
    two are directly comparable; and Task 13's ad hoc 2 s sampling
    recorded the same field (mean 25.80, peak 50.05 on
    results/B/run-009), so this series is comparable with the figures
    already in the committed record. Fields 2 and 3 are the 5- and
    15-minute averages, which over a run of this length are dominated by
    load from BEFORE the run started -- the opposite of the question.
    Its own limitation, stated rather than glossed: the 1-minute figure
    is itself a ~60 s exponential average, so it records the SUSTAINED
    level and cannot resolve a sub-second spike (run-005 lost three rmw
    responses inside one 0.4 s window). "Was this run contended?" is the
    question it answers.

    HOST-WIDE, so it is read once per sample cycle and stamped onto every
    process row of that cycle -- the same shape as rtf -- and it is not
    attributable to any one process.

    An unreadable or malformed file returns the contract's -1 sentinel
    rather than raising: this is a background recorder, and killing it
    over one bad read would lose the whole M3 series for a live run. -1
    and not 0.0, because a real 0.0 would state that the host was idle,
    which is exactly the false reading this series exists to prevent.
    """
    try:
        with open(os.path.join(proc_root, "loadavg")) as f:
            return float(f.read().split()[0])
    except (FileNotFoundError, OSError, ValueError, IndexError):
        return float(NOT_APPLICABLE)


def compute_cpu_pct(prev_ticks: dict, curr_ticks: dict, interval_s: float, clk_tck: int) -> float:
    """Sum of Δ(utime+stime)/CLK_TCK/interval*100 over PIDs alive now.

    A PID absent from `prev_ticks` (freshly resolved this sample, e.g.
    a restarted process) contributes zero -- there is no earlier
    baseline to diff against yet; it starts contributing from the next
    sample onward.
    """
    if interval_s <= 0:
        raise ValueError("interval_s must be > 0")
    delta_ticks = sum(
        max(0, ticks - prev_ticks.get(pid, ticks)) for pid, ticks in curr_ticks.items()
    )
    return (delta_ticks / clk_tck) / interval_s * 100.0


def sample_pids_cpu_rss(pids, proc_root: str, page_size: int):
    """Current cpu ticks (per pid) + summed RSS for a PID list.

    A PID that exits between resolution (pgrep) and this read is
    skipped rather than raising -- a transient exit is not an error,
    and dropping it here also drops it from the next sample's delta
    baseline, which is the correct behaviour.
    """
    ticks = {}
    rss = 0
    for pid in pids:
        try:
            ticks[pid] = read_pid_cpu_ticks(pid, proc_root)
            rss += read_pid_rss_bytes(pid, proc_root, page_size)
        except (FileNotFoundError, ProcessLookupError, ValueError, OSError, IndexError):
            # IndexError covers a /proc/<pid>/stat or statm read that
            # raced a process exit and came back short (fewer fields
            # than expected) -- a transient exit, same as the other
            # exceptions here, must not end the whole sampling run.
            continue
    return ticks, rss


# ---------------------------------------------------------------------------
# cgroup v2 reads (containers) -- pure, unit-tested against fake files.
# ---------------------------------------------------------------------------


def cgroup_dir(container_id: str) -> str:
    return f"{CGROUP_BASE}/docker-{container_id}.scope/"


def read_cgroup_cpu_usec(cg_dir: str):
    try:
        with open(os.path.join(cg_dir, "cpu.stat")) as f:
            for line in f:
                key, _, val = line.partition(" ")
                if key == "usage_usec":
                    return int(val)
    except (FileNotFoundError, OSError, ValueError):
        return None
    return None


def read_cgroup_memory_current(cg_dir: str):
    try:
        with open(os.path.join(cg_dir, "memory.current")) as f:
            return int(f.read().strip())
    except (FileNotFoundError, OSError, ValueError):
        return None


def read_cgroup_pids(cg_dir: str) -> list:
    try:
        with open(os.path.join(cg_dir, "cgroup.procs")) as f:
            return [int(line) for line in f if line.strip()]
    except (FileNotFoundError, OSError, ValueError):
        return []


def compute_cgroup_cpu_pct(prev_usec, curr_usec, interval_s: float) -> float:
    """Δusage_usec/1e6/interval*100; 0.0 with no earlier baseline yet."""
    if prev_usec is None or curr_usec is None:
        return 0.0
    return (max(0, curr_usec - prev_usec) / 1e6) / interval_s * 100.0


def elapsed_since(prev_mono, now_mono: float, fallback_s: float) -> float:
    """Measured wall-clock delta (time.monotonic()) since a label's
    previous sample, not the nominal --interval.

    A sampling cycle can run long (N pgrep/docker calls plus two
    nvidia-smi calls, each with its own timeout), so the real gap
    between two successive reads for a label can exceed the nominal
    interval -- dividing CPU-time deltas by the unchanged nominal
    value would then systematically overstate cpu_pct, worst exactly
    when the host is most loaded. `prev_mono` is None only for a
    label's very first sample, where there is no prior tick baseline
    either: compute_cpu_pct/compute_cgroup_cpu_pct report 0% in that
    case regardless of the divisor, so `fallback_s` only needs to
    satisfy compute_cpu_pct's `interval_s > 0` check, not be accurate.
    """
    return (now_mono - prev_mono) if prev_mono is not None else fallback_s


# ---------------------------------------------------------------------------
# GPU aggregation over a PID list -- pure, unit-tested with plain dicts.
# ---------------------------------------------------------------------------


def gpu_totals_for_pids(pids, vram_map: dict, sm_map: dict):
    """Sum GPU vram/sm% across `pids` that appear in nvidia-smi's output.

    Returns the contract's -1 sentinel (not 0) when none of the pids
    have any GPU context at all: 0 would misreport "on GPU, using
    nothing" for a process that never touches the GPU. vram_bytes and
    gpu_util_pct are resolved independently (different nvidia-smi
    queries), per the brief.
    """
    vram_hits = [vram_map[p] for p in pids if p in vram_map]
    sm_hits = [sm_map[p] for p in pids if p in sm_map]
    vram = sum(vram_hits) if vram_hits else NOT_APPLICABLE
    sm = sum(sm_hits) if sm_hits else float(NOT_APPLICABLE)
    return sm, vram


# ---------------------------------------------------------------------------
# Row formatting -- pure; pins the resources.csv column order exactly.
# ---------------------------------------------------------------------------


def format_row(
    sample_system_ns, process, cpu_pct, rss_bytes, gpu_util_pct, vram_bytes, rtf, loadavg_1m
) -> list:
    """Row values in the resources.csv contract's exact column order."""
    return [
        sample_system_ns,
        process,
        cpu_pct,
        rss_bytes,
        gpu_util_pct,
        vram_bytes,
        rtf,
        loadavg_1m,
    ]


# ---------------------------------------------------------------------------
# Live resolution: pgrep / docker / nvidia-smi. Not unit-tested (thin
# subprocess wrappers); exercised live by the Step-4 smoke run.
# ---------------------------------------------------------------------------


def resolve_pids(pattern: str) -> list:
    """PIDs matching `pgrep -f <pattern>`; [] if pgrep is absent or no match."""
    try:
        proc = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True, timeout=5)
    except OSError:
        return []
    if proc.returncode not in (0, 1):  # 1 = no processes matched, not an error
        return []
    return [int(p) for p in proc.stdout.split()]


def resolve_container_id(name: str):
    try:
        proc = subprocess.run(
            ["docker", "inspect", "--format", "{{.Id}}", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    cid = proc.stdout.strip()
    return cid or None


def gpu_pid_vram_bytes() -> dict:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return {}
    if proc.returncode != 0:
        return {}
    out = {}
    for line in proc.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 2:
            continue
        try:
            out[int(parts[0])] = int(parts[1]) * 1024 * 1024
        except ValueError:
            continue
    return out


def gpu_pid_sm_pct() -> dict:
    try:
        proc = subprocess.run(
            ["nvidia-smi", "pmon", "-c", "1", "-s", "u"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return {}
    if proc.returncode != 0:
        return {}
    out = {}
    for line in proc.stdout.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            out[pid] = float(parts[3])
        except ValueError:
            pass  # "-" = no sm sample on this poll; leave pid unset -> -1
    return out


# ---------------------------------------------------------------------------
# Per-entry sampling: combines resolution + math for one process-map entry.
# ---------------------------------------------------------------------------


def sample_pattern_entry(
    entry, proc_root, page_size, clk_tck, elapsed_s, prev_ticks, vram_map, sm_map
):
    """`elapsed_s` is the MEASURED wall-clock gap since this label's
    previous sample (see elapsed_since), not the nominal --interval."""
    pids = resolve_pids(entry["pattern"])
    ticks, rss = sample_pids_cpu_rss(pids, proc_root, page_size)
    cpu = compute_cpu_pct(prev_ticks or {}, ticks, elapsed_s, clk_tck)
    sm, vram = gpu_totals_for_pids(pids, vram_map, sm_map)
    return cpu, rss, sm, vram, ticks


def sample_container_entry(entry, elapsed_s, prev_usec, vram_map, sm_map):
    """`elapsed_s` is the MEASURED wall-clock gap since this label's
    previous sample (see elapsed_since), not the nominal --interval."""
    cid = resolve_container_id(entry["container"])
    if cid is None:
        # Not running / docker unavailable this sample: report the same
        # zero-state a pattern matching no PIDs would, and drop any
        # stale usec baseline so a later restart does not diff against
        # a now-meaningless value.
        return 0.0, 0, float(NOT_APPLICABLE), NOT_APPLICABLE, None
    cg = cgroup_dir(cid)
    usec = read_cgroup_cpu_usec(cg)
    cpu = compute_cgroup_cpu_pct(prev_usec, usec, elapsed_s)
    mem = read_cgroup_memory_current(cg)
    pids = read_cgroup_pids(cg)
    sm, vram = gpu_totals_for_pids(pids, vram_map, sm_map)
    return cpu, (mem if mem is not None else 0), sm, vram, usec


# ---------------------------------------------------------------------------
# CLI / main loop
# ---------------------------------------------------------------------------


def load_process_map(path) -> list:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("processes", []) or []


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="M3 per-process resource sampler.")
    p.add_argument("--processes", required=True, type=Path, help="process map YAML")
    p.add_argument("--out", required=True, type=Path, help="resources.csv path")
    p.add_argument("--interval", type=float, default=1.0, help="sample period, seconds")
    p.add_argument(
        "--proc-root", default="/proc", help="/proc root (--proc-root makes the CPU math testable)"
    )
    return p.parse_args(argv)


def _sleep_until(target_monotonic: float, stop_flag: dict, chunk_s: float = 0.1) -> None:
    """Sleep in small chunks so SIGTERM is noticed within `chunk_s`,
    rather than waiting out a whole `time.sleep(interval)` (which
    CPython auto-retries across an EINTR from a handler that does not
    raise, per PEP 475)."""
    while not stop_flag["stop"]:
        remaining = target_monotonic - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(chunk_s, remaining))


def run(processes_path, out_path, interval_s: float, proc_root: str) -> None:
    entries = load_process_map(processes_path)
    page_size = os.sysconf("SC_PAGE_SIZE")
    clk_tck = os.sysconf("SC_CLK_TCK")

    stop_flag = {"stop": False}

    def _handle_sigterm(signum, frame):
        stop_flag["stop"] = True

    signal.signal(signal.SIGTERM, _handle_sigterm)

    prev_ticks: dict = {}  # label -> {pid: ticks}
    prev_usec: dict = {}  # label -> usage_usec
    prev_sample_mono: dict = {}  # label -> time.monotonic() of that label's previous read

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(RESOURCE_COLUMNS)
        f.flush()

        next_tick = time.monotonic()
        while not stop_flag["stop"]:
            now_ns = time.time_ns()
            vram_map = gpu_pid_vram_bytes()
            sm_map = gpu_pid_sm_pct()
            # Once per cycle, beside now_ns, because loadavg is a property of
            # the HOST at this sample instant and not of any process -- so it
            # repeats across the rows sharing this now_ns, exactly as rtf does.
            # Read AFTER the two nvidia-smi calls on purpose: those are the
            # cycle's own slowest step, and the figure a reader wants is the
            # load the sampled processes were actually running under.
            loadavg_1m = read_loadavg_1m(proc_root)

            for entry in entries:
                label = entry["label"]
                # Captured per label, right before that label's own
                # resolve+read, so cpu_pct divides by the REAL elapsed
                # time since this label's previous snapshot -- not the
                # nominal --interval, which a slow cycle (N pgrep/docker
                # calls + two nvidia-smi calls, each with its own
                # timeout) can overrun.
                sample_mono = time.monotonic()
                elapsed_s = elapsed_since(prev_sample_mono.get(label), sample_mono, interval_s)
                if "pattern" in entry:
                    cpu, rss, sm, vram, ticks = sample_pattern_entry(
                        entry,
                        proc_root,
                        page_size,
                        clk_tck,
                        elapsed_s,
                        prev_ticks.get(label),
                        vram_map,
                        sm_map,
                    )
                    prev_ticks[label] = ticks
                elif "container" in entry:
                    cpu, rss, sm, vram, usec = sample_container_entry(
                        entry,
                        elapsed_s,
                        prev_usec.get(label),
                        vram_map,
                        sm_map,
                    )
                    prev_usec[label] = usec
                else:
                    raise ValueError(f"process map entry {entry!r} needs 'pattern' or 'container'")
                prev_sample_mono[label] = sample_mono
                writer.writerow(
                    format_row(now_ns, label, cpu, rss, sm, vram, NOT_APPLICABLE, loadavg_1m)
                )
                f.flush()

            next_tick += interval_s
            sleep_s = next_tick - time.monotonic()
            if sleep_s <= 0:
                # Fell behind (slow sample): resync instead of a
                # tight-loop burst trying to catch up sample-for-sample.
                next_tick = time.monotonic()
            else:
                _sleep_until(next_tick, stop_flag)


def main(argv=None) -> int:
    args = parse_args(argv)
    run(args.processes, args.out, args.interval, args.proc_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
