# Community-acceptance rubric: three CARLA↔Autoware integration approaches

**Pre-registered 2026-08-04, before any metric was retrieved.** This document
is built from three commits, in this order:

1. `docs(evaluation): pre-register acceptance rubric criteria` — the
   criterion list, each criterion's direction, and empty value cells. Zero
   metrics existed in the repository at that commit.
2. `docs(evaluation): rubric evidence snapshot` — fills the value cells
   below by running `scripts/evaluation/rubric_snapshot.sh` and records the
   retrieval date + links.
3. `docs(evaluation): correct rubric snapshot cells that failed
re-verification` — an adversarial re-verification pass found 4 cells that
   didn't reproduce (a PR-count truncation artifact, two conflated GitHub
   rulesets, an over-broad claim, and a hand-count error) plus one editorial
   slip in commit 2 (see the note under Criterion 7). All are fixed and
   documented in place below, per this document's own rule: corrections land
   in a **follow-up commit**, never a rewrite of commits 1 or 2. See
   "Fix round 1" below for the full disposition.

The ordering is the point: the criteria and their directions were locked
before anyone looked at a single GitHub API response or `git rev-list`
count, so no criterion could be added, dropped, or re-directioned after the
fact to favor a particular approach's numbers. If a criterion is found
missing after the pre-registration commit, it is added in a **follow-up**
commit with a note explaining why — the pre-registration commit itself is
never rewritten.

**Retrieved 2026-08-05T02:13 UTC**, by running
`bash scripts/evaluation/rubric_snapshot.sh` from this repo's root. Every
value cell below cites the command (reproduced in that script) or the URL a
cell's manual observation came from. Where the fresh snapshot's numbers
differ from a number the design spec quoted at spec-writing time
(2026-07-27), both are given — see the per-criterion notes and
"Known outcomes checked against this snapshot" below.

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

| Label            | Approach                                                                                                                                        | Repo                                                                                                                                                                                                                                                 |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Extension**    | This repo's out-of-tree C-ABI extension `.so` + declarative runner, against a CARLA fork carrying the native-ROS-2 patch set this repo requires | [`autowarefoundation/carla-autoware-extension`](https://github.com/autowarefoundation/carla-autoware-extension) (+ required fork, see Criterion 3)                                                                                                   |
| **tier4-native** | tier4's in-fork native ROS 2/DDS integration, built directly into a CARLA UE5 fork                                                              | [`tier4/carla-autoware-native`](https://github.com/tier4/carla-autoware-native), branch [`autoware-support`](https://github.com/tier4/carla-autoware-native/tree/autoware-support)                                                                   |
| **Bridge**       | `autoware_carla_interface`, an in-tree Python bridge node against an upstream CARLA release binary                                              | [`autowarefoundation/autoware_universe`](https://github.com/autowarefoundation/autoware_universe), path [`simulator/autoware_carla_interface`](https://github.com/autowarefoundation/autoware_universe/tree/main/simulator/autoware_carla_interface) |

## Criteria

Each row states the criterion, the **direction** (which value a reader
concerned with community acceptance would generally read as more favorable —
recorded for transparency, not to be summed into a score), and the value
cells, each traceable to a command or a linked observation.

### 1. Governance / ownership

**Direction:** foundation- or multi-org-governed ownership is generally read
as lower long-term risk than a single company's fork or a single
unaffiliated individual's repo, but this is a qualitative judgment, not a
ranking — record the actual ownership structure for each.

| Extension                                                                                                                                                                                                                                                                                                                                                                                                                         | tier4-native                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | Bridge                                                                                                                                                                                                                                                            |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Repo hosted under the `autowarefoundation` GitHub org, but with no CODEOWNERS file and a `main` ruleset that requires only passing status checks (`cpp-tests`, `pytest`, `pre-commit`), not a human approving review (`gh api repos/autowarefoundation/carla-autoware-extension/rulesets`). In practice, ownership sits with the sole author. The required fork lives on a personal account (`youtalk/carla`), no org governance. | Owned by tier4 (a single company, Tier IV Inc.), a hard fork of `carla-simulator/carla`. **Corrected in fix round 1** (the original cell conflated two rulesets): the repo has two active rulesets — one (id `20353122`) requires 1 approving CODEOWNER review but its `ref_name.include` list is `develop`/`release`/`master`/`main`/`trunk`/`dev`/`stage`/`staging`/etc., **not** `autoware-support`; the other (id `20231367`, "sec-inc-85 emergency lockdown") IS repo-wide (`~ALL`) but carries no `pull_request` rule at all. The authoritative per-branch check, `gh api repos/tier4/carla-autoware-native/rules/branches/autoware-support`, confirms only `creation, update, deletion, non_fast_forward` apply to that branch — no approval gate reaches it, and the branch is **frozen** (updates/deletion/force-push all blocked). The `.github/CODEOWNERS` file is inherited **verbatim** from upstream CARLA (`* @carla-simulator/codeowners-carla`) and, per the above, is never consulted on this branch anyway. | Lives inside `autowarefoundation/autoware_universe`, the flagship AWF monorepo under AWF project-steering-committee governance; the package's own `.github/CODEOWNERS` line names 4 maintainers (3 `@tier4.jp` + 1 external `gmail.com`), matching `package.xml`. |

### 2. Who must accept it

**Direction:** descriptive, not ranked — records which body's sign-off (an
AWF maintainer team, a single company, upstream CARLA maintainers, etc.)
currently gates or would gate adoption of each approach.

| Extension                                                                                                                                              | tier4-native                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Bridge                                                                                                                                                                               |
| ------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| CI green only (`required_status_checks` ruleset) — no required human approval configured on `main`. All 30 PRs to date self-merged by the sole author. | **Corrected in fix round 1**: nobody, currently — `gh api repos/tier4/carla-autoware-native/rules/branches/autoware-support` shows only `creation, update, deletion, non_fast_forward` apply to `autoware-support`, no `pull_request` rule. The 1-approving-CODEOWNER-review ruleset exists in the repo but its branch-name patterns don't reach `autoware-support` (see Criterion 1); the ruleset that IS repo-wide has no review requirement. The branch is instead **frozen** against updates/deletion/force-push — a sharper fact than "someone must approve," and one that reinforces the stalled-sync finding (Criterion 7) rather than softening it. | `autoware_universe`'s `main - approval` ruleset: `required_approving_review_count=1`, `require_code_owner_review=true` — for this path, one of the 4 named maintainers must approve. |

### 3. Total unmerged artifact set a user must install

**Direction:** lower is more favorable — a smaller unmerged footprint is
less for an adopter to build, trust, and maintain outside upstream.

| Extension                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | tier4-native                                                                                                                                                                                                                                  | Bridge                                                                                                                               |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **219 commits** ahead of `upstream/ue5-dev` on `feat/autoware-seminative-phase-b` (`git rev-list --count upstream/ue5-dev..feat/autoware-seminative-phase-b`, run in `~/src/carla-autoware-integration`) **+ this repo's own 25 commits** on `main`. The design spec quoted **216** at spec-writing time (2026-07-27) — the fresh count is **219**, +3, consistent with the 3 P4-transport-sweep-era commits visible at the head of the delta's log (`docs(ros2): pre-register the CAL-seam publish-order confound...`, `fix(ros2): publish the CAL-seam twins adjacent...`, `feat(ros2): add env-gated bench in-core cloud publisher...`) landing on the fork between spec-writing and this snapshot. Both numbers are reported per this task's instruction: the spec's is a snapshot from spec-writing time, this snapshot's is the current truth. | **305 commits** ahead of `upstream/ue5-dev` on `tier4/autoware-support` (`git rev-list --count upstream/ue5-dev..tier4/autoware-support`, run in `~/src/carla-autoware-native`) — matches the design spec's quoted **305** exactly; no drift. | **0** — quoted explicitly. In-tree in `autoware_universe`'s own `main`; nothing to fork or build outside upstream (see Criterion 5). |

**Note on fork lineage (bonus finding, not a rubric cell):** the extension's
fork is **not** built on top of tier4's fork (`git merge-base --is-ancestor
tier4/autoware-support feat/autoware-seminative-phase-b` → `NO`); the two
share an older common ancestor. The commits unique to the extension's
branch relative to `tier4/autoware-support` are **121** (`git rev-list
--count tier4/autoware-support..feat/autoware-seminative-phase-b`) — see
Criterion 6 for why this matters for bus factor.

### 4. Upstreamed ratio

**Direction:** higher is more favorable — the fraction of the approach's
required changes that have already landed in an upstream (CARLA or
Autoware) `main`/default branch, out of the total changes it depends on.

| Extension                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | tier4-native                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Bridge                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| PR-count proxy (not a SHA-exact map onto the 219-commit delta): [`youtalk`](https://github.com/youtalk)'s PRs to `carla-simulator/carla` — 23 merged / 12 closed-unmerged / 6 open of 41 total; [`JArmandoAnaya`](https://github.com/JArmandoAnaya)'s (2nd fork contributor) — **43 merged / 12 open / 2 closed-unmerged of 57 total** (corrected in fix round 1: the original 38/12/0/50 was a `gh search prs --limit 50` truncation artifact — the result count landed exactly on the cap and silently erased 2 closed-unmerged PRs, erring in the extension's favor; re-run at `--limit 200`, which the script now asserts against hitting again). Combined **66 merged of 98 opened ≈ 67.3%** (was reported 61/91 ≈ 67%). The spec's named mitigation chain [`#9743`–`#9758`](https://github.com/carla-simulator/carla/pull/9743) is confirmed on a full recheck of all 16 numbers in that inclusive range: 11 exist as PRs — the 8-part `JArmandoAnaya` `[1/8]`…`[8/8]` ROS2 pipeline (all MERGED: `#9743`, `#9745`, `#9746`, `#9748`, `#9751`, `#9756`, `#9757`, `#9758`) plus `youtalk`'s unrelated-topic [`#9744`](https://github.com/carla-simulator/carla/pull/9744) and [`#9749`](https://github.com/carla-simulator/carla/pull/9749) (both MERGED) plus one unrelated PR by a third author, `#9750` (CLOSED, unmerged); the remaining 5 numbers (`#9747`, `#9752`–`#9755`) don't exist as PRs in that repo at all (number-sequence gaps, not evidence against the claim). | **0**, scoped correctly (corrected in fix round 1 — the original "no PR from any of the delta's actual authors" was broader than any command run and false as literally written): the delta's 4 actual **Robotec/tier4-specific** authors — [`TauTheLepton`](https://github.com/TauTheLepton) (Mateusz Palczuk), [`Goldob`](https://github.com/Goldob) (Adam Gotlib), [`wojciechczerski`](https://github.com/wojciechczerski), [`hosokawa-ikuto`](https://github.com/hosokawa-ikuto) — each have **zero** PRs to `carla-simulator/carla`. This does **not** extend to the whole delta: several delta authors are shared-ancestor CARLA-community contributors (Criterion 6) with large upstream PR histories unrelated to tier4-native's own work — [`glopezdiest`](https://github.com/glopezdiest) 82 PRs, [`Blyron`](https://github.com/Blyron) 145, [`mackierx111`](https://github.com/mackierx111) 1 — so the "no upstreaming" finding is scoped to tier4/Robotec's own authors, not a repo-wide text-search absence. | N/A — it **is** the upstream (in-tree in `autoware_universe`'s own default branch; no separate upstreaming step exists). |

### 5. Runs against an official upstream CARLA release binary (yes/no)

**Direction:** "yes" is more favorable — this is called out as its own line
because it is the single largest real-world adoption differentiator: an
approach a user can run against a stock release download has a categorically
lower adoption bar than one requiring a multi-hour UE5 fork build.

| Extension                                                                                               | tier4-native                                                                                                                                        | Bridge                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No.** Requires building the CARLA fork's UE5.5 source tree from scratch — the fork _is_ the artifact. | **No.** Same UE5.5 fork source build ([`autoware-support` README](https://github.com/tier4/carla-autoware-native/blob/autoware-support/README.md)). | **Yes.** Installs a stock CARLA 0.9.15 release binary + a prebuilt ROS 2 Humble communication package (pip/egg from [`gezp/carla_ros`](https://github.com/gezp/carla_ros/releases/tag/carla-0.9.15-ubuntu-22.04)), per the [bridge README](https://github.com/autowarefoundation/autoware_universe/blob/main/simulator/autoware_carla_interface/README.md). |

### 6. Maintainer count and bus factor

**Direction:** higher maintainer count / higher bus factor is more
favorable — fewer people whose absence would stall the project is higher
risk.

| Extension                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | tier4-native                                                                                                                                                                                                                                                                                                                                                             | Bridge                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **This repo: 1** (solo, `youtalk`; 25/25 commits, 0 external reviewers across all 30 PRs to date — 24 merged, 5 open, 1 closed-unmerged, all authored by `youtalk`, the only reviewer ever recorded being `youtalk` themself (self-review on 2 PRs) — `gh pr list --repo autowarefoundation/carla-autoware-extension --state all --json author,mergedAt,state,reviews`). **Required fork's 219-commit delta:** dominated by 2 authors, Yutaka Kondo (66) + Jesus Armando Anaya (47) = 113/219 ≈ 52%, plus ~30 more contributing 1–20 commits each. Most of those smaller contributors' names **also appear in tier4-native's own delta** (Blyron, MarcelPiNacy-CVC, Luis Poveda Cano, glopezdiest, AinaRoca, …) — a 98-commit range shared between `upstream/ue5-dev` and the two forks' common ancestor that neither team originated (general un-upstreamed CARLA-community commits). The genuinely **extension-only** work (`tier4/autoware-support..feat/autoware-seminative-phase-b`, 121 commits) is 90% two people: Kondo (63) + Anaya (46) = 109/121. | Dominated by 2 Robotec.ai contractor engineers — Mateusz Palczuk (98) + Wojciech Czerski (62) = 160/305 ≈ 52% — with tier4's own named employee, HOSOKAWA Ikuto (14 + 2 aliased = 16 commits), a **minority** contributor to the branch bearing tier4's name. Bus factor for the branch's day-to-day work looks concentrated in 2 external contractors, not tier4 staff. | **4 named maintainers** in `package.xml`/`CODEOWNERS` (3 `@tier4.jp` + 1 external `gmail.com`). Path-scoped commit history (42 lifetime commits since 2024-07-19) shows **10 distinct author logins in the last 12 months**, one of which (`awf-autoware-bot[bot]`) is an automation account — 9 human authors. |

### 7. Activity — 90-day commits, lifetime commits, and distinct contributors in the last 12 months

**Direction:** higher is generally more favorable, **except** that a young
repo can post high 90-day/12-month activity purely by having no history to
average against. **The extension row is annotated "repo created
2026-07-20"** for exactly this reason — a 7-day-old (16-day-old at this
snapshot) hyperactive repo must not win an activity metric by construction,
and any reader comparing this row across approaches must read the
annotation before drawing a conclusion from the numbers.

> **Note on this paragraph (added in fix round 1):** the parenthetical
> "(16-day-old at this snapshot)" above was added by the evidence-snapshot
> commit (`docs(evaluation): rubric evidence snapshot`), which edited this
> **pre-registered** Direction paragraph from commit 1 — a slip against this
> document's own rule that criteria/directions, once pre-registered, are
> only ever touched by a follow-up commit with a note, never silently
> rewritten by the value-filling commit. It cannot be unmade without
> rewriting history, which this document also forbids. Recorded here
> instead, transparently: the edit is **additive-only** — it updates a
> day-count as time passed between pre-registration (2026-08-04) and
> retrieval (2026-08-05), without changing the criterion's meaning, its
> direction, or the "repo created 2026-07-20" annotation itself. No value
> cell was affected by this edit.

| Extension (repo created 2026-07-20)                                                                                                                                                                                                                                                                                                                                                                                                                                          | tier4-native                                                                                                                                                                                                                                                                                                                                                                             | Bridge (path-scoped, `simulator/autoware_carla_interface`)                                                                                                                   |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **This repo:** 25 lifetime commits = 25 in the past 90 days (repo is 16 days old at snapshot time) = **1** distinct contributor in 12 months. **Required fork delta:** 219 lifetime, **100** in the past 90 days, **25** distinct author emails in the past 12 months (corrected in fix round 1 from a hand-count error of 24; the script now pipes this count through `wc -l` instead of requiring a reader to count a printed list) (shared-ancestor caveat: Criterion 6). | **305 lifetime**, **0** commits in the past 90 days (`tier4/autoware-support`'s own tip is `6315b856f` dated **2026-04-08** — about 4 months stale as of this snapshot, not merely "~2026-05" as the spec estimated), **24** distinct author emails in the past 12 months (a trailing tail on a branch that has stopped moving; see Criterion 9 for the CI-silence that goes with this). | **42 lifetime** commits (earliest 2024-07-19, latest 2026-07-24), **8** in the past 90 days, **10** distinct author logins in 12 months (9 human + `awf-autoware-bot[bot]`). |

### 8. Install complexity (steps, build hours, disk)

**Direction:** lower is more favorable — fewer manual steps, less build
time, less disk footprint to get from zero to a running stack.

| Extension                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | tier4-native                                                                                                                                                                                                                                                                                                                                         | Bridge                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Required fork shares the **same** UE5.5-source-build cost floor as tier4-native (not separately documented in this repo, since that build lives in the sibling fork repo). The extension `.so` itself builds in well under a minute (`cmake`+`ninja`, plain C++, no UE toolchain — see `ci.yaml`'s `cpp-tests` job). ~6 top-level bring-up steps documented in [`docs/running-e2e.md`](https://github.com/autowarefoundation/carla-autoware-extension/blob/main/docs/running-e2e.md) (build → container up + bootstrap → CARLA+extension+runner → Autoware → RViz → arm). | **~300 GB free disk**; **3–4 hours** to build Unreal Engine from source, plus **up to 1 hour** for the first editor build (both figures verbatim from the [`autoware-support` README](https://github.com/tier4/carla-autoware-native/blob/autoware-support/README.md)); ~5 install-script steps + separately install ROS 2 Humble + Autoware 0.45.1. | No CARLA source build at all: download a stock CARLA 0.9.15 release binary + pip-install a prebuilt ROS 2 Humble communication package + fetch/reshape Lanelet2 map assets + a normal `colcon build` of one package. ~5–6 steps, no multi-hour build, no unusual disk footprint (per the [bridge README](https://github.com/autowarefoundation/autoware_universe/blob/main/simulator/autoware_carla_interface/README.md); no hours/disk figure is stated there because none is needed). |

### 9. Automated test/CI coverage of the integration path

**Direction:** higher/more coverage is more favorable — CI that actually
exercises the CARLA↔Autoware integration path (not just a generic build) is
stronger evidence of ongoing correctness than CI that doesn't touch it.

| Extension                                                                                                                                                                                                                                                                                                                                                         | tier4-native                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Bridge                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One workflow, [`ci.yaml`](https://github.com/autowarefoundation/carla-autoware-extension/blob/main/.github/workflows/ci.yaml): `cpp-tests` builds+links the extension `.so` against ROS 2 Jazzy and runs its gtest suite + checks the exported `carla_ros2_extension_init` ABI symbol; `pytest` runs the Python runner's tests. No live CARLA+Autoware run in CI. | All 6 CI workflows target `ue5-dev` (push/PR) or are `workflow_dispatch`-only placeholders ([`ue5_pr.yml`](https://github.com/tier4/carla-autoware-native/blob/main/.github/workflows/ue5_pr.yml) triggers on PRs into `ue5-dev`, not `autoware-support`). **The only CI run ever recorded on `autoware-support`** (`gh api repos/tier4/carla-autoware-native/actions/runs?branch=autoware-support`) is a single Dependabot-style "pip … Jinja2 - Update" event, 2025-09-15 — zero real build/test runs have ever validated the native-integration branch itself. | `autoware_universe`'s repo-wide [`build-and-test-differential.yaml`](https://github.com/autowarefoundation/autoware_universe/blob/main/.github/workflows/build-and-test-differential.yaml) builds any PR-touched package including this one, but the package has no `test/` directory and its `CMakeLists.txt` explicitly disables `ament_cmake_flake8` under `BUILD_TESTING` — CI here means "does it build + pass generic ament lint," not a functional or simulator-backed test. |

**None of the three approaches runs a live CARLA+Autoware simulator loop in
CI** — this repo's own live-stack gates (G0–G3, `docs/e2e-report.md`) are run
manually per `docs/running-e2e.md`, not on every PR.

### 10. License

**Direction:** descriptive, not ranked — records the license each approach
ships under and whether it is compatible with the other two / with upstream
CARLA and Autoware licensing.

| Extension                          | tier4-native                                                         | Bridge                                                                      |
| ---------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Apache License 2.0 (repo license). | MIT (repo license; inherited from upstream CARLA's own MIT license). | Apache License 2.0 (`package.xml` + `autoware_universe` host-repo license). |

All three are permissive and mutually compatible.

### 11. Documentation quality

**Direction:** higher/more comprehensive is more favorable — this is a
qualitative judgment (presence of install guide, architecture doc,
troubleshooting record, etc.), recorded with links to what was found, not a
numeric score.

| Extension                                                                                                                                                                                                                                                                                                                | tier4-native                                                                                                                                                                                                                                                                                                      | Bridge                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 8 dedicated docs under [`docs/`](https://github.com/autowarefoundation/carla-autoware-extension/tree/main/docs) (~130 KB combined): `architecture.md`, `e2e-report.md`, `environment.md`, `g0-report.md`, `mgrs-handedness.md`, `nishishinjuku-map.md`, `prerequisites.md`, `running-e2e.md`, plus the top-level README. | One 349-line [`autoware-support` branch README](https://github.com/tier4/carla-autoware-native/blob/autoware-support/README.md) (install guide + demo instructions); the repo's `Docs/` directory (ReadTheDocs source) carries **zero** autoware-specific files — it's the plain upstream CARLA doc site content. | One 301-line [README](https://github.com/autowarefoundation/autoware_universe/blob/main/simulator/autoware_carla_interface/README.md) + a `docs/images` folder (illustrations only) + an auto-generated `CHANGELOG.rst`; no separate architecture/troubleshooting doc. |

## Known outcomes checked against this snapshot

The design spec (`2026-07-27-three-approach-evaluation-design.md`,
"Community-acceptance rubric" section) stated these expected outcomes ahead
of the snapshot. Each is checked below against live data: confirmed
verbatim, corrected, or marked unverifiable-with-link.

**Extension — "solo-authored with zero external reviewers so far... requires
an unmerged fork (mitigation: the staged upstream PR pipeline, #9743–#9758
already merged)."** CONFIRMED for the repo itself, with a scope
clarification: every commit and every PR on `autowarefoundation/carla-autoware-extension`
since its creation is authored by `youtalk`, and the only "reviews" in the
PR history are two self-reviews (`#8`, `#12`) — zero external reviewers,
exactly as claimed (`gh pr list --repo autowarefoundation/carla-autoware-extension --json author,reviews`).
The required fork is more collaborative than "solo" might suggest read in
isolation — see Criterion 6 — but that is additive detail about the fork,
not a contradiction of the claim about the repo and its review process. The
mitigation PR pipeline is CONFIRMED: of the 16 numbers in `#9743`–`#9758`,
the 8 that belong to `JArmandoAnaya`'s staged pipeline are all MERGED, plus
`youtalk`'s unrelated-topic `#9744` and `#9749` (also MERGED) — see
Criterion 4 for the full number-by-number recheck, including the 5 numbers
that are gaps (not PRs at all) and the 1 (`#9750`) that is an unrelated
third author's closed, unmerged PR.

**Bridge — "version-locked to 0.9.15 with the 0.10 direction contested
(four opened-and-closed PRs, then draft #13077 pivoting to SplatSim)."**
The 0.9.15 version lock is CONFIRMED verbatim (the bridge README's own
"Supported Environment" table still lists `carla: 0.9.15` as of this
snapshot). The PR count and #13077's state are CORRECTED:

- Fresh search finds **five**, not four, PRs explicitly mentioning CARLA
  0.10 by the same author (`hakuturu583`), all opened-and-closed, none
  merged: [`#13048`](https://github.com/autowarefoundation/autoware_universe/pull/13048),
  [`#13049`](https://github.com/autowarefoundation/autoware_universe/pull/13049),
  [`#13051`](https://github.com/autowarefoundation/autoware_universe/pull/13051),
  [`#13052`](https://github.com/autowarefoundation/autoware_universe/pull/13052),
  [`#13060`](https://github.com/autowarefoundation/autoware_universe/pull/13060).
- [`#13077`](https://github.com/autowarefoundation/autoware_universe/pull/13077)
  ("add SplatSim v1.2.0 gRPC rendering integration") was a draft when the
  spec was written (created 2026-07-27, the same day) but has **since been
  closed** (2026-07-29), unmerged — it is no longer an open draft as of
  this snapshot.
- A further successor, [`#13089`](https://github.com/autowarefoundation/autoware_universe/pull/13089)
  ("add SplatSim gRPC rendering integration"), opened the same day #13077
  closed (2026-07-29) and is the PR **currently open** as of this snapshot
  — and unlike all five of its predecessors, it is **not** marked draft.

  So the freshly-counted "0.10 direction" chain is: 5 closed 0.10-labeled
  PRs → 1 closed SplatSim-pivot PR (`#13077`) → 1 currently-open, non-draft
  SplatSim PR (`#13089`). None of the six PRs found have been merged; CARLA
  0.10 support itself has not landed.

**tier4-native — "issues disabled, zero forks, no upstreaming, stalled
sync."** CONFIRMED, and the staleness is sharper than the spec's estimate:

- `has_issues: false` CONFIRMED (`open_issues_count: 7` in the same API
  response is not a contradiction — GitHub counts open PRs in that field
  even when Issues is disabled).
- `forks_count: 0` CONFIRMED.
- No upstreaming CONFIRMED, **scoped correctly as of fix round 1**: the
  delta's 4 actual Robotec/tier4-specific authors each have zero PRs to
  `carla-simulator/carla`. (The original wording, "zero PRs from any of the
  delta's actual authors," was broader than any command run and false as
  literally written — several delta authors are shared-ancestor
  CARLA-community contributors with large upstream PR histories unrelated
  to tier4-native's own work; see Criterion 4.) A text search for `"tier4"`
  / `"robotec"` across that repo's PRs also returns zero hits, kept for
  context only.
- Stalled sync CONFIRMED and SHARPENED: the spec estimated the sync
  stalled "~2026-05"; this snapshot finds `tier4/autoware-support`'s own
  tip commit dated **2026-04-08**, with **zero** commits landed on the
  branch in the 90 days before this snapshot, and its CI having fired
  exactly **once**, ever, on that branch — a dependency-bump automation
  event (2025-09-15), never a real build/test (Criteria 7 and 9). Fix round
  1 adds one more data point in the same direction: `autoware-support` is
  not merely un-synced, it is **frozen** at the ruleset level — `creation,
update, deletion, non_fast_forward` are all blocked, with no
  `pull_request`/approval rule ever reaching the branch either (Criteria 1
  and 2).

## Fix round 1 (commit 3)

An adversarial re-verification pass re-ran the snapshot script's underlying
commands and found 5 issues, all fixed in commit 3 without touching commits
1 or 2:

1. **Criterion 4, extension cell** — `JArmandoAnaya`'s PR breakdown was
   captured at `gh search prs --limit 50` and returned exactly 50 results
   (38 merged + 12 open + 0 closed) — a silent truncation, not the true
   total, that happened to erase 2 real closed-unmerged PRs and erred in the
   extension's favor. Re-run at `--limit 200`: 43 merged / 12 open / 2
   closed of 57 total. True combined ratio: **66 merged of 98 opened ≈
   67.3%** (was 61/91 ≈ 67%). Fixed: the cell, and the script (a
   `pr_state_breakdown` helper now used for every author-scoped PR search,
   at `--limit 200`, with a `WARNING` line if a result count ever equals the
   limit again).
2. **Criteria 1 and 2, tier4-native cells** — conflated two different
   rulesets' conditions and rules. The authoritative per-branch endpoint
   (`gh api repos/tier4/carla-autoware-native/rules/branches/autoware-support`)
   shows only `creation, update, deletion, non_fast_forward` apply to
   `autoware-support` — no `pull_request`/approval rule reaches it at all.
   Fixed: both cells rewritten to the corrected (and sharper — "frozen, no
   review gate," not "1 review required") reading; the script now queries
   the per-branch endpoint directly instead of resolving a ruleset by name.
3. **Criterion 4, tier4-native cell** — "no PR from any of the delta's
   actual authors" was broader than any command run and false as literally
   written: shared-ancestor CARLA-community delta authors (`glopezdiest`,
   `Blyron`, `mackierx111`) have substantial upstream PR histories. Fixed:
   the claim is scoped to the delta's 4 Robotec/tier4-specific authors
   (still zero PRs each), and the script now runs both the scoped-zero and
   the shared-nonzero author searches explicitly.
4. **Criterion 7, extension cell** — "24 distinct author emails" was a
   hand-count error; the redirected script output already contained 25
   lines. Fixed: the cell now says 25; the script pipes both forks'
   12-month-distinct-author counts through `wc -l` so the number is
   machine-produced, not hand-counted.
5. **A pre-registration-text edit in commit 2** — commit 2 added
   "(16-day-old at this snapshot)" inline into §7's pre-registered Direction
   paragraph from commit 1, which this document's own rule reserves for a
   follow-up commit with a note. It cannot be unmade (no history rewrite);
   the note now sits directly under that paragraph, stating the edit is
   additive-only and affected no value cell.

## Reproducing this snapshot

`scripts/evaluation/rubric_snapshot.sh` contains the exact `gh api` / `git`
command that produced every value above. Re-run it
(`bash scripts/evaluation/rubric_snapshot.sh`) to refresh the snapshot;
re-running it does **not** authorize editing the criterion list or
directions above without a follow-up commit that explains the change — see
the note at the top of this document. The script requires `gh` to be
authenticated and, for the fork-delta and bus-factor cells, the two local
sibling clones CLAUDE.md documents (`~/src/carla-autoware-integration`,
`~/src/carla-autoware-native`); if a clone isn't present, that section
prints a `SKIP` line rather than failing the whole snapshot.
