#!/usr/bin/env bash
# Community-acceptance rubric evidence snapshot (docs/evaluation/rubric.md).
#
# Every command below is labeled with the rubric criterion + approach cell it
# fills, so re-running this script re-derives every value in the filled
# table -- there is no number in rubric.md that isn't traceable to a line
# here (a few cells are architectural facts a command can't produce; those
# are marked MANUAL OBSERVATION and carry a URL instead of a command).
#
# WHY THE CRITERION LIST IS NOT DERIVED FROM THIS SCRIPT: the rubric's
# criteria + directions were committed in a PRIOR commit
# (docs(evaluation): pre-register acceptance rubric criteria) before this
# script existed. Running this script never edits that criterion list --
# see the note at the top of rubric.md.
#
# THE FORK-INHERITED-HISTORY TRAP (read before trusting a raw contributor
# count): tier4/carla-autoware-native is a GitHub *fork* of
# carla-simulator/carla (`gh api repos/tier4/carla-autoware-native --jq
# .fork,.parent.full_name` -> true, carla-simulator/carla). Its
# /contributors endpoint therefore returns carla-simulator/carla's entire
# ~166-person upstream contributor list, not tier4's native-integration
# authors -- naively quoting that number as tier4's "maintainer count" would
# be a fabricated-by-API-shape error, not a finding. Every activity /
# bus-factor cell for tier4-native below is instead computed over the LOCAL
# commit range `upstream/ue5-dev..tier4/autoware-support` (the same range
# the design spec's "305 commits ahead of ue5-dev" figure uses), which
# isolates tier4's own delta from CARLA's inherited history. The same
# reasoning applies to the extension's required fork delta.
#
# THIS SCRIPT DOES NOT REGENERATE A FILED FIGURE -- read this before trusting
# a re-run against rubric.md's numbers. Unlike everything under
# benchmarks/analysis/, its output is a DATED SNAPSHOT of moving state:
#   (a) every non-clone cell is a live `gh api` / `gh search prs` against
#       GitHub at the moment of the run (PR counts, ruleset ids, actions/runs
#       totals, the bridge's path-scoped commit list -- all move);
#   (b) SINCE_90D / SINCE_365D below are computed from the RUN DATE, so every
#       "N in 90 days" cell is a function of when you run this;
#   (c) the two local clones' branches are moving refs.
# For (c) the script now prints `git rev-parse` for BOTH endpoints beside every
# `rev-list --count`, so a re-run is comparable to the SHAs rubric.md pins in
# Criteria 3 and 6 ("Appendix: snapshot audit trail"). For (a) and (b) there is
# no remedy but the run date -- REDIRECT THIS SCRIPT AND COMMIT THE LOG:
#   bash scripts/evaluation/rubric_snapshot.sh > /tmp/rubric-snapshot.log 2>&1
# rubric.md's audit-trail appendix exists because the 2026-08-05T02:13 UTC run
# was NOT captured that way and cannot be reconstructed.
#
# PREREQUISITES:
#   - `gh` authenticated (gh auth status) with no special scopes beyond
#     public repo read.
#   - Two LOCAL git clones. This script is READ-ONLY against them by default:
#     it never fetches unless you pass --fetch (see below), because fetching
#     the very refs whose counts you are reporting MUTATES the repositories
#     the numbers are computed over -- `fetch --prune` in particular deletes
#     remote-tracking refs and is not idempotent with respect to what was
#     there before. That is the same class of defect as an analysis script
#     rewriting results/; it just happens outside this repo.
#       EXT_FORK_CLONE   (default ~/src/carla-autoware-integration), on
#                        branch feat/autoware-seminative-phase-b
#       TIER4_FORK_CLONE (default ~/src/carla-autoware-native), with the
#                        `tier4` and `upstream` remotes already fetched
#     Both paths are documented HERE (they were previously documented only in
#     an untracked CLAUDE.md, i.e. a pointer to one operator's machine). In
#     that operator's setup both are git worktrees sharing one shallow clone's
#     .git (`~/src/carla`); any independent clone with the same branches and
#     remotes present reproduces the same rev-list counts -- EXCEPT the bonus
#     check below, which additionally needs $TIER4_FORK_BRANCH to resolve
#     INSIDE $EXT_FORK_CLONE and now says so by name instead of falling
#     through silently.
#     If a clone is missing, its section prints a loud MISSING line and the
#     rest of the snapshot still runs. The script still exits 0 in that case,
#     so ALWAYS grep the transcript for "MISSING" before transcribing values:
#     a skipped clone silently removes Criteria 3, 6 and 7's fork halves.
#
# USAGE: bash scripts/evaluation/rubric_snapshot.sh [--fetch]
set -euo pipefail

DO_FETCH=0
for arg in "$@"; do
  case "$arg" in
    --fetch) DO_FETCH=1 ;;
    *) echo "unknown argument: $arg (usage: $0 [--fetch])" >&2; exit 2 ;;
  esac
done

EXT_REPO="autowarefoundation/carla-autoware-extension"
TIER4_REPO="tier4/carla-autoware-native"
BRIDGE_REPO="autowarefoundation/autoware_universe"
BRIDGE_PATH="simulator/autoware_carla_interface"

EXT_FORK_CLONE="${EXT_FORK_CLONE:-$HOME/src/carla-autoware-integration}"
EXT_FORK_BRANCH="${EXT_FORK_BRANCH:-feat/autoware-seminative-phase-b}"
TIER4_FORK_CLONE="${TIER4_FORK_CLONE:-$HOME/src/carla-autoware-native}"
TIER4_FORK_BRANCH="${TIER4_FORK_BRANCH:-tier4/autoware-support}"
# The repo's ACTUAL default branch, queried alongside autoware-support so the
# activity cells can name which ref is stalled and which is active.
TIER4_MAIN_BRANCH="${TIER4_MAIN_BRANCH:-tier4/main}"
UPSTREAM_BASE="${UPSTREAM_BASE:-upstream/ue5-dev}"

NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SINCE_90D="$(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ)"
SINCE_365D="$(date -u -d '365 days ago' +%Y-%m-%dT%H:%M:%SZ)"

hdr() { printf '\n=== %s ===\n' "$1"; }

# Every rev-list --count in this script goes through this helper, so no count
# is ever printed without both of its endpoints resolved to a SHA. Fix-round-2
# finding: rubric.md quoted 219 / 305 / 121 against MOVING refs that the script
# itself fetched before counting, so not even an operator holding both clones
# could confirm a number after the fact.
count_range() {
  local clone="$1" base="$2" head="$3"
  echo "git rev-list --count $base..$head"
  echo "  $base = $(git -C "$clone" rev-parse "$base" 2>/dev/null || echo '(unresolvable)')"
  echo "  $head = $(git -C "$clone" rev-parse "$head" 2>/dev/null || echo '(unresolvable)')"
  git -C "$clone" rev-list --count "$base..$head"
}

# Opt-in only. See the PREREQUISITES note on why fetching is not the default.
maybe_fetch() {
  local clone="$1"; shift
  if [ "$DO_FETCH" -eq 1 ]; then
    echo "(--fetch: git -C $clone fetch $*)"
    git -C "$clone" fetch "$@" --quiet || true
  else
    echo "(no fetch -- refs are read as-is; pass --fetch to refresh them first)"
  fi
}

# gh search prs is CAP-SILENT: it returns exactly --limit results with no
# indication a real total was truncated to fit. Fix-round-1 finding: the
# JArmandoAnaya cell was originally captured at --limit 50 and returned
# EXACTLY 50 (38 merged + 12 open + 0 closed) -- a truncation artifact that
# happened to erase the 2 closed-unmerged PRs the account actually has,
# erring in the extension's favor. Every author-scoped PR search below goes
# through this helper so every count carries an explicit "did we hit the
# cap" check instead of silently trusting a round number.
pr_state_breakdown() {
  local repo="$1" author="$2" limit="${3:-200}"
  gh search prs --repo "$repo" --author "$author" --limit "$limit" --json state --jq \
    "(group_by(.state) | map({state: .[0].state, n: length})),
     (\"total=\" + (length|tostring)),
     (if length >= $limit then \"WARNING: result count == --limit=$limit -- may be truncated, RAISE THE LIMIT and re-run\" else \"OK: total is below --limit=$limit, count is exhaustive\" end)"
}

# The `gh api .../commits` calls below are cap-silent in exactly the same way,
# and were left unguarded when the PR searches above were fixed. `per_page`
# maxes out at 100 and a single unpaginated request returns at most that many
# items with no marker that a longer history was cut off -- so a commit count
# that lands on exactly 100 is a FLOOR, not a total, and reading it as a total
# would understate an active repo (the opposite direction of the JArmandoAnaya
# truncation above, but the same class of error). Every commits call routes
# through this helper so the cap check is printed next to the figure it
# qualifies. $2 is the jq expression producing the figure itself.
gh_api_commits_capped() {
  local url="$1" expr="$2"
  gh api "$url" --jq \
    "($expr),
     (if length >= 100 then \"WARNING: response length == per_page cap of 100 -- TRUNCATED; the figure above is a FLOOR, not a total. Paginate (--paginate) and re-run\" else \"OK: below the per_page cap of 100, the figure above is exhaustive\" end)"
}

hdr "Snapshot retrieval time (record this as the table's retrieval date)"
echo "NOW_UTC=$NOW_UTC"
echo "90-day cutoff (SINCE_90D)=$SINCE_90D"
echo "365-day cutoff (SINCE_365D)=$SINCE_365D"

# ---------------------------------------------------------------------------
# Criterion 10 (license) + repo-level facts reused by several other criteria.
# ---------------------------------------------------------------------------
hdr "Criterion 10 (license) + repo metadata -- Extension"
gh api "repos/$EXT_REPO" --jq \
  '"created_at=" + .created_at, "pushed_at=" + .pushed_at, "license=" + .license.spdx_id, "forks_count=" + (.forks_count|tostring), "has_issues=" + (.has_issues|tostring), "open_issues_count=" + (.open_issues_count|tostring)'

hdr "Criterion 10 (license) + repo metadata -- tier4-native"
gh api "repos/$TIER4_REPO" --jq \
  '"created_at=" + .created_at, "pushed_at=" + .pushed_at, "license=" + .license.spdx_id, "forks_count=" + (.forks_count|tostring), "has_issues=" + (.has_issues|tostring), "open_issues_count=" + (.open_issues_count|tostring), "is_fork=" + (.fork|tostring), "fork_parent=" + .parent.full_name'

hdr "Criterion 10 (license) + repo metadata -- Bridge host repo (autoware_universe)"
gh api "repos/$BRIDGE_REPO" --jq \
  '"created_at=" + .created_at, "license=" + .license.spdx_id, "forks_count=" + (.forks_count|tostring), "has_issues=" + (.has_issues|tostring)'

hdr "Criterion 10 (license) -- Bridge package.xml maintainers + license"
gh api "repos/$BRIDGE_REPO/contents/$BRIDGE_PATH/package.xml" --jq '.content' \
  | base64 -d | grep -E '<maintainer|<license'

# ---------------------------------------------------------------------------
# Criterion 1/2 (governance/ownership, who must accept it): CODEOWNERS +
# merge rulesets. GitHub's modern rulesets API, not the classic branch-
# protection endpoint (the classic endpoint 404s for these repos because
# they use rulesets).
# ---------------------------------------------------------------------------
hdr "Criteria 1-2 -- Extension: main ruleset (status checks only, no required review)"
gh api "repos/$EXT_REPO/rulesets" --jq '.[] | .name + " (" + .enforcement + ")"'
EXT_RULESET_ID="$(gh api "repos/$EXT_REPO/rulesets" --jq '.[] | select(.name=="main") | .id')"
gh api "repos/$EXT_REPO/rulesets/$EXT_RULESET_ID" --jq '.rules[] | .type'

hdr "Criteria 1-2 -- Extension: no CODEOWNERS file (404 expected and informative)"
gh api "repos/$EXT_REPO/contents/CODEOWNERS" >/dev/null 2>&1 \
  && echo "CODEOWNERS present" \
  || echo "CODEOWNERS absent (404) -- no formal reviewer gate beyond the ruleset's required status checks"

# Fix-round-1 finding: chasing a ruleset by NAME and reading its
# conditions/rules is the wrong method -- a repo can have several rulesets,
# each covering a different branch set with different rules, and a reader
# (or an earlier run of this very script) can accidentally attribute one
# ruleset's rules to a branch actually governed by a different one. GitHub's
# per-branch EFFECTIVE-rules endpoint (`rules/branches/<branch>`) is the
# authoritative source: it returns the union of whatever rulesets actually
# apply to that exact branch, with no name-matching required.
hdr "Criteria 1-2 -- tier4-native: the two repo-level rulesets (context only -- see the per-branch check below for what actually applies)"
gh api "repos/$TIER4_REPO/rulesets" --jq '.[] | (.id|tostring) + " " + .name + " (" + .enforcement + ")"'

hdr "Criteria 1-2 -- tier4-native: EFFECTIVE rules on autoware-support itself (authoritative -- not a ruleset chased by name)"
echo "gh api repos/$TIER4_REPO/rules/branches/autoware-support"
gh api "repos/$TIER4_REPO/rules/branches/autoware-support" --jq '[.[].type]'
# Fix-round-2 finding: printing only the rule TYPES establishes that those rule
# types are configured, NOT that the branch is frozen for the people who
# maintain it -- a ruleset's bypass_actors list can exempt an org/team/app
# entirely. rubric.md Criterion 2 now scopes the word "frozen" accordingly.
# Enumerated here so the scope is measured rather than assumed:
echo "-- bypass actors per ruleset that reaches this branch (empty list == no exemptions) --"
for rs in $(gh api "repos/$TIER4_REPO/rules/branches/autoware-support" --jq '[.[].ruleset_id] | unique | .[]'); do
  echo "-- ruleset $rs --"
  gh api "repos/$TIER4_REPO/rulesets/$rs" --jq '.name, ([.bypass_actors[]? | {actor_type, actor_id, bypass_mode}])' || echo "(ruleset $rs not readable with this token)"
done
echo "(expect: creation, update, deletion, non_fast_forward -- i.e. the branch is FROZEN"
echo " against updates/deletion/force-push, but NO pull_request rule reaches it, so no"
echo " approving-review gate applies here despite the repo having a ruleset elsewhere that"
echo " requires one -- that ruleset's ref_name.include list does not cover autoware-support)"

hdr "Criteria 1-2 -- tier4-native: inherited CODEOWNERS (context; see above for whether it's ever consulted on autoware-support)"
gh api "repos/$TIER4_REPO/contents/.github/CODEOWNERS" --jq '.content' | base64 -d

hdr "Criteria 1-2 -- Bridge: autoware_universe main ruleset (1 CODEOWNER approval required) + package CODEOWNERS line"
BRIDGE_RULESET_ID="$(gh api "repos/$BRIDGE_REPO/rulesets" --jq '.[] | select(.name=="main - approval") | .id')"
gh api "repos/$BRIDGE_REPO/rulesets/$BRIDGE_RULESET_ID" --jq '.rules[] | select(.type=="pull_request") | .parameters | "required_approving_review_count=" + (.required_approving_review_count|tostring), "require_code_owner_review=" + (.require_code_owner_review|tostring)'
gh api "repos/$BRIDGE_REPO/contents/.github/CODEOWNERS" --jq '.content' | base64 -d | grep -F "$BRIDGE_PATH"

# ---------------------------------------------------------------------------
# Criterion 3 (total unmerged artifact set) -- the 216/305-style fork deltas.
# Reproduces the design spec's own method exactly: git rev-list --count
# against upstream/ue5-dev. The spec quotes 216 (extension) / 305 (tier4);
# this script's job is to report the FRESH count, not the spec's snapshot.
# ---------------------------------------------------------------------------
hdr "Criterion 3 -- tier4-native fork delta (spec quotes 305)"
if [ -d "$TIER4_FORK_CLONE" ]; then
  maybe_fetch "$TIER4_FORK_CLONE" tier4 --prune
  maybe_fetch "$TIER4_FORK_CLONE" upstream ue5-dev
  count_range "$TIER4_FORK_CLONE" "$UPSTREAM_BASE" "$TIER4_FORK_BRANCH"
else
  echo "MISSING: TIER4_FORK_CLONE not found at $TIER4_FORK_CLONE -- Criteria 3, 6 and 7's tier4 fork halves are ABSENT from this transcript"
fi

# Fix-round-2 finding (2026-08-05): scoping the CAPABILITY comparison to
# autoware-support is correct -- it is the branch the benchmark's cell B builds
# -- but scoping the ACTIVITY/MAINTENANCE verdict to it and publishing "stopped
# moving" about tier4-native the approach is not: tier4/main is the repo's
# actual default branch, is 349 commits ahead of autoware-support, and carries
# 205 commits inside the same 90-day window this snapshot reports as 0. This
# block exists so the branch-vs-approach distinction is MEASURED, not argued.
hdr "Criterion 3/7 -- tier4/main (the repo's DEFAULT branch), for the branch-vs-approach distinction"
if [ -d "$TIER4_FORK_CLONE" ]; then
  echo "-- repo HEAD branch per the remote --"
  git -C "$TIER4_FORK_CLONE" remote show tier4 2>/dev/null | grep -i 'HEAD branch' || echo "(remote show unavailable; tier4/main assumed)"
  count_range "$TIER4_FORK_CLONE" "$UPSTREAM_BASE" "$TIER4_MAIN_BRANCH"
  count_range "$TIER4_FORK_CLONE" "$TIER4_FORK_BRANCH" "$TIER4_MAIN_BRANCH"
  echo "-- tips --"
  git -C "$TIER4_FORK_CLONE" log -1 --format='%H %ci  autoware-support' "$TIER4_FORK_BRANCH"
  git -C "$TIER4_FORK_CLONE" log -1 --format='%H %ci  main' "$TIER4_MAIN_BRANCH"
  echo "-- 90-day commits: autoware-support, then main (the pair the rubric must print together) --"
  git -C "$TIER4_FORK_CLONE" rev-list --count --since="90 days ago" "$TIER4_FORK_BRANCH"
  git -C "$TIER4_FORK_CLONE" rev-list --count --since="90 days ago" "$TIER4_MAIN_BRANCH"
  echo "-- 12-month distinct author emails on main (machine-produced) --"
  git -C "$TIER4_FORK_CLONE" log --since="365 days ago" "$TIER4_MAIN_BRANCH" --format='%ae' | sort -u | wc -l
  echo "-- is autoware-support an ancestor of main? --"
  if git -C "$TIER4_FORK_CLONE" merge-base --is-ancestor "$TIER4_FORK_BRANCH" "$TIER4_MAIN_BRANCH"; then
    echo "YES"
  else
    echo "NO -- the two diverged; main was fast-forwarded from the ue5-dev lineage (gap-catalog.md 1.3)"
  fi
else
  echo "MISSING: TIER4_FORK_CLONE not found -- the branch-vs-approach check is ABSENT from this transcript"
fi

hdr "Criterion 3 -- Extension's required fork delta (spec quotes 216)"
if [ -d "$EXT_FORK_CLONE" ]; then
  maybe_fetch "$EXT_FORK_CLONE" upstream ue5-dev
  count_range "$EXT_FORK_CLONE" "$UPSTREAM_BASE" "$EXT_FORK_BRANCH"
else
  echo "MISSING: EXT_FORK_CLONE not found at $EXT_FORK_CLONE -- Criteria 3, 6 and 7's extension fork halves are ABSENT from this transcript"
fi

hdr "Criterion 3 -- Extension repo's own commit count (the '+ this repo' half of the artifact set)"
gh_api_commits_capped "repos/$EXT_REPO/commits?per_page=100&sha=main" 'length'

hdr "Criterion 3 -- Bridge's unmerged artifact set (spec quotes 0, quoted explicitly)"
echo "MANUAL OBSERVATION: the bridge ships inside $BRIDGE_REPO at $BRIDGE_PATH and installs"
echo "against an official CARLA release binary (see Criterion 5) -- there is no fork to build."

# NAMED PRECONDITION (fix round 2): this check reads $TIER4_FORK_BRANCH inside
# $EXT_FORK_CLONE. The old code did a refspec-less `fetch <path>` first, which
# writes FETCH_HEAD and NOT that ref -- so the ref only ever existed here in the
# operator's shared-.git worktree arrangement, and on an independent clone both
# lines fell through behind `2>/dev/null` and silently dropped the 121-commit
# figure that Criteria 3 and 6 both quote. Now it is checked and named.
hdr "Bonus reproducibility check -- is either fork built on top of the other's delta?"
if [ ! -d "$EXT_FORK_CLONE" ]; then
  echo "MISSING: EXT_FORK_CLONE not found -- bonus check ABSENT from this transcript"
elif ! git -C "$EXT_FORK_CLONE" rev-parse --verify --quiet "$TIER4_FORK_BRANCH" >/dev/null; then
  echo "SKIP (precondition unmet): $TIER4_FORK_BRANCH does not resolve inside $EXT_FORK_CLONE."
  echo "  This check needs BOTH forks' refs in ONE clone. Add the tier4 remote and fetch it:"
  echo "    git -C $EXT_FORK_CLONE remote add tier4 https://github.com/tier4/carla-autoware-native.git && git -C $EXT_FORK_CLONE fetch tier4"
  echo "  Until then rubric.md's 121-commit extension-only figure is NOT reproduced by this run."
else
  echo "git merge-base --is-ancestor $TIER4_FORK_BRANCH $EXT_FORK_BRANCH"
  if git -C "$EXT_FORK_CLONE" merge-base --is-ancestor "$TIER4_FORK_BRANCH" "$EXT_FORK_BRANCH"; then
    echo "YES -- tier4/autoware-support is an ancestor of the extension's fork branch"
  else
    echo "NO -- the two forks share an older common ancestor, not a direct lineage"
  fi
  echo "(extension-only work if tier4 were an ancestor; still a useful upper bound otherwise)"
  count_range "$EXT_FORK_CLONE" "$TIER4_FORK_BRANCH" "$EXT_FORK_BRANCH"
fi

# ---------------------------------------------------------------------------
# Criterion 4 (upstreamed ratio): PR-count based (not a SHA-exact mapping to
# the Criterion-3 delta -- a commit-for-commit cherry-pick trace is out of
# this snapshot's scope). Counts merged vs total PRs opened by each fork's
# known authors against the upstream repo the fork tracks.
# ---------------------------------------------------------------------------
hdr "Criterion 4 -- Extension's upstreaming: youtalk's PRs to carla-simulator/carla"
pr_state_breakdown carla-simulator/carla youtalk 200

hdr "Criterion 4 -- Extension's upstreaming: JArmandoAnaya's PRs to carla-simulator/carla (2nd fork contributor)"
pr_state_breakdown carla-simulator/carla JArmandoAnaya 200

hdr "Criterion 4 -- Extension's mitigation PR chain the spec names (#9743-#9758, full inclusive range)"
for n in $(seq 9743 9758); do
  gh pr view "$n" --repo carla-simulator/carla --json number,state,title,author --jq '[.number,.state,.author.login,.title] | @tsv' \
    || echo "$n does not exist as a PR in carla-simulator/carla (gap in the number sequence)"
done

# Fix-round-1 finding: "no PR from any of the delta's actual authors" is
# broader than any command originally run here, and false as literally
# written -- the ~98-commit range shared with the un-upstreamed
# CARLA-community pool (see Criterion 3/6) has authors (glopezdiest, Blyron,
# ...) who DO have large upstream PR histories; they're just not
# tier4/robotec-specific. The claim must be scoped to the delta's actual
# ROBOTEC/TIER4 authors (GH logins resolved from the shortlog emails via
# `gh api search/users?q=<name>` / direct `gh api users/<login>` lookups),
# and both halves -- scoped-zero and shared-nonzero -- need their own command.
hdr "Criterion 4 -- tier4-native's upstreaming, SCOPED to the delta's Robotec/tier4-specific authors (the 4 responsible for 198/305 commits -- see Criterion 6): expect zero"
for u in TauTheLepton Goldob wojciechczerski hosokawa-ikuto; do
  echo "-- $u (Mateusz Palczuk / Adam Gotlib / Wojciech Czerski / HOSOKAWA Ikuto's GH login) --"
  pr_state_breakdown carla-simulator/carla "$u" 200
done

hdr "Criterion 4 -- CONTRAST: shared-ancestor community authors in the SAME delta are NOT zero (why the claim above must be scoped, not repo-wide)"
for u in glopezdiest Blyron mackierx111; do
  echo "-- $u --"
  pr_state_breakdown carla-simulator/carla "$u" 200
done

hdr "Criterion 4 -- broader text search (context only, not the basis of the scoped claim above)"
gh search prs --repo carla-simulator/carla "tier4" --limit 10 --json number,title,state
gh search prs --repo carla-simulator/carla "robotec" --limit 10 --json number,title,state

hdr "Criterion 4 -- Bridge's upstreaming: N/A, it IS the upstream (in-tree in autoware_universe)"

# ---------------------------------------------------------------------------
# Criterion 5 (runs against an official upstream CARLA release binary):
# architectural fact, not a metric a command computes -- recorded as MANUAL
# OBSERVATION with the exact doc line each verdict is read from.
# ---------------------------------------------------------------------------
hdr "Criterion 5 -- MANUAL OBSERVATION (see the links this prints)"
echo "Bridge: README $BRIDGE_PATH/README.md line 'Install CARLA 0.9.15' + a prebuilt"
echo "  ROS 2 Humble communication *package* (gezp/carla_ros release), not a source build."
echo "  https://github.com/autowarefoundation/autoware_universe/blob/main/$BRIDGE_PATH/README.md"
echo "Extension + tier4-native: both require building the CARLA fork's UE5.5 source tree"
echo "  from scratch (this is the fork itself, not an add-on to a release binary)."
echo "  https://github.com/tier4/carla-autoware-native/blob/autoware-support/README.md"

# ---------------------------------------------------------------------------
# Criteria 6-7 (maintainer count/bus factor, activity): delta-scoped for the
# two native forks (see the fork-inherited-history trap note above);
# repo-scoped for the extension repo itself; path-scoped for the bridge
# (autoware_universe is a monorepo -- whole-repo contributor stats would
# mix in every other Autoware package's history).
# ---------------------------------------------------------------------------
hdr "Criteria 6-7 -- Extension repo (this repo): commits + unique author"
# Guarded on the same grounds as the bridge-side author list: a truncated page
# yields a SUBSET of the authors, and "one unique author" is exactly the claim
# this line is quoted for -- so an unnoticed cap would manufacture the finding.
gh_api_commits_capped "repos/$EXT_REPO/commits?per_page=100&sha=main" '[.[].commit.author.name] | unique'
echo "(repo created 2026-07-20 -- 90-day and lifetime windows are identical; see rubric.md's annotation)"

hdr "Criteria 2+6 -- Extension repo: PR authorship + review history (solo-authored/zero-external-reviewers claim)"
gh pr list --repo "$EXT_REPO" --state all --limit 200 --json number,author,mergedAt,state,reviews --jq \
  '(group_by(.state) | map({state: .[0].state, n: length})), ([.[].author.login] | unique), ([.[].reviews[].author.login] | unique)'

hdr "Criteria 6-7 -- tier4-native delta (upstream/ue5-dev..tier4/autoware-support): bus factor + activity"
if [ -d "$TIER4_FORK_CLONE" ]; then
  echo "-- full author breakdown (bus factor), by commit count --"
  git -C "$TIER4_FORK_CLONE" shortlog -sne "$UPSTREAM_BASE..$TIER4_FORK_BRANCH"
  echo "-- 90-day commit count in the delta --"
  git -C "$TIER4_FORK_CLONE" rev-list --count --since="90 days ago" "$UPSTREAM_BASE..$TIER4_FORK_BRANCH"
  echo "-- 12-month distinct author emails in the delta --"
  git -C "$TIER4_FORK_CLONE" log --since="365 days ago" "$UPSTREAM_BASE..$TIER4_FORK_BRANCH" --format='%ae' | sort -u
  echo "-- count of the above (machine-produced -- do not hand-count the printed list) --"
  git -C "$TIER4_FORK_CLONE" log --since="365 days ago" "$UPSTREAM_BASE..$TIER4_FORK_BRANCH" --format='%ae' | sort -u | wc -l
  echo "-- last commit date on tier4/autoware-support itself (staleness check; CI-coverage check is under Criterion 9) --"
  git -C "$TIER4_FORK_CLONE" log -1 --format='%H %ci' "$TIER4_FORK_BRANCH"
else
  echo "MISSING: TIER4_FORK_CLONE not found -- this section is ABSENT from the transcript"
fi

hdr "Criteria 6-7 -- Extension's required fork delta (upstream/ue5-dev..feat/autoware-seminative-phase-b): bus factor + activity"
if [ -d "$EXT_FORK_CLONE" ]; then
  echo "-- full author breakdown (bus factor), by commit count --"
  git -C "$EXT_FORK_CLONE" shortlog -sne "$UPSTREAM_BASE..$EXT_FORK_BRANCH"
  echo "-- 90-day commit count in the delta --"
  git -C "$EXT_FORK_CLONE" rev-list --count --since="90 days ago" "$UPSTREAM_BASE..$EXT_FORK_BRANCH"
  echo "-- 12-month distinct author emails in the delta --"
  git -C "$EXT_FORK_CLONE" log --since="365 days ago" "$UPSTREAM_BASE..$EXT_FORK_BRANCH" --format='%ae' | sort -u
  echo "-- count of the above (machine-produced -- do not hand-count the printed list; fix-round-1 finding: a hand-count of this exact list previously miscounted 24 instead of 25) --"
  git -C "$EXT_FORK_CLONE" log --since="365 days ago" "$UPSTREAM_BASE..$EXT_FORK_BRANCH" --format='%ae' | sort -u | wc -l
else
  echo "MISSING: EXT_FORK_CLONE not found -- this section is ABSENT from the transcript"
fi

hdr "Criteria 6-7 -- Bridge ($BRIDGE_PATH, path-scoped -- NOT autoware_universe-wide)"
echo "-- lifetime commits touching the path --"
gh_api_commits_capped "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&per_page=100" 'length'
echo "-- earliest/latest commit date touching the path (lifetime window) --"
# Same capped page: if it truncated, 'min' is the oldest commit ON THE PAGE and
# not the true first-touch date, so the cap check qualifies this pair too.
gh_api_commits_capped "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&per_page=100" '[.[].commit.author.date] | (min, max)'
echo "-- 90-day commits touching the path --"
gh_api_commits_capped "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&since=$SINCE_90D&per_page=100" 'length'
echo "-- 12-month distinct author logins touching the path --"
# Truncation here drops CONTRIBUTORS, not just commits: the unique set is a
# subset of the true one, so the cap check is load-bearing for this line.
gh_api_commits_capped "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&since=$SINCE_365D&per_page=100" '[.[].author.login] | unique'
echo "-- named maintainers (package.xml, already printed under Criterion 10) --"

# ---------------------------------------------------------------------------
# Criterion 8 (install complexity): MANUAL OBSERVATION, sourced from each
# project's own install docs. No command computes "hours"; these are the
# exact doc lines the figures come from.
# ---------------------------------------------------------------------------
hdr "Criterion 8 -- MANUAL OBSERVATION (doc lines the figures come from)"
echo "tier4-native (autoware-support branch README): 'Around 300Gb free disk space';"
echo "  'Building Unreal Engine from source can take 3-4 hours'; first editor build 'up to 1 hour'."
echo "  https://github.com/tier4/carla-autoware-native/blob/autoware-support/README.md"
echo "Extension: shares the SAME underlying UE5.5-fork build cost (same Unreal Engine"
echo "  fork this repo's required CARLA build is built from) -- no separate hours/disk"
echo "  figure is documented in this repo because that build lives in the sibling fork"
echo "  repo, not here; the extension .so itself builds in well under a minute"
echo "  (cmake+ninja, plain C++, no UE toolchain -- see this repo's ci.yaml cpp-tests job)."
echo "  https://github.com/autowarefoundation/carla-autoware-extension/blob/main/docs/running-e2e.md"
echo "Bridge: no source build of CARLA or of the bridge's simulator at all -- a stock CARLA"
echo "  0.9.15 release download + pip-installed ROS 2 Humble communication package + a"
echo "  normal colcon build of one ament_python/ament_cmake package."
echo "  https://github.com/autowarefoundation/autoware_universe/blob/main/$BRIDGE_PATH/README.md"

# ---------------------------------------------------------------------------
# Criterion 9 (CI coverage of the integration path).
# ---------------------------------------------------------------------------
hdr "Criterion 9 -- Extension repo's CI workflow(s)"
gh api "repos/$EXT_REPO/contents/.github/workflows" --jq '.[].name'
echo "(ci.yaml's cpp-tests job builds+links the extension .so against ROS 2 Jazzy and runs its gtest suite -- see the job for the exact commands)"

hdr "Criterion 9 -- tier4-native's CI workflow trigger branches (does any target autoware-support?)"
for f in ue5_pr.yml ue5_dev.yml ue4_dev.yml ue4_release.yml ue4_content.yml; do
  echo "-- $f --"
  gh api "repos/$TIER4_REPO/contents/.github/workflows/$f" --jq '.content' | base64 -d | grep -A3 '^on:'
done

hdr "Criterion 9 -- tier4-native: has any CI run EVER fired on the autoware-support branch itself?"
gh api "repos/$TIER4_REPO/actions/runs?branch=autoware-support&per_page=5" --jq '.total_count'
gh api "repos/$TIER4_REPO/actions/runs?branch=autoware-support&per_page=5" --jq '.workflow_runs[] | .name + " (" + .event + ", " + .created_at + ")"'

hdr "Criterion 9 -- Bridge: build-and-test-differential.yaml exists repo-wide; does the package itself have unit tests?"
gh api "repos/$BRIDGE_REPO/contents/$BRIDGE_PATH" --jq '.[].name'
echo "(no test/ directory in the listing above; CMakeLists.txt explicitly disables ament_cmake_flake8"
echo " under BUILD_TESTING -- CI here means build + generic ament lint checks, not a functional test)"

# ---------------------------------------------------------------------------
# Criterion 11 (documentation quality): directory listings + sizes, so a
# reader can judge depth without this script asserting a score.
# ---------------------------------------------------------------------------
hdr "Criterion 11 -- Extension repo's docs/ directory"
gh api "repos/$EXT_REPO/contents/docs" --jq '.[] | .name + " (" + (.size|tostring) + " bytes)"'

hdr "Criterion 11 -- tier4-native: autoware-support README length + Docs/ dir (autoware-specific docs?)"
gh api "repos/$TIER4_REPO/contents/README.md?ref=autoware-support" --jq '.content' | base64 -d | wc -l
echo "-- count of Docs/ entries with 'autoware' in the name (0 means the branch README is the only autoware-specific doc) --"
gh api "repos/$TIER4_REPO/contents/Docs?ref=autoware-support" --jq '.[].name' | grep -ic autoware || true

hdr "Criterion 11 -- Bridge: README length + docs/ subfolder contents"
gh api "repos/$BRIDGE_REPO/contents/$BRIDGE_PATH/README.md" --jq '.content' | base64 -d | wc -l
gh api "repos/$BRIDGE_REPO/contents/$BRIDGE_PATH/docs" --jq '.[].name'

hdr "Snapshot complete"
echo "Transcribe the values above into docs/evaluation/rubric.md's value cells,"
echo "under a retrieval date of $NOW_UTC, each with the link this script printed"
echo "or the repo/PR URL the gh call resolved."
echo
echo "BEFORE TRANSCRIBING: grep this transcript for 'MISSING' -- a skipped clone"
echo "removes Criteria 3, 6 and 7's fork halves without failing the run."
echo "AND: commit the transcript. rubric.md's audit-trail appendix exists only"
echo "because the 2026-08-05T02:13 UTC run's stdout was never captured."
