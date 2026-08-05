# Community-acceptance rubric: three CARLA↔Autoware integration approaches

**Pre-registered 2026-08-04, before any metric was retrieved.** This document
exists in two halves, committed in two separate commits, in this order:

1. **This commit** — the criterion list, each criterion's direction, and
   **empty value cells**. No metric, count, date, or link appears below this
   line as of this commit.
2. A later commit, `docs(evaluation): rubric evidence snapshot`, which fills
   the value cells using `scripts/evaluation/rubric_snapshot.sh` and records
   the retrieval date + links.

The ordering is the point: the criteria and their directions are locked
before anyone looks at a single GitHub API response or `git rev-list`
count, so no criterion can be added, dropped, or re-directioned after the
fact to favor a particular approach's numbers. If a criterion is found
missing after the pre-registration commit, it is added in a **follow-up**
commit with a note explaining why — the pre-registration commit itself is
never rewritten.

## No composite score

**This rubric does not compute, imply, or rank a total score.** Each row is
independent evidence for a reader to weigh according to their own priorities
(a foundation evaluating long-term maintenance risk weighs governance and bus
factor differently than an integrator who only cares about "does it run
against a release binary today"). Summing, weighting, or averaging the rows
below into a single number is explicitly out of scope and would misrepresent
what the underlying data supports — several rows are categorical (yes/no,
license family) or are call-it-yourself judgments (documentation quality)
that do not reduce to a scalar without inventing a weighting the spec never
asked for.

## The three approaches

| Label            | Approach                                                                                                                                        | Repo                                                                                         |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **Extension**    | This repo's out-of-tree C-ABI extension `.so` + declarative runner, against a CARLA fork carrying the native-ROS-2 patch set this repo requires | `autowarefoundation/carla-autoware-extension` (+ required fork, see Criterion 3)             |
| **tier4-native** | tier4's in-fork native ROS 2/DDS integration, built directly into a CARLA UE5 fork                                                              | `tier4/carla-autoware-native`                                                                |
| **Bridge**       | The in-tree `autoware_carla_interface`, a Python bridge node against an upstream CARLA release binary                                           | Autoware's own repos (exact path confirmed in the evidence snapshot commit) + upstream CARLA |

## Criteria

Each row states the criterion, the **direction** (which value a reader
concerned with community acceptance would generally read as more favorable —
recorded for transparency, not to be summed into a score), and then one
empty value cell per approach. Value cells are filled only in the evidence
snapshot commit.

### 1. Governance / ownership

**Direction:** foundation- or multi-org-governed ownership is generally read
as lower long-term risk than a single company's fork or a single
unaffiliated individual's repo, but this is a qualitative judgment, not a
ranking — record the actual ownership structure for each.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 2. Who must accept it

**Direction:** descriptive, not ranked — records which body's sign-off (an
AWF maintainer team, a single company, upstream CARLA maintainers, etc.)
currently gates or would gate adoption of each approach.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 3. Total unmerged artifact set a user must install

**Direction:** lower is more favorable — a smaller unmerged footprint is
less for an adopter to build, trust, and maintain outside upstream.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 4. Upstreamed ratio

**Direction:** higher is more favorable — the fraction of the approach's
required changes that have already landed in an upstream (CARLA or
Autoware) `main`/default branch, out of the total changes it depends on.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 5. Runs against an official upstream CARLA release binary (yes/no)

**Direction:** "yes" is more favorable — this is called out as its own line
because it is the single largest real-world adoption differentiator: an
approach a user can run against a stock release download has a categorically
lower adoption bar than one requiring a multi-hour UE5 fork build.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 6. Maintainer count and bus factor

**Direction:** higher maintainer count / higher bus factor is more
favorable — fewer people whose absence would stall the project is higher
risk.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 7. Activity — 90-day commits, lifetime commits, and distinct contributors in the last 12 months

**Direction:** higher is generally more favorable, **except** that a young
repo can post high 90-day/12-month activity purely by having no history to
average against. **The extension row is annotated "repo created
2026-07-20"** for exactly this reason — a 7-day-old hyperactive repo must not
win an activity metric by construction, and any reader comparing this row
across approaches must read the annotation before drawing a conclusion from
the numbers.

| Extension (repo created 2026-07-20) | tier4-native | Bridge |
| ----------------------------------- | ------------ | ------ |
|                                     |              |        |

### 8. Install complexity (steps, build hours, disk)

**Direction:** lower is more favorable — fewer manual steps, less build
time, less disk footprint to get from zero to a running stack.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 9. Automated test/CI coverage of the integration path

**Direction:** higher/more coverage is more favorable — CI that actually
exercises the CARLA↔Autoware integration path (not just a generic build) is
stronger evidence of ongoing correctness than CI that doesn't touch it.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 10. License

**Direction:** descriptive, not ranked — records the license each approach
ships under and whether it is compatible with the other two / with upstream
CARLA and Autoware licensing.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

### 11. Documentation quality

**Direction:** higher/more comprehensive is more favorable — this is a
qualitative judgment (presence of install guide, architecture doc,
troubleshooting record, etc.), recorded with links to what was found, not a
numeric score.

| Extension | tier4-native | Bridge |
| --------- | ------------ | ------ |
|           |              |        |

## Known outcomes the evidence snapshot must check

The design spec (`2026-07-27-three-approach-evaluation-design.md`,
"Community-acceptance rubric" section) states expected outcomes ahead of the
snapshot for several rows above (governance/ownership, unmerged artifact
set, activity). The evidence-snapshot commit is required to check each of
those expectations against live data and, for each, either confirm it
verbatim, correct it, or mark it unverifiable-with-link — it does not get to
silently inherit the spec's wording. Nothing from the spec's expected
outcomes is transcribed into this pre-registration commit: doing so here
would risk the value cells above being filled to match a preview instead of
independently retrieved evidence.

## Reproducing this snapshot

`scripts/evaluation/rubric_snapshot.sh` (added in the evidence-snapshot
commit) contains the exact `gh api` / `git` command that fills every cell
above. Re-run it to refresh the snapshot; re-running it does **not**
authorize editing the criterion list or directions above without a
follow-up commit that explains the change — see the note at the top of this
document.
