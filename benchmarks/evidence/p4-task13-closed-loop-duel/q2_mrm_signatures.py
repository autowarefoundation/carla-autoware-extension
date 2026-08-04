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
Counts only; no cross-cell quantity is computed.
"""

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


if __name__ == "__main__":
    main()
