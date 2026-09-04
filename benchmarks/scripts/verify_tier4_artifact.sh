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
# against the tier4 tree's own .uproject (cells/tier4-native.sh:181-183) and
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
#
# EVERY exit path must carry a named check, including the ones nothing here
# raises deliberately: both callers print "the tier4 plugin-artifact gate
# refused this run (named reason above)" on a non-zero exit
# (preflight.sh:316, cells/tier4-native.sh:77), so an unnamed abort --
# a python traceback, a git command answering nothing -- leaves the operator
# hunting for a line that was never printed. The `if ! VAR="$(...)"` wrappers
# below exist for exactly that.
#
# HOW FAR THAT GUARANTEE REACHES, stated precisely because fix round 1 asserted
# it while one line still broke it. Every command substitution here whose
# failure is REACHABLE is wrapped in `if !` (or captured with `|| true`) and
# then failed by name. MEASURED 2026-07-31: the source scan below was NOT. A
# bare `newest_line="$(find ... | awk ...)"` under `set -o pipefail` turned an
# unreadable subdirectory under a scanned root into exit 1 with EMPTY stdout,
# EMPTY stderr -- find's own message went to a `2>/dev/null` that has since
# been dropped -- and no named check whatsoever, which is worse than the
# python-traceback case this comment was written about. It is now
# tier4-source-scan. The bare substitutions that remain are unreachable by
# construction, not exhaustively listed here -- a per-line list goes stale the
# moment this comment moves. `stat -c %Y` on the two artifacts (check 2 proved
# they are regular files) is one instance; every other reads this script's own
# location or state a prior check validated. TIER4_STALE_ACK is normalised by
# parameter expansion alone, spawning nothing, for the same reason.
#
# ENV. TIER4_TREE is required; the other three are optional:
#   TIER4_PATCH_DIR  the registered patch set the worktree is compared against
#                    (defaults to this repo's benchmarks/patches/tier4-native)
#   TIER4_STALE_ACK  a REASON STRING -- never a boolean -- that downgrades the
#                    tier4-artifact-stale refusal to a loud, recorded WARN.
#                    See "STALENESS ACKNOWLEDGEMENT" below for why it exists.
#   TIER4_STALE_ACK_SOURCE_SHA256
#                    the tier4_source_sha256 the acknowledgement was granted
#                    for. MANDATORY whenever TIER4_STALE_ACK is set: it is what
#                    stops an acknowledgement transferring to a later run whose
#                    sources really did change. Every refusal that needs it
#                    prints this tree's current digest, so it is copy-pasteable
#                    without a second command and without a rebuild.
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
# (cells/tier4-native.sh:27,181), so the same file is the one that runs.
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
# can only ever cause a false REFUSAL -- never a false pass, which would be a
# filed measurement of unknown provenance. A false refusal is NOT free, though,
# and the first draft of this comment claimed it was ("a rebuild, loudly
# named"): a rebuild is forbidden mid-campaign, so the acknowledgement path
# documented below is what actually resolves one.
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
# `rev-parse --git-dir` is NOT sufficient, and the first draft of this script
# used it: it WALKS UP. A $TIER4_TREE that is merely a subdirectory of some
# other repository -- a pin pointing one level too deep, a tree unpacked inside
# a checkout -- answers with the ENCLOSING repo's git dir, and every identity
# below would then be that repo's. A WRONG identity in a manifest is worse than
# a missing one, because nothing downstream can tell it is wrong. So compare
# the discovered top level against the path actually asked for. `realpath` on
# both sides because the pin reaches the tree through $HOME, which may itself
# be a symlink, while git always answers with the resolved path.
TIER4_TOPLEVEL="$(git -C "$TIER4_TREE" rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$TIER4_TOPLEVEL" ] ||
  fail "tier4-tree: $TIER4_TREE is not a git work tree, so no tree identity can be
  recorded for the run (pins.yaml tier4_carla_fork.path)"
[ "$(realpath "$TIER4_TOPLEVEL")" = "$(realpath "$TIER4_TREE")" ] ||
  fail "tier4-tree: $TIER4_TREE is NOT the root of a git work tree -- it sits inside
  $TIER4_TOPLEVEL, whose sha and worktree state would be recorded as the tier4
  tree's identity (pins.yaml tier4_carla_fork.path)"

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
#
# FOUR STEPS, in this order for this reason: 3a resolves the source roots, 3b
# takes the newest source MTIME (the verdict's left-hand side), 3c digests the
# SAME file set by CONTENT, and 3d reads the acknowledgement. 3d comes last
# because the acknowledgement is BOUND to 3c's digest and every refusal it makes
# prints that digest -- an operator must never be told to supply a value the
# refusal itself withheld.
#
# STALENESS ACKNOWLEDGEMENT -- TIER4_STALE_ACK. Added in fix round 1 of Task
# 17b (2026-07-30) because this check, as first written, could refuse forever.
# BOUND to a source digest in fix round 2 (2026-07-31) because, as first
# acknowledged, it could stop refusing forever.
#
# WHY THE ACKNOWLEDGEMENT EXISTS. This check compares ARTIFACT MTIME against
# SOURCE MTIME over whole directory trees. Cell A's gate does not need the mtime
# axis at all: its tree's changes are COMMITTED, so it compares against HEAD's
# commit time (scripts/e2e/verify_editor_artifact.sh:24-25). The tier4 tree's
# campaign changes are UNCOMMITTED, which is why the mtime axis is used here and
# why it is unstable. Mtime moves under operations that change no content at
# all: benchmarks/patches/tier4-native/README.md:15-17 documents `git apply` of
# the three registered patches, which write CMake/Toolchain.cmake,
# LibCarla/CMakeLists.txt and LibCarla/source/carla/GlibcCompat.c -- ALL THREE
# under the roots scanned below. Re-applying them, a `git checkout`, a `stash
# pop`, or an editor save with no edit in it bumps a source mtime above the
# artifacts and refuses EVERY B-family run thereafter, content unchanged. Task
# 18 runs the B arm ten or more times; it cannot be blocked by that, and the
# only remedy this check first named -- a rebuild -- is FORBIDDEN mid-campaign,
# so a false refusal had no resolution at all.
#
# WHY IT IS BOUND. As first written the acknowledgement was BLANKET: any
# non-empty TIER4_STALE_ACK downgraded the refusal, on that run and on every
# later one. One `export` left in an operator's shell therefore turned this
# check off for a whole session -- including a run whose sources GENUINELY
# changed, which is precisely the case the check exists to refuse. The `unused`
# WARN does not catch that: it only fires when nothing is stale. Task 18 files
# ~20 B-family runs from one shell, so a sticky export is not a hypothesis.
#
# TIER4_STALE_ACK_SOURCE_SHA256 closes it. The acknowledgement carries the
# tier4_source_sha256 it was granted FOR and stops applying the moment the
# scanned sources' content moves: it is an assertion about ONE source state, so
# it expires with that state.
#
#   ACK unset                  -> refuse, exactly as before. The default, and
#                                 what an unattended run gets.
#   ACK="<reason>" + SHA=<this tree's digest>
#                              -> a stale artifact becomes a WARN on stderr and
#                                 the run proceeds. The reason AND the digest go
#                                 to stdout, so every affected run carries both
#                                 the condition and the state it was granted for
#                                 in its OWN manifest. Recorded, never hidden.
#   ACK="" / blank             -> named refusal, tier4-stale-ack-unexplained.
#                                 No reason, no acknowledgement. Set-but-empty
#                                 is the shape a typo and an unset lookup both
#                                 take, and an acknowledgement nobody can read
#                                 later is indistinguishable from hiding one.
#   ACK set, SHA unset/blank   -> named refusal, tier4-stale-ack-unbound.
#   ACK set, SHA != this tree  -> named refusal, tier4-stale-ack-mismatch.
#
# (SHA set with ACK unset is ignored, and tier4_stale_ack=none records that. It
# cannot hide anything: with no reason there is no acknowledgement, so a stale
# artifact still meets the full tier4-artifact-stale refusal, which prints the
# exact pair of exports to make.)
#
# All three acknowledgement refusals are EAGER -- they fire whether or not
# anything is stale. Two reasons. (1) tier4-stale-ack-unexplained already
# behaved that way and has a test pinning it: a malformed acknowledgement is
# never silently ignored. (2) The keys are filed on EVERY run, so a manifest
# recording tier4_stale_ack_reason for a source state its run did not have is a
# corrupt record even when nothing was suppressed. The remedy is always one line
# and the refusal always prints it: unset the two variables, or re-bind them to
# the digest shown. Never a rebuild.
#
# WHAT THE BINDING DOES NOT DO. It does not make the acknowledgement
# self-justifying. The digest is this tree's own and every refusal prints it, so
# an operator can always copy it out -- deliberately, because a false refusal
# must have a remedy. What the binding buys is NON-TRANSFERABILITY across source
# states. What makes the reason checkable rather than merely asserted is still
# tier4_source_sha256 in the manifest, compared against the last run that passed
# with no acknowledgement at all.
#
# SCOPE: check 3 only. Check 4 (artifact older than HEAD's commit) stays
# unacknowledgeable, because it can only fire when HEAD MOVED -- a real content
# change, not mtime drift.
# ---------------------------------------------------------------------------

# --- 3a: which of the scanned roots exist ----------------------------------
present=()
for p in "${SOURCE_PATHS[@]}"; do
  [ -e "$p" ] && present+=("$p")
done
[ "${#present[@]}" -gt 0 ] ||
  fail "tier4-source-roots: none of ${SOURCE_PATHS[*]} exist, so artifact staleness
  cannot be judged at all -- $TIER4_TREE is not a CARLA tree"

# --- 3b: the newest source mtime -------------------------------------------
# The maximum is taken by awk, NOT by `sort -rn | head -1`: `head` closes the
# pipe on its first line, SIGPIPE-kills `sort`, and under `set -o pipefail`
# that makes the whole command exit 141 -- the same trap cells/tier4-native.sh
# documents for `ss | grep -q`. Measured here 2026-07-30: the first draft of
# this script exited 141 on the real tree.
#
# `if !` and not a bare assignment, and no `2>/dev/null` on the find: pipefail
# makes a find that cannot read one subdirectory fail the whole pipeline, and as
# a bare assignment under `set -e` that aborted the script with EMPTY stdout and
# EMPTY stderr -- measured 2026-07-31, exit 1, no named check at all. find's own
# message is the operator's evidence and now reaches stderr, ahead of the name.
if ! newest_line="$(find "${present[@]}" -type f -printf '%T@ %p\n' |
  awk '$1 + 0 > max { max = $1 + 0; line = $0 } END { if (line != "") print line }')"; then
  fail "tier4-source-scan: scanning ${present[*]} for the newest source failed (the
  scanner's own error is above this line), so artifact staleness could not be judged.
  -> an unreadable directory under a scanned root is the usual cause. Fix the
     permissions rather than skipping the gate: a partial scan would judge
     staleness against a SUBSET of the sources and pass a stale artifact."
fi
[ -n "$newest_line" ] ||
  fail "tier4-source-roots: no files under ${present[*]}"
NEWEST_SRC_EPOCH="${newest_line%% *}"
NEWEST_SRC_EPOCH="${NEWEST_SRC_EPOCH%%.*}"
NEWEST_SRC_PATH="${newest_line#* }"

# --- 3c: content digest of the same file set -------------------------------
# CONTENT digest of the SAME file set 3b just judged by mtime. This is what
# makes an acknowledged mtime staleness provable instead of asserted: two runs
# whose tier4_source_sha256 agree were built from byte-identical sources, no
# matter what their mtimes did in between. It does NOT prove freshness on its
# own -- nothing here records the digest the artifacts were built FROM -- so it
# is a comparison across runs, never a substitute for 3b's verdict.
#
# Computed HERE rather than in the identity block below, where fix round 1 put
# it, because 3d's refusals have to print it: an acknowledgement that must carry
# a digest the refusal withheld would be unobtainable without a passing run, and
# on a stale tree there is no passing run to get it from.
#
# Same membership rule as `find "${present[@]}" -type f`: regular files only,
# symlinks skipped on both sides. Paths are relativised to the tree so a moved
# or renamed checkout digests identically, and sorted so directory order cannot
# change the answer. `os.walk` gets an onerror that RAISES: its default is to
# swallow the error and walk on, which would digest a subset of the sources and
# call it the source state -- the same silent-partial-scan failure 3b now names.
# That onerror is belt-and-braces and is NOT covered by any test, deliberately
# recorded as such: 3b's find fails on an unreadable DIRECTORY first, so nothing
# can reach this walk with one in place while 3b precedes it. Deleting the
# onerror leaves the whole module green (mutation `source-digest-walks-on`,
# 2026-07-31), so it rests on reading, not on a test. It is kept because 3b's
# membership rule and this one are maintained separately and only match today.
# MEASURED 2026-07-31 on the real tree: 1094 regular files, 6.3 MB of content
# (8.8 MB as `du` reports it, which is the figure the round-1 comment carried)
# under the four roots, and the whole gate -- 3b's find, this digest, and every
# digest in the identity block -- runs in 0.07-0.08 s wall, five consecutive
# invocations. Splitting this digest out of the identity block costs one extra
# python start-up, which is the whole of the 0.01 s over the 0.06-0.07 s round 1
# measured.
TIER4_SOURCE_ROOTS="$(printf '%s\n' "${present[@]}")"
if ! SOURCE_SHA256="$(
  TIER4_TREE="$TIER4_TREE" TIER4_SOURCE_ROOTS="$TIER4_SOURCE_ROOTS" python3 - <<'PY'
import hashlib
import os


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def reraise(err):
    raise err


tree = os.environ["TIER4_TREE"]
roots = [p for p in os.environ["TIER4_SOURCE_ROOTS"].splitlines() if p]
source_files = []
for root in roots:
    if os.path.isfile(root):
        source_files.append(root)
        continue
    for dirpath, dirnames, filenames in os.walk(root, onerror=reraise):
        dirnames.sort()
        for name in sorted(filenames):
            candidate = os.path.join(dirpath, name)
            if os.path.isfile(candidate) and not os.path.islink(candidate):
                source_files.append(candidate)
h = hashlib.sha256()
for rel in sorted(os.path.relpath(p, tree) for p in source_files):
    h.update(rel.encode() + b"\0")
    h.update(sha256_file(os.path.join(tree, rel)).encode() + b"\0")
print(h.hexdigest())
PY
)"; then
  fail "tier4-source-digest: the scanned sources under ${present[*]} could not be
  digested (the reader's own error is above this line).
  -> an unreadable FILE under a scanned root is the usual cause, and it is fatal
     rather than skippable: without this digest an acknowledged staleness would
     rest on nothing checkable, and every run would record a source identity
     covering only the files that happened to be readable."
fi

# --- 3d: the acknowledgement, bound to 3c's digest --------------------------
STALE_ACK_STATE=none
STALE_ACK_REASON=-
STALE_ACK_SOURCE=-
if [ -n "${TIER4_STALE_ACK+set}" ]; then
  # Newlines, carriage returns and tabs collapse to spaces and the ends are
  # trimmed -- by parameter expansion alone, so this spawns nothing and has no
  # exit path (see the named-check note in the header). stdout here is a
  # KEY=VALUE stream that preflight.sh forwards verbatim into the manifest
  # (run.sh:481 splits on the first `=` per LINE), so a reason carrying a newline
  # would silently become a second, junk placement key. Spaces inside the value
  # are fine and are preserved.
  STALE_ACK_REASON="${TIER4_STALE_ACK//[$'\n\r\t']/ }"
  STALE_ACK_REASON="${STALE_ACK_REASON#"${STALE_ACK_REASON%%[![:space:]]*}"}"
  STALE_ACK_REASON="${STALE_ACK_REASON%"${STALE_ACK_REASON##*[![:space:]]}"}"
  [ -n "$STALE_ACK_REASON" ] ||
    fail "tier4-stale-ack-unexplained: TIER4_STALE_ACK is set but carries no reason.
  -> set it to WHY the mtime staleness is acceptable -- it is written into every
     affected run's manifest as placement.tier4_stale_ack_reason -- or unset it
     and let tier4-artifact-stale refuse."
  # All whitespace removed, not just the ends: this is a hex digest, so there is
  # no interior whitespace to preserve and a wrapped copy-paste should still bind.
  STALE_ACK_SOURCE="${TIER4_STALE_ACK_SOURCE_SHA256:-}"
  STALE_ACK_SOURCE="${STALE_ACK_SOURCE//[[:space:]]/}"
  [ -n "$STALE_ACK_SOURCE" ] ||
    fail "tier4-stale-ack-unbound: TIER4_STALE_ACK is set but
  TIER4_STALE_ACK_SOURCE_SHA256 is not, so the acknowledgement is bound to no
  source state and would apply to every later run -- including one whose sources
  really did change, which is the case tier4-artifact-stale exists to refuse.
  -> re-export it together with THIS tree's digest:
       export TIER4_STALE_ACK_SOURCE_SHA256=$SOURCE_SHA256
     (the same value this gate emits as tier4_source_sha256 on every run it lets
     through), or unset TIER4_STALE_ACK and let tier4-artifact-stale refuse."
  [ "$STALE_ACK_SOURCE" = "$SOURCE_SHA256" ] ||
    fail "tier4-stale-ack-mismatch: TIER4_STALE_ACK was granted for a DIFFERENT
  source state and no longer applies.
    granted for:  $STALE_ACK_SOURCE
    this tree:    $SOURCE_SHA256
    reason given: $STALE_ACK_REASON
  The scanned sources' CONTENT has moved since that acknowledgement was written,
  so the \"the mtime moved but the content did not\" claim it carries is not true
  of this tree. Named separately from tier4-artifact-stale on purpose: you are
  being told the acknowledgement EXPIRED, not merely that something is stale.
  -> if the new state is one you still mean to acknowledge, re-export
       export TIER4_STALE_ACK_SOURCE_SHA256=$SOURCE_SHA256
     with a reason that describes THAT state; otherwise unset TIER4_STALE_ACK."
  STALE_ACK_STATE=unused
fi

# --- 3e: the verdict -------------------------------------------------------
# Accumulated as a string rather than an array: `"${arr[@]}"` on an EMPTY array
# is an unbound-variable error under `set -u` on bash < 4.4, and this script has
# to keep working on whatever the host ships.
STALE_LIST=""
STALE_DETAIL=""
for so in "$EDITOR_SO" "$ROS2_SO"; do
  so_mtime="$(stat -c %Y "$so")"
  if [ "$so_mtime" -lt "$NEWEST_SRC_EPOCH" ]; then
    STALE_LIST="${STALE_LIST:+$STALE_LIST,}$(basename "$so")"
    STALE_DETAIL="$STALE_DETAIL
  $so ($so_mtime) is OLDER than the newest source it is built from,
  $NEWEST_SRC_PATH ($NEWEST_SRC_EPOCH)."
  fi
done

if [ -n "$STALE_LIST" ]; then
  if [ "$STALE_ACK_STATE" = "none" ]; then
    fail "tier4-artifact-stale:$STALE_DETAIL
  Two remedies, and the SECOND is the one to reach for mid-campaign:
  -> rebuild the tier4 fork's plugin -- a stale .so publishes a different wire
     format from the source the record cites; or
  -> if the mtime moved with the CONTENT unchanged (re-applying the registered
     patches, a git checkout, a stash pop and an editor save all do that --
     benchmarks/patches/tier4-native/README.md:15-17), acknowledge it with BOTH
     of these -- the reason and the source state it is granted for:
       export TIER4_STALE_ACK=\"<why this staleness is acceptable>\"
       export TIER4_STALE_ACK_SOURCE_SHA256=$SOURCE_SHA256
     The refusal becomes a WARN and both values are written into the run's
     manifest. The digest is THIS tree's, printed here so that obtaining it needs
     neither a rebuild nor a passing run; it is what stops the acknowledgement
     carrying over to a later run whose sources really did change. Compare
     tier4_source_sha256 against the last run that passed WITHOUT an
     acknowledgement to show the content really is unchanged."
  fi
  STALE_ACK_STATE=applied
  note "WARN: tier4-artifact-stale ACKNOWLEDGED -- this run is NOT blocked.$STALE_DETAIL
  reason: $STALE_ACK_REASON
  granted for tier4_source_sha256=$STALE_ACK_SOURCE, which is this tree's own, so
  the acknowledgement stops applying as soon as the scanned sources' content moves.
  Recorded as placement.tier4_stale_ack=applied, .tier4_stale_ack_reason,
  .tier4_stale_ack_source_sha256 and .tier4_stale_ack_artifacts on THIS run's
  manifest, so every measurement made under the acknowledgement carries it.
  tier4_source_sha256 is what makes the reason checkable rather than asserted."
else
  note "OK: tier4 plugin artifacts are newer than every source under ${present[*]}"
  # Loud in the other direction too: an acknowledgement that was set and not
  # needed is a leftover export, and the next operator should know it is armed.
  if [ "$STALE_ACK_STATE" = "unused" ]; then
    note "WARN: TIER4_STALE_ACK is set but nothing is stale, so it was NOT used
  (recorded as placement.tier4_stale_ack=unused). Reason given: $STALE_ACK_REASON
  It is bound to this tree's current tier4_source_sha256, so it is armed for a
  later run in this shell -- unset it if that is not what you want."
  fi
fi

# ---------------------------------------------------------------------------
# Check 4 -- tier4-artifact-older-than-head. Cell A's own check, kept for
# parity, and WEAK HERE ON PURPOSE: the tier4 tree carries its campaign changes
# UNCOMMITTED (the registered patch set), so its HEAD timestamp says nothing
# about when the code that runs was last edited. Check 3 is the load-bearing
# one; this one only catches the case of the tree being fast-forwarded onto a
# newer upstream commit without a rebuild.
# ---------------------------------------------------------------------------
#
# `|| true` plus an emptiness test, NOT a bare command substitution: on a repo
# with no commit yet, `git show HEAD` fails, and under `set -e` an assignment
# from a failing substitution aborts the script with git's own error and NO
# named check -- while both callers go on to print "named reason above". Same
# reasoning as the identity wrapper further down.
#
# NAMED tier4-tree-no-head, not tier4-tree. It was tier4-tree until fix round 2
# (2026-07-31), which is check 1's name too -- so the test covering this path
# asserted a string that check 1 also prints, and would have kept passing if the
# refusal had migrated to check 1, i.e. if the behaviour it documents had gone
# away. Distinct names are what let a test pin WHICH check refused. Note that a
# substring assertion still cannot: "tier4-tree" is a prefix of this name, which
# is why tests compare the whole name (see named_check() in the test module).
COMMIT_EPOCH="$(git -C "$TIER4_TREE" show -s --format=%ct HEAD 2>/dev/null || true)"
[ -n "$COMMIT_EPOCH" ] ||
  fail "tier4-tree-no-head: $TIER4_TREE has no HEAD commit, so neither its sha nor its
  commit time can be recorded for the run (pins.yaml tier4_carla_fork.sha)"
for so in "$EDITOR_SO" "$ROS2_SO"; do
  so_mtime="$(stat -c %Y "$so")"
  if [ "$so_mtime" -lt "$COMMIT_EPOCH" ]; then
    fail "tier4-artifact-older-than-head: $so ($so_mtime) is OLDER than the tier4
  tree's HEAD commit ($COMMIT_EPOCH).
  -> rebuild the tier4 fork's plugin before any B-family run. Deliberately NOT
     acknowledgeable via TIER4_STALE_ACK: this can only fire when HEAD moved,
     which is a real content change and not mtime drift."
  fi
done

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
# pre-registered supports. The digests below make the state durable either way,
# which is the thing that was missing.
#
# `if ! VAR="$(...)"` and not a bare assignment: an assignment from a failing
# command substitution aborts under `set -e` with whatever python printed and NO
# `PREFLIGHT FAIL: <check>` line, while preflight.sh:316 and
# cells/tier4-native.sh:77 both then tell the operator to read a "named reason
# above" that does not exist. In a condition, `set -e` does not fire, so the
# named check below is reached on every failure of the block. python's own
# traceback still goes to stderr, ahead of the named line, because only stdout
# is captured here.
# ---------------------------------------------------------------------------
if ! TIER4_IDENTITY_KV="$(
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

# -uall, NOT the default -unormal. -unormal COLLAPSES a wholly untracked
# directory to one `dir/` entry, so a future registered patch that creates files
# in a NEW directory would compare `dir/` against that patch's `+++ b/dir/file`
# paths and report a spurious `diverged:` -- refusing nothing, but filing a
# false divergence on every run. The reason -unormal happened to work today is
# narrow: patch 0002's GlibcCompat.c lands in an ALREADY-TRACKED directory.
porcelain = subprocess.run(
    ["git", "-C", tree, "status", "--porcelain", "-uall"],
    capture_output=True,
    text=True,
    check=True,
).stdout

# `XY <path>`; a rename is `R  <old> -> <new>` and the NEW path is the one that
# describes the tree as it stands. `??` marks untracked, which the content
# digest below has to read from disk rather than from `git diff`.
dirty = set()
untracked = set()
for line in porcelain.splitlines():
    code, path = line[:2], line[3:]
    if " -> " in path:
        path = path.split(" -> ", 1)[1]
    path = path.strip().strip('"')
    dirty.add(path)
    if code == "??":
        untracked.add(path)

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


# CONTENT digest of the divergence from HEAD, not just its shape.
# tier4_worktree_paths_sha256 above hashes only the sorted PATH list, so any
# edit to an already-dirty file left it unchanged -- including an edit to
# PythonAPI/examples/autoware_demo.py, registered patch 0003, the file that sets
# --lidar-pps and --lidar-rotation-hz. That is the sensor configuration
# benchmarks/results/B/PROVENANCE.md section 4 leaves open, so the paths-only
# digest reproduced, for the configuration half, the very "a path is not an
# identity" gap this gate exists to close.
#
# `git diff HEAD --binary` covers staged and unstaged changes to TRACKED files
# in one reproducible byte stream; untracked files are absent from it and are
# appended by content, path-tagged and sorted, so a rename between two untracked
# files changes the digest.
h = hashlib.sha256()
h.update(subprocess.run(
    ["git", "-C", tree, "diff", "HEAD", "--binary"],
    capture_output=True, check=True,
).stdout)
for path in sorted(untracked):
    h.update(b"\0untracked\0" + path.encode() + b"\0")
    full = os.path.join(tree, path)
    # -uall lists files, not directories, so this is a guard against a symlink
    # or a socket rather than an expected shape.
    if os.path.isfile(full) and not os.path.islink(full):
        h.update(sha256_file(full).encode())
    else:
        h.update(b"<not-a-regular-file>")
worktree_content_sha256 = h.hexdigest()

print("tier4_git_sha=" + subprocess.run(
    ["git", "-C", tree, "rev-parse", "HEAD"],
    capture_output=True, text=True, check=True,
).stdout.strip())
print("tier4_worktree=" + state)
print("tier4_worktree_paths_sha256=" + hashlib.sha256(
    "\n".join(sorted(dirty)).encode()
).hexdigest())
print("tier4_worktree_content_sha256=" + worktree_content_sha256)
print("tier4_plugin_sha256=" + sha256_file(os.environ["EDITOR_SO"]))
print("tier4_ros2_native_sha256=" + sha256_file(os.environ["ROS2_SO"]))
PY
)"; then
  fail "tier4-identity: the tree-identity reader failed for $TIER4_TREE (its own
  error is above this line).
  -> a run may not be filed without an identity for the tree that produced it,
     which is the whole point of this gate; fix the tree or the patch directory
     ($TIER4_PATCH_DIR) rather than skipping the gate."
fi

echo "$TIER4_IDENTITY_KV"
echo "tier4_source_sha256=$SOURCE_SHA256"
echo "tier4_plugin_mtime=$(stat -c %Y "$EDITOR_SO")"
echo "tier4_ros2_native_mtime=$(stat -c %Y "$ROS2_SO")"
echo "tier4_newest_source_mtime=$NEWEST_SRC_EPOCH"
# ALWAYS emitted, all four, exactly as preflight.sh emits map_bundle_pin
# unconditionally: an omitted key would make "no acknowledgement was needed" and
# "this gate is an older version that had none" the same observation in a
# manifest. `none` / `unused` / `applied` distinguishes not-set from
# set-but-not-needed from actually-used.
#
# The fourth outcome the acknowledgement can have -- MISMATCHED, granted for a
# source state that is not this tree's -- is deliberately absent from this
# domain, because it is a REFUSAL: the run never starts and no manifest is
# written, so no filed value could carry it. What makes it reconstructible from
# the record instead is the pair below: tier4_stale_ack_source_sha256 alongside
# tier4_source_sha256 on every filed run. For an `applied` acknowledgement the
# two are equal by construction (a mismatch refuses), so the honest description
# of the key is not "proof the ack matched" but "the binding was required and
# satisfied" -- which is exactly what distinguishes such a manifest from one
# written by the blanket-acknowledgement version of this gate, where the key is
# absent altogether.
echo "tier4_stale_ack=$STALE_ACK_STATE"
echo "tier4_stale_ack_reason=$STALE_ACK_REASON"
echo "tier4_stale_ack_source_sha256=$STALE_ACK_SOURCE"
echo "tier4_stale_ack_artifacts=${STALE_LIST:--}"

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
