#!/usr/bin/env bash
# Artifact-staleness gate and tree-identity recorder for the tier4-native cell
# family -- cells B, B-hf, B45 and D (benchmarks/cells/tier4-native.sh:2).
#
#   TIER4_TREE=~/src/carla-autoware-native bash verify_tier4_artifact.sh
#
# WHY THIS EXISTS (Task 17b, 2026-07-30). Cell A is gated: cells/extension.sh
# launches scripts/e2e/run_e2e.sh (cells/extension.sh:192), which calls
# scripts/e2e/verify_editor_artifact.sh (run_e2e.sh:126) and refuses a run
# whose editor plugin .so is older than CARLA HEAD. The B family reached
# nothing equivalent: its launcher boots the SHARED engine's UnrealEditor
# against the tier4 tree's own .uproject (cells/tier4-native.sh:147-149) and
# neither that launcher nor cells/tier4_autoware.sh contained any artifact
# check at all. Every B-family run committed before this script was therefore
# ungated -- see benchmarks/results/B/PROVENANCE.md for what that does and does
# not leave established.
#
# The manifests were no better: placement recorded `carla_tree`, which is a
# PATH, not an identity. No git sha, no artifact digest, no build timestamp.
# Nothing tied a filed measurement to the bytes that produced it.
#
# TWO OUTPUT CHANNELS, deliberately (the same split preflight.sh uses for its
# map-bundle skips):
#   stdout  KEY=VALUE lines ONLY -- the durable half. preflight.sh captures
#           these and run.sh folds them into the manifest's `placement` block,
#           so anything printed to stdout that is not KEY=VALUE corrupts a
#           manifest. Tests pin that contract.
#   stderr  OK/WARN prose -- the visible half, for the operator watching a
#           bring-up.
#
# Exit 2 with a NAMED check on stderr on refusal, matching preflight.sh's
# convention (verify_editor_artifact.sh predates it and uses 1). A refusal here
# happens at preflight, BEFORE run.sh writes a manifest, so the run never
# starts and no exclusion criterion is consumed -- this is a precondition in
# the sense of preflight.sh's disk and stale-SHM checks, NOT a new entry in
# benchmarks/config/exclusions.md, which may not be edited.
set -euo pipefail

TIER4_TREE=${TIER4_TREE:?set TIER4_TREE to the tier4 fork checkout (pins.yaml tier4_carla_fork.path)}

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="$(cd "$HERE/.." && pwd)"
# Overridable so the unit tests can point the registered-patch comparison at a
# synthetic set without copying the real one.
TIER4_PATCH_DIR="${TIER4_PATCH_DIR:-$BENCH/patches/tier4-native}"

fail() { echo "PREFLIGHT FAIL: $*" >&2; exit 2; }
note() { echo "$*" >&2; }

# ---------------------------------------------------------------------------
# The artifacts. `-game` on the shared engine's UnrealEditor binary loads the
# plugin's EDITOR .so, which is why cell A's gate names that file and not the
# shipping one; the tier4 family boots through the same binary
# (cells/tier4-native.sh:27,147), so the same file is the one that runs.
#
# libcarla-ros2-native.so is gated alongside it because the two split the ROS 2
# publishing path between them and only one of them is rebuilt by some targets.
# MEASURED 2026-07-30 on the tree as it stands: libUnrealEditor-Carla.so
# DEFINES carla::ros2::ROS2::ProcessDataFromLidar and carries an UNDEFINED
# reference to carla::ros2::CarlaLidarPublisher::SetDataEx, which
# libcarla-ros2-native.so defines. A stale copy of either half is a different
# wire format, so both are gated.
# ---------------------------------------------------------------------------
PLUGIN_BIN_DIR="$TIER4_TREE/Unreal/CarlaUnreal/Plugins/Carla/Binaries/Linux"
EDITOR_SO="$PLUGIN_BIN_DIR/libUnrealEditor-Carla.so"
ROS2_SO="$PLUGIN_BIN_DIR/libcarla-ros2-native.so"

# Sources the two artifacts are built from. DELIBERATELY OVER-APPROXIMATED:
# both artifacts are checked against the union rather than each against its own
# subset, because ROS2.cpp lives under LibCarla/source yet links into the
# EDITOR plugin (measured above), so a per-artifact split would have to encode
# that and would silently rot when the build layout moves. Over-approximating
# can only ever cause a false REFUSAL -- which is a rebuild, loudly named --
# and never a false pass, which is a filed measurement of unknown provenance.
# CMake/ and LibCarla/CMakeLists.txt are included because two of the three
# registered patches (0001-toolchain-libm, 0002-glibc-compat) change exactly
# those build inputs.
SOURCE_PATHS=(
  "$TIER4_TREE/LibCarla/source"
  "$TIER4_TREE/Unreal/CarlaUnreal/Plugins/Carla/Source"
  "$TIER4_TREE/LibCarla/CMakeLists.txt"
  "$TIER4_TREE/CMake"
)

# ---------------------------------------------------------------------------
# Check 1 -- tier4-tree. The tree must exist and be a git work tree, because
# its git sha is half of the identity this script is here to record. A path
# that resolves to something else entirely is the shape a moved checkout or a
# mistyped pin takes.
# ---------------------------------------------------------------------------
[ -d "$TIER4_TREE" ] ||
  fail "tier4-tree: $TIER4_TREE is not a directory (pins.yaml tier4_carla_fork.path)"
git -C "$TIER4_TREE" rev-parse --git-dir >/dev/null 2>&1 ||
  fail "tier4-tree: $TIER4_TREE is not a git work tree, so no tree identity can be
  recorded for the run (pins.yaml tier4_carla_fork.path)"

# ---------------------------------------------------------------------------
# Check 2 -- tier4-artifact-missing. Named separately from staleness: "never
# built in this tree" and "built, then left behind" need different fixes.
# ---------------------------------------------------------------------------
for so in "$EDITOR_SO" "$ROS2_SO"; do
  [ -f "$so" ] ||
    fail "tier4-artifact-missing: $so
  -> build the tier4 fork's editor plugin before any B-family run
     (benchmarks/patches/tier4-native/README.md has the recipe)"
done

# ---------------------------------------------------------------------------
# Check 3 -- tier4-artifact-stale. The trap verify_editor_artifact.sh guards
# for cell A, transposed: an artifact older than a source it is built from is a
# binary running code nobody in the record has read.
#
# Sub-second parts are truncated on BOTH sides, so a source and an artifact
# written inside the same second compare equal and pass -- which is what a
# build that reads a file and relinks moments later actually looks like.
# ---------------------------------------------------------------------------
present=()
for p in "${SOURCE_PATHS[@]}"; do
  [ -e "$p" ] && present+=("$p")
done
[ "${#present[@]}" -gt 0 ] ||
  fail "tier4-source-roots: none of ${SOURCE_PATHS[*]} exist, so artifact staleness
  cannot be judged at all -- $TIER4_TREE is not a CARLA tree"

# The maximum is taken by awk, NOT by `sort -rn | head -1`: `head` closes the
# pipe on its first line, SIGPIPE-kills `sort`, and under `set -o pipefail`
# that makes the whole command exit 141 -- the same trap cells/tier4-native.sh
# documents for `ss | grep -q`. Measured here 2026-07-30: the first draft of
# this script exited 141 on the real tree.
newest_line="$(find "${present[@]}" -type f -printf '%T@ %p\n' 2>/dev/null |
  awk '$1 + 0 > max { max = $1 + 0; line = $0 } END { if (line != "") print line }')"
[ -n "$newest_line" ] ||
  fail "tier4-source-roots: no files under ${present[*]}"
NEWEST_SRC_EPOCH="${newest_line%% *}"
NEWEST_SRC_EPOCH="${NEWEST_SRC_EPOCH%%.*}"
NEWEST_SRC_PATH="${newest_line#* }"

for so in "$EDITOR_SO" "$ROS2_SO"; do
  so_mtime="$(stat -c %Y "$so")"
  if [ "$so_mtime" -lt "$NEWEST_SRC_EPOCH" ]; then
    fail "tier4-artifact-stale: $so ($so_mtime) is OLDER than the newest source it is
  built from, $NEWEST_SRC_PATH ($NEWEST_SRC_EPOCH).
  -> rebuild the tier4 fork's plugin before any B-family run; a stale .so
     publishes a different wire format from the source the record cites."
  fi
done

# ---------------------------------------------------------------------------
# Check 4 -- tier4-artifact-older-than-head. Cell A's own check, kept for
# parity, and WEAK HERE ON PURPOSE: the tier4 tree carries its campaign changes
# UNCOMMITTED (the registered patch set), so its HEAD timestamp says nothing
# about when the code that runs was last edited. Check 3 is the load-bearing
# one; this one only catches the case of the tree being fast-forwarded onto a
# newer upstream commit without a rebuild.
# ---------------------------------------------------------------------------
COMMIT_EPOCH="$(git -C "$TIER4_TREE" show -s --format=%ct HEAD)"
for so in "$EDITOR_SO" "$ROS2_SO"; do
  so_mtime="$(stat -c %Y "$so")"
  if [ "$so_mtime" -lt "$COMMIT_EPOCH" ]; then
    fail "tier4-artifact-older-than-head: $so ($so_mtime) is OLDER than the tier4
  tree's HEAD commit ($COMMIT_EPOCH).
  -> rebuild the tier4 fork's plugin before any B-family run."
  fi
done

note "OK: tier4 plugin artifacts are newer than every source under ${present[*]}"

# ---------------------------------------------------------------------------
# Identity. Recorded, not gated -- with ONE exception noted below.
#
# The worktree state is compared against the REGISTERED patch set, derived from
# benchmarks/patches/tier4-native/*.patch rather than from a hardcoded list, so
# adding or dropping a registered patch updates the expectation automatically
# instead of silently widening it.
#
# A divergence (a fourth edit, or a registered patch that is not applied) is
# reported and WARNed, NOT refused. Two reasons, both deliberate: the brief for
# this gate specifies exactly one refusal, staleness; and turning an unexpected
# local edit into a hard stop would add a run-blocking criterion that nothing
# pre-registered supports. The digest below makes the state durable either way,
# which is the thing that was missing.
# ---------------------------------------------------------------------------
TIER4_IDENTITY_KV="$(
  TIER4_TREE="$TIER4_TREE" TIER4_PATCH_DIR="$TIER4_PATCH_DIR" \
    EDITOR_SO="$EDITOR_SO" ROS2_SO="$ROS2_SO" python3 - <<'PY'
import glob
import hashlib
import os
import subprocess


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


tree = os.environ["TIER4_TREE"]
patch_dir = os.environ["TIER4_PATCH_DIR"]

porcelain = subprocess.run(
    ["git", "-C", tree, "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=True,
).stdout

# `XY <path>`; a rename is `R  <old> -> <new>` and the NEW path is the one that
# describes the tree as it stands.
dirty = set()
for line in porcelain.splitlines():
    path = line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    dirty.add(path.strip().strip('"'))

# `+++ b/<path>` is the post-image path, so a patch that CREATES a file (whose
# `---` side is /dev/null, as 0002 does for GlibcCompat.c) is still counted.
registered = set()
for patch in sorted(glob.glob(os.path.join(patch_dir, "*.patch"))):
    with open(patch, errors="replace") as fh:
        for line in fh:
            if line.startswith("+++ b/"):
                registered.add(line[6:].strip())

if not dirty:
    state = "clean"
elif dirty == registered:
    state = "registered-patches"
else:
    extra = sorted(dirty - registered)
    absent = sorted(registered - dirty)
    state = "diverged:+{}:-{}".format(",".join(extra) or "-", ",".join(absent) or "-")

print("tier4_git_sha=" + subprocess.run(
    ["git", "-C", tree, "rev-parse", "HEAD"],
    capture_output=True, text=True, check=True,
).stdout.strip())
print("tier4_worktree=" + state)
print("tier4_worktree_paths_sha256=" + hashlib.sha256(
    "\n".join(sorted(dirty)).encode()
).hexdigest())
print("tier4_plugin_sha256=" + sha256_file(os.environ["EDITOR_SO"]))
print("tier4_ros2_native_sha256=" + sha256_file(os.environ["ROS2_SO"]))
PY
)"

echo "$TIER4_IDENTITY_KV"
echo "tier4_plugin_mtime=$(stat -c %Y "$EDITOR_SO")"
echo "tier4_ros2_native_mtime=$(stat -c %Y "$ROS2_SO")"
echo "tier4_newest_source_mtime=$NEWEST_SRC_EPOCH"

case "$TIER4_IDENTITY_KV" in
  *"tier4_worktree=diverged:"*)
    note "WARN: the tier4 tree's local edits are NOT the registered patch set
  ($TIER4_PATCH_DIR). The run is NOT blocked; the divergence is recorded in the
  manifest's placement.tier4_worktree, and it is a finding to write up, never a
  pin to retrofit."
    ;;
  *)
    note "OK: tier4 tree identity recorded"
    ;;
esac
exit 0
