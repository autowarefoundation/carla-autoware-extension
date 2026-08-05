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
# PREREQUISITES:
#   - `gh` authenticated (gh auth status) with no special scopes beyond
#     public repo read.
#   - Two LOCAL git clones, read-only for this script's purposes, whose
#     paths CLAUDE.md documents as this repo's sibling repos:
#       EXT_FORK_CLONE   (default ~/src/carla-autoware-integration), on
#                        branch feat/autoware-seminative-phase-b
#       TIER4_FORK_CLONE (default ~/src/carla-autoware-native), with the
#                        `tier4` and `upstream` remotes fetched
#     Both are git worktrees sharing one shallow clone's .git in this
#     operator's setup (`~/src/carla`); any independent clone with the same
#     branches and remotes fetched reproduces the same rev-list counts.
#     If a clone is missing, its section prints a SKIP line and the rest of
#     the snapshot still runs -- see CLAUDE.md "Sibling repos".
#
# USAGE: bash scripts/evaluation/rubric_snapshot.sh
set -euo pipefail

EXT_REPO="autowarefoundation/carla-autoware-extension"
TIER4_REPO="tier4/carla-autoware-native"
BRIDGE_REPO="autowarefoundation/autoware_universe"
BRIDGE_PATH="simulator/autoware_carla_interface"

EXT_FORK_CLONE="${EXT_FORK_CLONE:-$HOME/src/carla-autoware-integration}"
EXT_FORK_BRANCH="${EXT_FORK_BRANCH:-feat/autoware-seminative-phase-b}"
TIER4_FORK_CLONE="${TIER4_FORK_CLONE:-$HOME/src/carla-autoware-native}"
TIER4_FORK_BRANCH="${TIER4_FORK_BRANCH:-tier4/autoware-support}"
UPSTREAM_BASE="${UPSTREAM_BASE:-upstream/ue5-dev}"

NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SINCE_90D="$(date -u -d '90 days ago' +%Y-%m-%dT%H:%M:%SZ)"
SINCE_365D="$(date -u -d '365 days ago' +%Y-%m-%dT%H:%M:%SZ)"

hdr() { printf '\n=== %s ===\n' "$1"; }

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
  git -C "$TIER4_FORK_CLONE" fetch tier4 --prune --quiet || true
  git -C "$TIER4_FORK_CLONE" fetch upstream ue5-dev --quiet || true
  echo "git rev-list --count $UPSTREAM_BASE..$TIER4_FORK_BRANCH"
  git -C "$TIER4_FORK_CLONE" rev-list --count "$UPSTREAM_BASE..$TIER4_FORK_BRANCH"
else
  echo "SKIP: TIER4_FORK_CLONE not found at $TIER4_FORK_CLONE -- see CLAUDE.md Sibling repos"
fi

hdr "Criterion 3 -- Extension's required fork delta (spec quotes 216)"
if [ -d "$EXT_FORK_CLONE" ]; then
  git -C "$EXT_FORK_CLONE" fetch upstream ue5-dev --quiet || true
  echo "git rev-list --count $UPSTREAM_BASE..$EXT_FORK_BRANCH"
  git -C "$EXT_FORK_CLONE" rev-list --count "$UPSTREAM_BASE..$EXT_FORK_BRANCH"
else
  echo "SKIP: EXT_FORK_CLONE not found at $EXT_FORK_CLONE -- see CLAUDE.md Sibling repos"
fi

hdr "Criterion 3 -- Extension repo's own commit count (the '+ this repo' half of the artifact set)"
gh api "repos/$EXT_REPO/commits?per_page=100&sha=main" --jq 'length'

hdr "Criterion 3 -- Bridge's unmerged artifact set (spec quotes 0, quoted explicitly)"
echo "MANUAL OBSERVATION: the bridge ships inside $BRIDGE_REPO at $BRIDGE_PATH and installs"
echo "against an official CARLA release binary (see Criterion 5) -- there is no fork to build."

hdr "Bonus reproducibility check -- is either fork built on top of the other's delta?"
if [ -d "$EXT_FORK_CLONE" ]; then
  git -C "$EXT_FORK_CLONE" fetch "$TIER4_FORK_CLONE" 2>/dev/null || true
  echo "git merge-base --is-ancestor $TIER4_FORK_BRANCH $EXT_FORK_BRANCH"
  if git -C "$EXT_FORK_CLONE" merge-base --is-ancestor "$TIER4_FORK_BRANCH" "$EXT_FORK_BRANCH" 2>/dev/null; then
    echo "YES -- tier4/autoware-support is an ancestor of the extension's fork branch"
  else
    echo "NO -- the two forks share an older common ancestor, not a direct lineage"
  fi
  echo "git rev-list --count $TIER4_FORK_BRANCH..$EXT_FORK_BRANCH (extension-only work if tier4 were an ancestor; still a useful upper bound otherwise)"
  git -C "$EXT_FORK_CLONE" rev-list --count "$TIER4_FORK_BRANCH..$EXT_FORK_BRANCH" 2>/dev/null || echo "(remote ref unavailable in this clone; skip)"
else
  echo "SKIP: EXT_FORK_CLONE not found"
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
gh api "repos/$EXT_REPO/commits?per_page=100&sha=main" --jq '[.[].commit.author.name] | unique'
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
  echo "SKIP: TIER4_FORK_CLONE not found"
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
  echo "SKIP: EXT_FORK_CLONE not found"
fi

hdr "Criteria 6-7 -- Bridge ($BRIDGE_PATH, path-scoped -- NOT autoware_universe-wide)"
echo "-- lifetime commits touching the path --"
gh api "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&per_page=100" --jq 'length'
echo "-- earliest/latest commit date touching the path (lifetime window) --"
gh api "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&per_page=100" --jq '[.[].commit.author.date] | (min, max)'
echo "-- 90-day commits touching the path --"
gh api "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&since=$SINCE_90D&per_page=100" --jq 'length'
echo "-- 12-month distinct author logins touching the path --"
gh api "repos/$BRIDGE_REPO/commits?path=$BRIDGE_PATH&since=$SINCE_365D&per_page=100" --jq '[.[].author.login] | unique'
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
