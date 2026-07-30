#!/usr/bin/env python3
"""Answer "which pinned map bundle is actually installed?" by content hash.

    python3 -m benchmarks.scripts.bundle_pin <path-to-pointcloud_map.pcd>

`benchmarks/pins.yaml` carries several candidate contents for the ONE path
`scripts/e2e/map_defaults.sh` resolves and `docker/compose.yaml` mounts for a
map -- for Town10 the rigid re-registrations (`town10_pcd_shifted`,
`town10_pcd_refit`) and the regenerated bundle (`town10_pcd_regen`). Exactly
one can be installed at a time, so the invariant pins.yaml registers is:

    the file at that path hashes to the `sha256` of EXACTLY ONE pin block,
    and that block is the bundle the run used

-- never "whichever block is listed last", and never the directory name, which
is deliberately stable across rigid variants.

That invariant was registered with no consumer, which is the failure mode this
module exists to close: an invariant nothing checks is a comment. `preflight.sh`
calls this before a run so a bundle that matches NO pin (an unrecorded local
edit) or SEVERAL (two blocks pinning identical bytes, i.e. a duplicated
registration) is refused by name, up front, rather than silently measured and
attributed to whichever block a later reader guesses.

Exit 0 prints the matching key; exit 2 names the failure.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

import yaml

PINS = pathlib.Path(__file__).resolve().parents[1] / "pins.yaml"

# The pin blocks that describe candidate contents of a mounted bundle path.
# Listed explicitly rather than pattern-matched on the key name: a future
# `town10_pcd_something` that is NOT an installable bundle (a provenance-only
# record, say) must not silently join the candidate set and turn a legitimate
# single match into an ambiguous one.
BUNDLE_PIN_KEYS = ("town10_pcd_shifted", "town10_pcd_refit", "town10_pcd_regen")

EXIT_FAIL = 2


class BundlePinError(Exception):
    """The installed bundle does not correspond to exactly one pin block."""


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def installed_bundle_key(pins: dict, digest: str, keys=BUNDLE_PIN_KEYS) -> str:
    """The single pin key whose `sha256` equals `digest`.

    Pure, so the invariant is unit-testable without a map on disk. Raises
    `BundlePinError` naming the digest on zero matches and naming every
    colliding key on more than one -- both are registration faults, and
    neither is repaired here.
    """
    matches = [k for k in keys if k in pins and pins[k].get("sha256") == digest]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise BundlePinError(
            f"installed bundle sha256 {digest} matches no pin block in "
            f"pins.yaml (candidates: {', '.join(keys)}). An unrecorded bundle "
            f"cannot be measured: add its provenance block, or reinstall a "
            f"pinned bundle."
        )
    raise BundlePinError(
        f"installed bundle sha256 {digest} matches MORE THAN ONE pin block "
        f"({', '.join(matches)}); a duplicated registration makes the run's "
        f"bundle ambiguous. Remove the duplicate."
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pcd", help="path to the installed pointcloud_map.pcd")
    p.add_argument("--pins", default=str(PINS), help="pins.yaml path")
    args = p.parse_args(argv)

    path = pathlib.Path(args.pcd)
    if not path.is_file():
        print(f"BUNDLE PIN FAIL: {path} is not a file", file=sys.stderr)
        return EXIT_FAIL
    pins = yaml.safe_load(open(args.pins))
    try:
        key = installed_bundle_key(pins, sha256_file(path))
    except BundlePinError as exc:
        print(f"BUNDLE PIN FAIL: {exc}", file=sys.stderr)
        return EXIT_FAIL
    print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
