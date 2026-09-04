#### Summary

<!-- What does this change do, and why? -->

#### Verification

<!-- How did you check this? -->

- [ ] `pre-commit run --all-files` passes
- [ ] `python3 -m pytest tests -q` passes
- [ ] If this touches `scripts/e2e/`: a live gate run against CARLA `ue58-dev`
      (`scripts/e2e/run_gates.sh`), with the resulting `gates.txt`
