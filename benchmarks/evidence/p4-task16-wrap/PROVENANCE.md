# `p4-task16-wrap/` — provenance

Filed 2026-08-04 by P4 Task 16, review fix round 1. Two files.

| file                | sha256                                                             | what it is                                                 |
| ------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------- |
| `identity_walk.py`  | `6249644080fe3d0273ae76b6547925487bd30db3518c018db464080cf0fbd0bd` | the walk behind `docs/evaluation/p4-transport-sweep.md` §9 |
| `identity-walk.log` | `a08ce4a0c6774de829994ae0dd35a90a959abb8af6935e3dedb169123e1eddb2` | that script's stdout, captured with `>` (not `\| tee`)     |

Both files are excluded from the text-mutating pre-commit hooks
(`.pre-commit-config.yaml` excludes `^benchmarks/evidence/(?!.*\.md$)`), so these
digests are stable across `pre-commit run --all-files`; verified before and after
a full hook pass. This `PROVENANCE.md` is a `.md` and **is** formatted by
prettier, which is why its own digest is deliberately not listed.

Regenerate both, from the repository root:

```bash
PYTHONPATH=. python3 benchmarks/evidence/p4-task16-wrap/identity_walk.py \
  > benchmarks/evidence/p4-task16-wrap/identity-walk.log
sha256sum benchmarks/evidence/p4-task16-wrap/*
```

## Why this directory exists

Review round 1 of Task 16 raised two findings that were one defect. The wrap's
§9.1 asserted the engine BuildId was constant "across all 91 P4 runs" — a count
**no filed command produced**, and one reconstructible from no partition of the
filed data. Separately, the walk that sentence was cited to aggregated only
`engine_build_id`, `autoware_image` and `dds_profile_sha256`, so §9.2's entire
per-pool `harness_git_sha` table and §9.3's `patches_git_sha` claim — including
the load-bearing "both duel pools are sha-matched and clean, a provenance
improvement over P3" — had **no runnable command behind them at all**, against
the wrap's own §0.1 rule that every number does.

The coordinator's ruling was to fix it at the source rather than swap the count:
extend the walk to emit the shas and the run count, then quote whatever it
actually produces, and state the count discrepancy as a fact rather than
replacing it quietly. That is what this script does.

## What it does and does not contain

It reads `benchmarks/results/*/run-*/manifest.json` and **nothing else** — no
observer CSV, no `quality.json`, no `resources.csv`. It writes nothing. It is
deterministic: two consecutive runs are byte-identical.

**It contains no duel verdict, no delta, no median and no cross-cell performance
comparison.** Every value it prints is an identity key (a git sha, an engine
BuildId, an image reference, a DDS profile digest) or a count of runs. The
no-peeking rule that governed Tasks 10–15 would have permitted this script
unchanged; it is filed under Task 16 only because that is when the need for it
was found.

## The two facts it establishes that no `PROVENANCE.md` section states

1. **The P4 boundary in cell A falls at `run-015`, not `run-016`.** `A/run-015`
   is Task 11's cell-A bring-up (`PROVENANCE.md` §14.2, `duel_admissible:
false`) and is the first cell-A run carrying both `patches_git_sha 7000c78`
   and `engine_build_id bc08ce19`. `A/run-014` carries `ccff4f9` / `4210e602`,
   and its `harness_git_sha f0f8b4b` is a 2026-07-31 P3-era commit.
2. **84 filed manifests carry `bc08ce19`; 89 filed runs are P4 runs.** The
   difference is CAL-seam's five, which carry **no** `placement.engine_build_id`
   key at all — `PROVENANCE.md` §12.2's structural finding (`preflight.sh`'s
   BuildId check is gated on `APPROACH = extension | tier4-native`, and CAL-seam
   registers `calibration`), not drift. **Zero P4 manifests carry `4210e602`**,
   so the wrap's within-P4 single-identity claim stands on its substance; only
   the count previously attached to it was wrong.

## Why the P4 partition is selected on `patches_git_sha`

`write_manifest.py:30` defines that key as `git log -1 --format=%H --
benchmarks/patches/`, and it moved to `7000c785` — Task 9's registered relink
commit — at exactly the P3→P4 transition. Selecting on it partitions the filed
runs by the same event that moved the engine BuildId, so the boundary is
**derived from the data** rather than from a run-id range that would drift the
moment a run is added. The script's module docstring carries the full argument
and the `sha[:7]`-drops-`-dirty` trap the abbreviation helper exists to avoid.

## Test coverage, stated rather than implied

`tests/benchmarks/test_bundle_pin.py::test_every_evidence_directory_is_indexed_and_has_provenance`
covers this **directory**: it requires the name to appear in
`benchmarks/evidence/README.md`'s index table and requires this file to exist.
It caught the omission of both on the first run of the fix round.

**No test covers `identity_walk.py`'s behaviour**, and none is claimed.
`benchmarks/evidence/**` is excluded from the ruff and shellcheck hooks
(`.pre-commit-config.yaml`, and `PROVENANCE.md` §27.8 for why: a lint-driven
edit would make a certified producer no longer the file that produced the
recorded figure), and this campaign files evidence scripts as verbatim producers
rather than as library code. What is verified instead, and was verified for this
one: the script exits 0, two consecutive runs are byte-identical, and every
non-blank line of `identity-walk.log` appears byte-exactly in the wrap
document's quoted block. `PROVENANCE.md` §27.5's lesson — "an instrument that
cannot fail is not an instrument" — does not bite here, because this script
makes no pass/fail judgement: it is a census, and a census that printed the
wrong thing would contradict the manifests it is a census of.
