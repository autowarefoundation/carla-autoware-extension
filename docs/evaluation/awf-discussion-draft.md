> **DRAFT — not posted. For AWF community discussion.**

# Proposal: an out-of-tree extension as the community CARLA↔Autoware path

**This is a draft for private review. It has not been posted anywhere, and it
should not be posted until someone other than its author has checked it against
the evidence it summarises.**

The evidence behind every claim below lives in three documents in this
directory: [`report.md`](report.md) — the argued evaluation report;
[`rubric.md`](rubric.md) — the community-acceptance snapshot;
[`gap-catalog.md`](gap-catalog.md) — the 53-entry capability catalog. **This
document argues; those documents prove.** Every figure quoted here is quoted
together with the caveat `report.md` attaches to it, because several of the
figures mean much less than they look like they mean. Where this draft and the
report disagree, the report wins.

## 1. The ask

There are three ways to connect CARLA to Autoware today, and no community
decision about which one the Autoware Foundation supports. This draft asks the
working group for four things:

1. **Read the evidence and decide whether an out-of-tree extension is the
   architecture the community wants to back.** Not "is it the fastest" — the
   measurements do not answer that, and §3 explains why not — but "is a
   `.so` behind a frozen C ABI plus a declarative runner the right shape for
   something the community has to maintain for years".
2. **If yes, fix the thing a working group can actually fix.** The extension's
   weakest property is not technical, it is governance: one maintainer, zero
   external reviewers. Naming reviewers and co-maintainers costs the working
   group very little and removes the single largest objection to this proposal
   (§5).
3. **Open the capability roadmap.** The gap catalog is 53 entries with an
   argued reproduction path for each (§4). Most of the community-workable ones
   are small; the large ones need CARLA-core changes and would benefit from
   being planned in public rather than rediscovered per fork.
4. **Do not read this as a verdict against the other two approaches.** The
   campaign computed **no** equivalence or ranking statistic between the
   python-bridge and either native approach, in either measurement phase, and
   none may be inferred (`report.md` §0, §4.5). The comparison that does exist
   is narrower than it looks, and §3 states its limits before its results.

## 2. The three approaches

| approach          | what it is                                                | where it lives                                     |
| ----------------- | --------------------------------------------------------- | -------------------------------------------------- |
| **extension**     | out-of-tree `.so` behind a frozen C ABI + a Python runner | `autowarefoundation/carla-autoware-extension`      |
| **tier4-native**  | native ROS 2/DDS compiled into a CARLA UE5 fork           | `tier4/carla-autoware-native` @ `autoware-support` |
| **python-bridge** | `autoware_carla_interface`, an in-tree Python bridge node | `autowarefoundation/autoware_universe`             |

All three were measured or catalogued under one pre-registered protocol:
metric definitions, equivalence margins, exclusion criteria and the ceiling
evaluator were all committed **before the first measurement run existed**
(`report.md` §2.1). Stated exactly, because the report refuses the stronger
reading: **that is a provenance fact, not a blinding one** — one author and a
git DAG cannot show when a number was first seen — and the report records its
own exceptions in place rather than claiming a clean sheet: one margin was
frozen mid-campaign under an amendment rule that `margins.yaml` itself concedes
"cannot both hold literally", and the rubric's value-filling commit edited a
pre-registered direction paragraph (`report.md` §2.1).

## 3. What the evidence shows — and what it does not

### 3.1 Extension versus tier4-native, driving

The campaign's strongest result is a closed-loop comparison against
tier4-native, ten runs per side, on all five pre-registered metrics. The
report's own surviving wording, verbatim:

> on the closed-loop arm under a shared transport family — **and across an
> uncorrected Autoware image difference** — the extension and tier4-native
> stacks are **within the pre-registered margins on four of five metrics and
> separated beyond margin on the fifth, in tier4-native's favour, for reasons
> this campaign did not establish** (`report.md` §3.3)

Four qualifications travel with that sentence and are not optional:

- **It compares tier4-native on CycloneDDS, not on the transport tier4-native
  ships.** The report calls this arm `A-vs-B-cyc`. The comparison against
  tier4-native's own as-shipped Fast-DDS configuration (`A-vs-B`) is
  **permanently non-computable**: that configuration armed on **0 of 15**
  closed-loop runs (`report.md` §3.3, §1.2). The two must not be conflated.
- **Every row also spans an Autoware container-image difference**
  (`universe-devel-cuda` by digest against `universe-devel` by tag), which the
  source calls "the single most important" confound in it, and **no row is
  corrected for it** (`report.md` §0 rule 3, §3.3).
- **The four "within margin" rows are not four equal results.** One is a
  knife-edge at **97.1 %** of its own margin, on a metric whose instrument
  residual is **27×** that margin — and under a slightly narrower margin the
  decision rule does not return "undecided", it returns **tier4-native better**,
  on a **3 %** change in a threshold the measured calibration never determined.
  Another has a degenerate confidence interval and contributes no evidence at
  all. The report's own reading: "the effective evidentiary weight is closer to
  **two well-supported parity rows than four**" (`report.md` §3.3, §3.2).
- **The fifth metric goes against the extension.** Simulator-process CPU
  separates by **+58.250 pp** (CI [57.662, 59.161]) against a 10.0 pp margin,
  in tier4-native's favour, and **the cause is not established**. A registered
  confound runs against the extension on exactly this metric — its sensor rig
  is configured at 20 Hz against tier4-native's 10 Hz and ships **2.118×** the
  bytes for the same point count — but the report also carries that confound's
  own refutation: it "was present in P3 [the earlier measurement phase]
  unchanged — **where cell A [the extension] won the row anyway** — so **it
  does not explain the reversal on its own**" (`report.md` §3.2). This is the
  largest thing the campaign found and did not resolve.

And `parity` here is a decision against a frozen margin, **not a proof of
identity** and not a calibrated 95 % equivalence statement — the estimator's
interval coverage was never validated, and its expected failure mode runs in
the direction that favours this report's headline (`report.md` §2.2).

### 3.2 The static comparison, and what it re-attributed

A second, static comparison spans two phases. Under mismatched transports the
extension separated from tier4-native on every computable metric. Under a
**shared** transport family, **three of the four returned `parity`; the fourth
reversed against the extension, beyond margin, cause unestablished** —
simulator-process CPU, Δ **+52.005 pp** (CI [49.617, 52.871]) against a 10.0 pp
margin, where the earlier phase had read **−12.873 pp** in the extension's
favour. For the three, the pre-registered rule attributes the earlier
separation to the as-shipped Fast-DDS configuration, **not to the approach**;
it does **not** license retro-attributing the CPU row's earlier reading, and
**the two cannot both be an approach difference** (`report.md` §3.2). Four
caveats gate that:

- **It closes on four of the five pre-registered margin metrics, not five** —
  control-command staleness was unavailable throughout the earlier phase and
  `insufficient-data` in the later one.
- **The earlier phase was cross-vendor**: the extension ran on CycloneDDS with
  a loopback-only profile, tier4-native on Fast-DDS with a **harness-authored**
  profile it did not ship — the largest caveat on that phase, and the reason
  the second phase exists (`report.md` §1.2).
- **The flips are three views of one condition, not three findings**, and the
  report says so in advance; one flipped from a verdict already compatible with
  practical equivalence, and one has a degenerate interval. The instrument is
  implicated too: on the earlier phase's tier4-native side the clock-fit
  residual median is **22.48 ms** — **11×** the 2.0 ms margin and **3.6×** the
  delta the verdict was built on (`report.md` §3.2).
- **Every shared-transport row also spans the same Autoware image difference**
  as §3.1's rows: "every A-vs-B-cyc row in this document also spans an image
  difference, and no row … is corrected for it" (`report.md` §0 rule 3, §3.2).

Read together: on the latency and rate metrics, on this workload, the extension
pays no measurable systems-level penalty against an in-fork native
implementation — on a comparison weaker than a clean A/B, and stated as one.
**On simulator-process CPU it does pay one**, on both arms, beyond margin and
in tier4-native's favour. The report calls that reversal "the largest thing P4
discovered and did not resolve" (`report.md` §8), and §3.1 above carries both
the confound that runs against the extension on that metric and the report's
own finding that the confound does not explain it.

### 3.3 The cost of the seam itself

The extension's defining choice is routing Autoware vocabulary through a frozen
C ABI instead of compiling it into CARLA core. That seam was measured directly,
both twins publishing an identical 921 908-byte cloud inside one CARLA process:
**median +0.2784 ms, all five runs inside +0.2392…+0.2988 ms, positive in 5 of
5** (`report.md` §3.1).

**That is an upper bound on the seam mechanism's share, not a point estimate** —
a rule registered before the runs were collected — so quote **+0.2988 ms**
where a ceiling is wanted. Against the claim as registered ("no measurable
overhead") the honest reading is a downgrade: an overhead _was_ measured. What
the data supports is that the seam's cost is **small and bounded, not zero**.
The tails do not separate, and no claim is made about them at n = 5.

### 3.4 The python-bridge

**Nothing here is a finding against the bridge, and the report is explicit that
its registered claim about the bridge is not established** (`report.md` §4):
there is no ceiling measurement on the bridge at all — it was out of the
sweep — no cross-approach statistic, and the byte-layout argument the spec
registered is **retracted as unmeasured**. One within-approach contrast
survives and is worth the working group's attention:

- As shipped, the bridge starves Autoware's NDT localization: **0.08–0.27 Hz**.
  With **both registered patches applied** — the one-line `is_dense` fix _plus_
  a harmonized sensor rig and topic remap — the same measurement reads
  **1.91–7.52 Hz** on the same architecture, CARLA and container; the pooled
  medians differ by **≈ 45×** and the ranges do not overlap
  (`report.md` §4.2, §4.3). Two caveats on that contrast: the patched arm's
  **20 Hz target is the campaign's own comparability choice, not the bridge's
  default — its authors ship 11** (`report.md` §4.3); and every as-shipped
  figure is **optimistically biased**, three of the four runs excluded from that
  pool being the cell's three worst, with the bias not estimable from the
  surviving pool (`report.md` §4.2).
- **The cause is a two-sided interop contract mismatch, not a bridge
  architecture property**: the bridge publishes `is_dense=False` (a valid,
  conservative PointCloud2 value) and Autoware's `crop_box_filter_self`
  **rejects every cloud carrying it**. The Autoware half of that seam is as
  much a finding as the bridge half (`report.md` §2.3, §4.2).
- The bridge's one closed-loop attempt at the registered configuration failed
  at the route link — **cause not established, denominator 1**. Nothing
  establishes an intrinsic closed-loop property of the bridge, and the failing
  component is the same one that failed tier4-native's arms on the same host
  (`report.md` §4.3).

And the bridge holds the one adoption property neither native approach has: it
is the only one of the three that **runs against an official upstream CARLA
release binary** (`report.md` §3.5, rubric criterion 5 — extension **No**,
tier4-native **No**, bridge **Yes**).

### 3.5 The structural comparison

The extension carries **219** fork commits ahead of upstream CARLA plus **25**
in its own repo; tier4-native carries **305**; the bridge carries **0**, being
in-tree. Every figure here is a **dated snapshot over moving refs, not a
regenerable number** (endpoint SHAs are pinned in the report). Two things that
look like a comparison and are not:

- **The upstreaming figures are computed over different populations.** The
  extension fork's two dominant authors show **66 merged of 98 opened**
  (≈ 67.3 %) against `carla-simulator/carla` — but that is every PR they ever
  opened over their whole careers, unrelated-topic ones included, and **43 of
  the 66** belong to a CARLA-side contributor whose upstream record largely
  predates and is independent of this extension. The tier4 **0** is scoped to
  four named Robotec/tier4-specific delta authors and deliberately _excludes_
  shared-ancestor CARLA-community delta authors with large upstream histories
  (`glopezdiest` 82, `Blyron` 145) who also appear in the extension's own fork
  delta. **No ordering between the two cells is supported** (`report.md` §3.5).
- **The tier4 branch this campaign measured is frozen; tier4's development is
  not.** The `autoware-support` integration branch is tipped 2026-04-08, **0**
  commits in the 90 days before the snapshot, CI fired once ever. In the same
  clone at the same moment, **`tier4/main` — the repository's actual default
  branch — is tipped 2026-07-07 with 205 commits in that same window and 26
  distinct author emails in 12 months**, and nine of the branches this campaign
  catalogs as side branches are already merged into it. Scoping the capability
  comparison to `autoware-support` is correct — it is the branch that was built
  and measured — **but no sentence here is a maintenance verdict on
  tier4-native the approach** (`report.md` §3.5, §6).

## 4. The capability roadmap

[`gap-catalog.md`](gap-catalog.md) catalogs **53 capability entries** across
tier4-native's integration branch and its side branches, each with an argued
reproduction path on the extension architecture; [`report.md` §5](report.md)
summarises it. It is **code reading at pinned SHAs — no running stack, no
runtime measurement backs any verdict in it** — and six entries carry a scoped
`needs prototype` marker where that method reaches its edge (`gap-catalog.md`
§5.0, §7.4).

| class                              | main branch | side branches | total  |
| ---------------------------------- | ----------- | ------------- | ------ |
| already exists in the extension    | 11          | 3             | 14     |
| extension-side work                | 4           | 4             | 8      |
| CARLA-core seam work — sensor-side | 6           | 15            | 21     |
| CARLA-core seam work — ROS-side    | 7           | 3             | 10     |
| **entries**                        | **28**      | **25**        | **53** |

Effort classes: main branch **25 × S, 3 × M**; side branches **13 × S, 8 × M,
4 × L**. Four things a reader must carry with that table:

- **A class is the remaining delta from this repository's side, not the size of
  tier4's original change**, and classes are **per-entry, not cumulative**.
  Five of the main-branch S entries are S _only because_ the extension's own
  required CARLA fork independently re-implemented the same core change; two
  more are S on code volume while their remaining work is a **C ABI version
  bump**, a compatibility cost the class does not price. "89 % of tier4's
  merged integration work is a small lift" is **not** what the table says
  (`report.md` §5, `gap-catalog.md` §7.3, §5.0.4).
- **Three entries depend on artifacts that exist in neither tree**, so their
  cost is a lower bound rather than a reachability class: a raw-UDP packet
  encoder that lives in a **private** repository of unestablished
  obtainability, an Agnocast capability needing a kernel module that exists in
  neither tree, and 35 Japanese signal `.uasset` files of unestablished
  redistributability (`report.md` §5, `gap-catalog.md` §7.1).
- **The side-branch half skews far harder toward CARLA-core seam work —
  18 of 25, against 13 of 28 on main** — i.e. the integration branch's
  capabilities are largely ROS-layer and the side branches' largely are not.
  **That statistic received no second pass** and rests on a single analyst's
  code-reading judgement with no inter-rater check (`report.md` §5).
- The adversarial re-argument that found nothing overturned covered the
  **14 `already-exists` verdicts only** — the entries carrying the overclaim
  risk. The other 39 received one classification pass each (`report.md` §5).

## 5. Where this proposal is weak

The extension repository is **solo-maintained with no external review**: one
maintainer, every commit by one author, **zero external reviewers across
30 PRs**, the only recorded reviews being two self-reviews, no CODEOWNERS, and
a branch ruleset that requires passing checks rather than a human approval. By
comparison the bridge has 4 named maintainers and 9 human authors in
12 months, and tier4-native's branch — though no better governed — is at least
two-contributor dominated (`report.md` §3.5, rubric criteria 1 and 6). **This
is a governance risk that the comparator's numbers do not offset**, and it is
the reason the ask in §1 leads with reviewers rather than with adoption.
The evaluation documents themselves share the defect: they are single-author
and adversarially self-reviewed, not externally reviewed, and the design spec
they were registered against lives outside this repository, so the report's own
honesty checklist is **self-certifying** until that spec is published
(`report.md` §0, §8).

The extension is also **not fork-free today**. It requires building a CARLA
UE5.5 fork from source — **the fork is the artifact** — exactly as
tier4-native does, and on the rubric's "runs against an official upstream
release binary" criterion both natives read **No** while the bridge reads
**Yes**. That is the largest real-world adoption differentiator in the rubric
and it does not favour this proposal (`report.md` §3.5). Nor does any of the
three approaches run a live CARLA+Autoware loop in CI, this one included; the
extension's own end-to-end gates are run manually.

The mitigation is that **the fork is staged for upstream rather than held**:
the extension's named upstream mitigation chain, `#9743`–`#9758` against
`carla-simulator/carla`, was rechecked number by number, and the staged ROS 2
pipeline PRs in it are merged. Stated precisely, because the loose reading is
wrong: **not every number in that inclusive range is a merged PR** — several
are number-sequence gaps that are not PRs at all, one is an unrelated third
author's closed, unmerged PR, and two of the merged ones are unrelated-topic
PRs by the fork author ([`rubric.md`](rubric.md), criterion 4 and "Known
outcomes"). The pipeline is real and it merged; "every number in that range is
a merged PR" is not what the recheck found, and the 67.3 % figure in §3.5 must
not be read as a like-for-like upstreaming ratio against tier4's 0.

## 6. Proposed next steps for the working group

1. **Assign a reader.** One person outside this repository reads
   [`report.md`](report.md) and challenges its caveats. The report's known
   residual weaknesses are listed in its §8 and §8.1 rather than left for a
   reviewer to find; start there.
2. **Publish the design spec.** The report's honesty checklist and every
   registered-claim quotation are self-certifying while the spec sits outside
   the repository. Publishing it is the only fix, and it is cheap.
3. **Name external reviewers and co-maintainers for the extension repo**, add
   CODEOWNERS, and require a human approval on `main`. This directly retires
   the weakest row in §5 and is the one item the working group can complete
   without any new measurement.
4. **Ask tier4 which ref a joint effort should target.** The capability
   comparison here is scoped to `autoware-support`, which is frozen, while
   tier4's own development continued on the `ue5-dev`/`main` lineage. Whether
   `autoware-support` is intended to be revived materially changes what the
   roadmap in §4 should be diffed against.
5. **Fix the `is_dense` ⇄ `crop_box_filter_self` contract mismatch on the
   Autoware side.** It is a two-sided seam defect, it starves NDT on the
   as-shipped bridge today (§3.4), and repairing it helps whichever path the
   community picks. Note what §3.4's ≈ 45× is and is not: a contrast between
   two **pooled medians** measured under different patch sets and a different
   rate target — **no paired design exists between the arms, so no per-run
   recovery factor is computable** (`report.md` §4.2). This step is not a
   promise of one.
6. **Scope the first roadmap slice in public**: the 8 extension-side entries
   are the community-workable ones; the seam entries (21 sensor-side, 10
   ROS-side) need CARLA-core PRs and should be planned against the upstream
   pipeline rather than re-forked.
7. **Treat any future head-to-head as needing a fresh design.** A comparison
   that a working group could rely on needs a matched Autoware image, a
   pre-registered multiplicity correction, and a validated interval estimator —
   this campaign has none of the three, and says so
   (`report.md` §2.2, §8.1).
