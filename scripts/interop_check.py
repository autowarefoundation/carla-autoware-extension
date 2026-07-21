#!/usr/bin/env python3
"""G0 interop check: verify CARLA native-DDS topics from a ROS 2 container.

Thin CLI over interop_lib (which holds all verdict logic): loads the YAML
topic contract, runs every check through the real `ros2` CLI, writes the
JSON/Markdown reports, and exits 0 iff every topic passes. Requires only
the ros2 CLI + PyYAML."""

import argparse
import json
import pathlib
import subprocess
import sys

import yaml

import interop_lib


def sh(cmd, timeout):
    """Run a shell command, returning (returncode, combined stdout+stderr).

    A timeout is reported as return code 124 to mirror the `timeout(1)`
    convention used by the echo/hz checks."""
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as e:
        return 124, (e.stdout or "") + (e.stderr or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topics", required=True)
    ap.add_argument("--report-dir", default="/work/reports")
    ap.add_argument(
        "--discover", action="store_true", help="just dump `ros2 topic list -t` and exit"
    )
    args = ap.parse_args()

    if args.discover:
        print(sh("ros2 topic list -t", 30)[1])
        return 0

    specs = yaml.safe_load(open(args.topics))["topics"]
    results = [interop_lib.evaluate_topic(s, sh) for s in specs]

    outdir = pathlib.Path(args.report_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "interop_results.json").write_text(json.dumps(results, indent=2))

    table = interop_lib.render_table(results)
    summary = interop_lib.summarize(results)
    (outdir / "interop_results.md").write_text(table + "\n\n" + summary + "\n")

    print(table)
    print(f"\n{summary}")
    return 1 if any(not r["ok"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
