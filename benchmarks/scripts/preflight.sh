#!/usr/bin/env bash
# Per-run preflight: refuse to start a run the host cannot honestly measure.
#
#   bash benchmarks/scripts/preflight.sh <cell> [--port N] [--results-dir DIR]
#
# Exit 0 with KEY=VALUE lines on stdout (run.sh folds them into the manifest's
# `placement` block); exit 2 with a NAMED reason on stderr otherwise. Every
# refusal below maps onto a pre-registered exclusion criterion
# (benchmarks/config/exclusions.md) so that "why did this run not happen" is
# answerable from the pre-registration, not from memory:
#
#   loadavg >= 8            criterion 6 (hostload)   -- localization degrades
#   RPC port already bound  criterion 7 (port)       -- SIGABRT inside LoadMap
#   engine BuildId mismatch criterion 8 (buildid)    -- editor modules stale
#
# Disk and stale DDS shared memory are not exclusion criteria: they are
# preconditions for the run producing data at all, so they are checked (and,
# for SHM, repaired) here rather than diagnosed afterwards.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$BENCH/.." && pwd)"

MAX_LOADAVG=8
MIN_FREE_GB=20
SHM_GLOB='fastrtps_*'
# Local, already-present image used only as a root shell with the host's
# /dev/shm: the observer image is the one image every cell already needs.
SHM_ROOT_IMAGE="bench-observer:universe-devel"

CELL="${1:?usage: preflight.sh <cell> [--port N] [--results-dir DIR] [--no-clean]}"
shift
PORT=2000
RESULTS_DIR="$BENCH/results"
# --no-clean: report the stale-SHM counts without deleting anything. Exists so
# `run.sh --dry-run` can run the REAL preflight (and therefore prove the
# manifest it would write is valid, BuildId included) without the one side
# effect preflight otherwise has on the host.
CLEAN=1
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --results-dir) RESULTS_DIR="$2"; shift 2 ;;
    --no-clean) CLEAN=0; shift ;;
    *) echo "PREFLIGHT FAIL: unknown argument $1" >&2; exit 2 ;;
  esac
done

fail() { echo "PREFLIGHT FAIL: $*" >&2; exit 2; }

# Cell identity comes from the pre-registered matrix, never from the caller:
# preflight's UE-only checks must not be skippable by mislabelling a cell.
CELL_JSON="$(cd "$REPO" && python3 -m benchmarks.scripts.cell_info "$CELL")" ||
  fail "cell $CELL is not registered in benchmarks/config/cells.yaml"
cell_field() { printf '%s' "$CELL_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin)['$1'])"; }
APPROACH="$(cell_field approach)"
CARLA_KIND="$(cell_field carla)"

# ---------------------------------------------------------------------------
# 1. Host load. P1 Verdict 1: localization degrades under load, so a run
#    started on a busy host measures the host, not the approach.
# ---------------------------------------------------------------------------
LOADAVG="$(awk '{print $1}' /proc/loadavg)"
awk -v l="$LOADAVG" -v m="$MAX_LOADAVG" 'BEGIN { exit !(l < m) }' ||
  fail "hostload:$LOADAVG (1-min loadavg >= $MAX_LOADAVG; exclusions.md criterion 6)"

# ---------------------------------------------------------------------------
# 2. Free disk on the filesystem that actually holds the results tree.
#    RESOLVED, never hardcoded: on this host / and /home are different
#    filesystems with very different free space, and the repo (hence
#    benchmarks/results/) lives on /home. Checking / would abort every run for
#    the wrong reason; hardcoding /home would break the moment the repo moves.
#    results/ may not exist yet on a first run, so walk up to the nearest
#    existing ancestor -- same filesystem, by definition.
# ---------------------------------------------------------------------------
probe="$RESULTS_DIR"
while [ ! -d "$probe" ]; do probe="$(dirname "$probe")"; done
RESULTS_FS="$(df -P "$probe" | awk 'NR==2 {print $6}')"
FREE_KB="$(df -Pk "$probe" | awk 'NR==2 {print $4}')"
FREE_GB=$((FREE_KB / 1024 / 1024))
[ "$FREE_GB" -ge "$MIN_FREE_GB" ] ||
  fail "disk: ${FREE_GB} GB free on $RESULTS_FS (holding $RESULTS_DIR), need >= ${MIN_FREE_GB} GB"

# ---------------------------------------------------------------------------
# 3. CARLA RPC port. A collision surfaces as SIGABRT inside LoadMap, not as a
#    bind error, so it is easy to misdiagnose as a build problem -- catch it
#    here instead. Cells with `carla: none` (CAL-rmw) bind nothing.
#    `ss` output is captured into a variable rather than piped to grep -q:
#    grep -q can close the pipe mid-write, SIGPIPE-killing ss, and under
#    pipefail that flips the result to "not bound" while the port IS bound
#    (the same trap run_e2e.sh's port_bound() documents).
# ---------------------------------------------------------------------------
if [ "$CARLA_KIND" != "none" ]; then
  ss_out="$(ss -ltn 2>/dev/null)" || true
  if [[ "$ss_out" =~ :${PORT}[[:space:]] ]]; then
    fail "port:$PORT (already bound; exclusions.md criterion 7)"
  fi
fi

# ---------------------------------------------------------------------------
# 4. Stale DDS shared memory. Segments accumulate across runs (the bridge
#    stack alone regrows 91 -> 383 in ten minutes) and a stale set degrades
#    discovery for the NEXT run, which would be charged to that run's
#    approach. User-owned ones we can delete directly; root-owned ones (left
#    by a container that ran as root with --ipc=host) need a root view of the
#    host's /dev/shm, which is exactly what --ipc=host gives a container.
#    `find -delete`, never a bare glob: an empty glob under some shells
#    expands to a literal pattern and deletes nothing while looking fine.
# ---------------------------------------------------------------------------
shm_count() { find /dev/shm -maxdepth 1 -name "$SHM_GLOB" "$@" 2>/dev/null | wc -l; }
SHM_USER_BEFORE="$(shm_count -user "$USER")"
if [ "$CLEAN" = "1" ]; then
  find /dev/shm -maxdepth 1 -name "$SHM_GLOB" -user "$USER" -delete 2>/dev/null || true
fi
SHM_USER_CLEARED=$((SHM_USER_BEFORE - $(shm_count -user "$USER")))

SHM_ROOT_BEFORE="$(shm_count ! -user "$USER")"
SHM_ROOT_CLEARED=0
if [ "$SHM_ROOT_BEFORE" -gt 0 ] && [ "$CLEAN" = "1" ]; then
  if docker run --rm --ipc=host "$SHM_ROOT_IMAGE" \
    find /dev/shm -maxdepth 1 -name "$SHM_GLOB" -delete >/dev/null 2>&1; then
    SHM_ROOT_CLEARED=$((SHM_ROOT_BEFORE - $(shm_count ! -user "$USER")))
  else
    # Reported, not fatal: a run CAN proceed with stale root-owned segments,
    # but the count must be visible in the manifest rather than absorbed.
    echo "WARN: could not clear $SHM_ROOT_BEFORE root-owned $SHM_GLOB segments" >&2
  fi
fi

# ---------------------------------------------------------------------------
# 5. Engine BuildId, UE-based approaches only. All three CARLA trees and the
#    shared engine share ONE BuildId (pins.yaml engine.build_id); a rebuild in
#    any tree bumps it everywhere, and a tree whose editor modules still carry
#    the old one aborts a -game launch silently (no console, "do not rebuild").
#    Every UnrealEditor.modules under the tree is checked, not just the plugin
#    one: any single stale module is enough to abort the launch.
# ---------------------------------------------------------------------------
ENGINE_BUILD_ID=""
CARLA_TREE=""
if [ "$APPROACH" = "extension" ] || [ "$APPROACH" = "tier4-native" ]; then
  # stdout on success is "<tree> <build-id>"; on failure the helper exits
  # non-zero with the named reason on stderr, folded in by 2>&1 so `fail`
  # can report it verbatim.
  if ! BUILDID_OUT="$(
    APPROACH="$APPROACH" PINS="$BENCH/pins.yaml" python3 - 2>&1 <<'PY'
import glob
import json
import os
import sys

import yaml

pins = yaml.safe_load(open(os.environ["PINS"]))
key = "extension_carla_fork" if os.environ["APPROACH"] == "extension" else "tier4_carla_fork"
tree = os.path.expanduser(str(pins[key]["path"]))
pinned = str(pins["engine"]["build_id"])

modules = sorted(glob.glob(f"{tree}/Unreal/CarlaUnreal/**/UnrealEditor.modules", recursive=True))
if not modules:
    sys.exit(f"buildid:{tree} has no UnrealEditor.modules (editor never built in this tree)")
stale = []
for path in modules:
    try:
        found = json.load(open(path))["BuildId"]
    except (OSError, ValueError, KeyError) as exc:
        stale.append(f"{path}: unreadable ({exc})")
        continue
    if found != pinned:
        stale.append(f"{path}: {found}")
if stale:
    sys.exit(f"buildid:{tree} != pins.yaml engine.build_id {pinned}: " + "; ".join(stale))
print(tree, pinned)
PY
  )"; then
    fail "$BUILDID_OUT (exclusions.md criterion 8)"
  fi
  read -r CARLA_TREE ENGINE_BUILD_ID <<<"$BUILDID_OUT"
fi

# ---------------------------------------------------------------------------
# 6. Map-bundle provenance. pins.yaml can carry several candidate contents for
#    ONE mounted bundle directory, so the registered invariant is that the
#    installed file hashes to EXACTLY ONE pin block -- and that block is the
#    bundle the run used. Enforced here because an invariant with no consumer
#    is a comment. Reported as `map_bundle_pin` so the manifest records WHICH
#    bundle, not merely that one matched.
#
#    FAILS only on a provenance FAULT: bytes matching none of the pins
#    registered for that bundle (changed without re-pinning) or matching
#    several (a duplicated registration). An UNREGISTERED bundle directory is
#    a gap in the record, not a corrupted bundle, so it SKIPS with a named
#    warning -- helper exit 3, distinct from its fault exit 2. That
#    distinction is load-bearing: an earlier revision checked one flat
#    candidate list against every cell and so FAILED every Nishi-Shinjuku run,
#    which would have blocked Task 15 and the whole C/D half of the campaign.
#    A provenance check must not stop measurement.
#
#    The bundle is resolved from what THE CELL'S OWN LAUNCHER mounts, not from
#    map_defaults.sh unconditionally: that table is the EXTENSION path's, while
#    cells/python-bridge.sh pins the unshifted ~/autoware_map/town10 for the E
#    family. Resolving E through map_defaults.sh recorded the extension cells'
#    bundle as E's -- a wrong provenance record the B family would have
#    inherited. APPROACH_BUNDLE_DIR in bundle_pin.py holds the non-extension
#    mappings: tier4-native resolves to nothing because Task 13 owns what it
#    mounts, and calibration has no localization stack at all.
# ---------------------------------------------------------------------------
MAP_BUNDLE_PIN=""
CELL_MAP="$(cell_field map)"
BUNDLE_DIR_NAME=""
if [ "$CELL_MAP" != "none" ]; then
  if [ "$APPROACH" = "extension" ]; then
    # shellcheck source=scripts/e2e/map_defaults.sh disable=SC1091
    . "$REPO/scripts/e2e/map_defaults.sh"
    carla_autoware_map_defaults "$CELL_MAP"
    if [ -n "$MAP_DEFAULT_DIR" ]; then
      BUNDLE_DIR_NAME="$(basename "$MAP_DEFAULT_DIR")"
    fi
  else
    BUNDLE_DIR_NAME="$(cd "$REPO" && APPROACH="$APPROACH" python3 -c '
import os

from benchmarks.scripts.bundle_pin import APPROACH_BUNDLE_DIR

print(APPROACH_BUNDLE_DIR.get(os.environ["APPROACH"]) or "")
')"
  fi
fi
if [ -n "$BUNDLE_DIR_NAME" ]; then
  BUNDLE_PCD="$HOME/autoware_map/$BUNDLE_DIR_NAME/pointcloud_map.pcd"
  if [ -r "$BUNDLE_PCD" ]; then
    set +e
    BUNDLE_OUT="$(cd "$REPO" && python3 -m benchmarks.scripts.bundle_pin \
      --bundle-dir "$BUNDLE_DIR_NAME" "$BUNDLE_PCD" 2>&1)"
    BUNDLE_RC=$?
    set -e
    case "$BUNDLE_RC" in
      0) MAP_BUNDLE_PIN="$BUNDLE_OUT" ;;
      3) echo "WARN: $BUNDLE_OUT" >&2 ;;
      *) fail "$BUNDLE_OUT" ;;
    esac
  fi
fi

# ---------------------------------------------------------------------------
# KEY=VALUE report. run.sh folds these into placement.
# ---------------------------------------------------------------------------
GOVERNOR="$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo unknown)"
echo "cpu_governor=$GOVERNOR"
echo "nproc=$(nproc)"
echo "loadavg=$LOADAVG"
echo "results_fs=$RESULTS_FS"
echo "free_gb=$FREE_GB"
if [ "$CARLA_KIND" != "none" ]; then
  echo "carla_rpc_port=$PORT"
fi
echo "shm_user_cleared=$SHM_USER_CLEARED"
echo "shm_root_cleared=$SHM_ROOT_CLEARED"
echo "shm_root_remaining=$(shm_count ! -user "$USER")"
if [ -n "$ENGINE_BUILD_ID" ]; then
  echo "engine_build_id=$ENGINE_BUILD_ID"
  echo "carla_tree=$CARLA_TREE"
fi
if [ -n "$MAP_BUNDLE_PIN" ]; then
  echo "map_bundle_pin=$MAP_BUNDLE_PIN"
fi
exit 0
