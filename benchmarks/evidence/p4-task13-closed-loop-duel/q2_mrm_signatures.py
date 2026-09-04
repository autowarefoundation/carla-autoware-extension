"""Task 13 Q2 observation: the `mrm_handler` readiness signatures, per B-cyc run.

PROVENANCE.md section 19.4 established the mechanism behind two static B-cyc runs
recording zero control traffic, and isolated one distinguishing line present in
both and in none of the other eight:

    [control.autoware_operation_mode_transition_manager]: Subscribed control_cmd
    is timed out.

What it could NOT settle from static-arm artifacts is whether the break is an
Autoware-side state bug (cell-independent) or an intermittent bare-DDS discovery
miss (a cost of B-cyc's registered row-11 caveat). A CLOSED-LOOP run engages, so
it exercises `mrm_handler` far harder -- section 19.4 names Task 13's runs as the
free discriminator.

This script is pure observation over logs that are being filed anyway. It adds
no run, alters no observer set, and reads nothing outside the run directories.
No cross-cell quantity is computed -- every table here is cell B-cyc only.

FIX ROUND 1 ADDITION: the PRE-ARM WINDOW. The first cut of this analysis
counted signatures and concluded the static arm's precondition "cannot arise"
in a closed-loop run. That inference was wrong, and the disproof is in these
same ten runs. The observer attaches ~6 s BEFORE the arm script in every run,
so each closed-loop run contains a pre-arm window in which the only possible
`control_cmd` source is section 19.4's emergency cycling -- exactly the static
arm's precondition. `pre_arm_window()` below measures it, and `outliers()`
measures the three dimensions on which the one signature-carrying run departs
from the other nine. Both exist so section 21's figures have a runnable source
rather than being asserted.
"""

import csv
import re
import sys
from pathlib import Path

ROOT = Path("/home/youtalk/src/carla-autoware-extension-worktrees/bench-p0")
RESULTS = ROOT / "benchmarks" / "results"
PRE_TASK13_BCYC = 11

# The section 19.4 signature, plus the two readiness messages named in the brief.
SIGNATURES = {
    "ctrl_cmd_timed_out": "Subscribed control_cmd is timed out.",
    "wait_availability": "waiting for operation_mode_availability msg...",
    "wait_mrm_avail": "waiting for mrm emergency stop to become available...",
    "no_mrm_available": "no mrm operation available: operate emergency_stop",
    "mrm_state_changed": "MRM State changed",
    "gate_emergency": "vehicle_cmd_gate",
    "monitor_error": "topic is timeout. Set ERROR",
    "monitor_warn": "topic is timeout. Set WARN",
}

# Arm-difficulty markers, read from the run's own arm.log rather than inferred.
ARM_RETRY = "change_to_autonomous: not yet ok"
ARM_SUCCESS = "change_to_autonomous: SUCCEEDED"
ARMED_PREFIX = "ARMED:"


def count_signatures(path: Path) -> dict:
    counts = dict.fromkeys(SIGNATURES, 0)
    if not path.exists():
        return counts
    with path.open(errors="replace") as fh:
        for line in fh:
            for key, needle in SIGNATURES.items():
                if needle in line:
                    counts[key] += 1
    return counts


def arm_difficulty(path: Path) -> dict:
    if not path.exists():
        return {"arm_retries": None, "armed": None, "arm_ad_api_ok": None}
    text = path.read_text(errors="replace")
    return {
        "arm_retries": text.count(ARM_RETRY),
        "armed": any(ln.startswith(ARMED_PREFIX) for ln in text.splitlines()),
        "arm_ad_api_ok": ARM_SUCCESS in text,
    }


CONTROL_CMD = "/control/command/control_cmd"
SIGNATURE = SIGNATURES["ctrl_cmd_timed_out"]


def _first_log_ts(path: Path, needle: str | None = None) -> float | None:
    """First `[<unix>.<ns>]` stamp in `path`, optionally on lines containing needle."""
    for ln in path.open(errors="replace"):
        if needle is not None and needle not in ln:
            continue
        m = re.search(r"\[(\d+\.\d+)\]", ln)
        if m:
            return float(m.group(1))
    return None


def _log_ts(path: Path, needle: str) -> list[float]:
    out = []
    for ln in path.open(errors="replace"):
        if needle in ln:
            m = re.search(r"\[(\d+\.\d+)\]", ln)
            if m:
                out.append(float(m.group(1)))
    return out


def _observer(d: Path) -> tuple[float, list[float]]:
    """(observer window start, control_cmd arrival times), both system-clock seconds."""
    starts, cc = [], []
    with (d / "observer.csv").open() as fh:
        for row in csv.DictReader(fh):
            t = int(row["arrival_system_ns"]) / 1e9
            starts.append(t)
            if row["topic"] == CONTROL_CMD:
                cc.append(t)
    return min(starts), cc


def pre_arm_window(dirs: list[Path]) -> None:
    """Section 19.4's precondition, measured -- does it arise on the closed-loop arm?

    The observer attaches before the arm script runs. In that gap nothing is
    engaged, so `control_cmd` can only come from `mrm_handler`'s emergency
    cycling driving `vehicle_cmd_gate` -- the static arm's exact mechanism.
    """
    print("\n## PRE-ARM WINDOW: the observer attaches before the arm, so the static")
    print("## arm's precondition (control_cmd only from emergency cycling) DOES arise.")
    print(f"{'run':<10} {'arm-obs_s':>10} {'first_cc-obs_s':>15} {'first_cc-arm_s':>15}  pre_arm_cc")
    for d in dirs:
        obs, cc = _observer(d)
        arm = _first_log_ts(d / "arm.log")
        if arm is None or not cc:
            print(f"{d.name:<10} {'-':>10} {'-':>15} {'-':>15}  -")
            continue
        print(
            f"{d.name:<10} {arm - obs:>+10.2f} {cc[0] - obs:>+15.2f} "
            f"{cc[0] - arm:>+15.2f}  {'YES' if cc[0] < arm else 'NO -- SILENT'}"
        )


def outliers(dirs: list[Path]) -> None:
    """The three dimensions on which a signature-carrying run may depart."""
    print("\n## per-run shape: mrm cycling extent and control-traffic span")
    print(f"{'run':<10} {'sig':>4} {'mrm_n':>6} {'last_mrm-engage_s':>18} {'cc_span_s':>10}")
    for d in dirs:
        sig = len(_log_ts(d / "tier4-autoware.log", SIGNATURE))
        mrm = _log_ts(d / "tier4-autoware.log", "MRM State changed")
        eng = _first_log_ts(d / "arm.log", "published engage=true")
        _, cc = _observer(d)
        tail = f"{mrm[-1] - eng:+18.1f}" if mrm and eng else f"{'-':>18}"
        span = f"{cc[-1] - cc[0]:10.1f}" if cc else f"{'-':>10}"
        print(f"{d.name:<10} {sig:>4} {len(mrm):>6} {tail} {span}")


def signature_band(dirs: list[Path]) -> None:
    """For each run carrying the signature, where its band sits vs the observer."""
    print("\n## signature band vs observer window start (signature-carrying runs only)")
    for d in dirs:
        w = _log_ts(d / "tier4-autoware.log", SIGNATURE)
        if not w:
            continue
        obs, cc = _observer(d)
        arm = _first_log_ts(d / "arm.log")
        print(
            f"{d.name}: n={len(w)} band {w[0]:.3f} -> {w[-1]:.3f} (span {w[-1] - w[0]:.2f}s)\n"
            f"  observer start {obs:.3f}; {sum(x < obs for x in w)} warnings precede it, "
            f"{sum(x >= obs for x in w)} follow\n"
            f"  band opens {obs - w[0]:.2f}s BEFORE the observer attaches, "
            f"closes {w[-1] - obs:.2f}s AFTER it\n"
            f"  arm starts {arm:.3f} ({arm - w[-1]:+.2f}s vs last warning); "
            f"first control_cmd {cc[0]:.3f} ({cc[0] - w[-1]:+.2f}s vs last warning)"
        )


def main() -> None:
    dirs = [
        d
        for d in sorted((RESULTS / "B-cyc").glob("run-*"))
        if int(d.name.split("-")[1]) > PRE_TASK13_BCYC
    ]
    print(f"# B-cyc closed-loop runs examined: {len(dirs)}\n")

    hdr = (
        f"{'run':<10} {'timedout':>8} {'wait_avail':>10} {'wait_mrm':>8} "
        f"{'no_mrm':>7} {'mrm_chg':>8} {'mon_ERR':>8} {'mon_WARN':>8} "
        f"{'retries':>7} {'armed':>6} {'ad_api':>7}"
    )
    print("## per-run signature counts (tier4-autoware.log) and arm difficulty (arm.log)")
    print(hdr)
    rows = []
    for d in dirs:
        c = count_signatures(d / "tier4-autoware.log")
        a = arm_difficulty(d / "arm.log")
        rows.append((d.name, c, a))
        print(
            f"{d.name:<10} {c['ctrl_cmd_timed_out']:>8} {c['wait_availability']:>10} "
            f"{c['wait_mrm_avail']:>8} {c['no_mrm_available']:>7} "
            f"{c['mrm_state_changed']:>8} {c['monitor_error']:>8} {c['monitor_warn']:>8} "
            f"{str(a['arm_retries']):>7} {str(a['armed']):>6} {str(a['arm_ad_api_ok']):>7}"
        )

    print("\n## Q2 readings")
    sig = [n for n, c, _ in rows if c["ctrl_cmd_timed_out"] > 0]
    wa = [n for n, c, _ in rows if c["wait_availability"] > 0]
    wm = [n for n, c, _ in rows if c["wait_mrm_avail"] > 0]
    retried = [n for n, _, a in rows if (a["arm_retries"] or 0) > 0]
    print(f"section 19.4 signature `Subscribed control_cmd is timed out.` present in: {sig or 'NONE'}")
    print(f"`waiting for operation_mode_availability msg...` present in: {wa or 'NONE'}")
    print(f"`waiting for mrm emergency stop to become available...` present in: {wm or 'NONE'}")
    print(f"runs whose arm needed >=1 change_to_autonomous retry: {retried or 'NONE'}")
    print(f"runs that did NOT reach ARMED: {[n for n, _, a in rows if not a['armed']] or 'NONE'}")

    # Does arm difficulty correlate with the readiness messages?
    both = sorted(set(retried) & set(sig + wa + wm))
    print(f"runs with BOTH an arm retry and any readiness/timeout signature: {both or 'NONE'}")
    # The retry count is INVARIANT at 1 across runs with and without the
    # readiness messages, which rules out co-variation with them -- it does not
    # rule out a uniformly discovery-induced single retry (fix round 1, M6).
    counts = sorted({a["arm_retries"] for _, _, a in rows})
    print(f"distinct change_to_autonomous retry counts across the ten runs: {counts}")

    pre_arm_window(dirs)
    outliers(dirs)
    signature_band(dirs)


if __name__ == "__main__":
    main()
