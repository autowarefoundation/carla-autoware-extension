#!/usr/bin/env python3
"""Answer "which pinned map bundle is actually installed?" by content hash.

    python3 -m benchmarks.scripts.bundle_pin <path-to-pointcloud_map.pcd>

`benchmarks/pins.yaml` can carry several candidate contents for ONE mounted
bundle directory -- for `town10-shifted` the rigid re-registrations
(`town10_pcd_shifted`, `town10_pcd_refit`). Exactly one can be installed at a
time, so the invariant pins.yaml registers is:

    the file at that path hashes to the digest of EXACTLY ONE pin block, and
    that block is the bundle the run used

-- never "whichever block is listed last", and never the directory name, which
is deliberately stable across rigid variants.

That invariant was registered with no consumer, which makes it a comment.
`preflight.sh` calls this before a run so a bundle whose bytes do not match its
registered provenance is refused up front rather than silently measured.

SCOPED PER BUNDLE DIRECTORY, which is the difference between protecting
provenance and blocking measurement. An earlier revision checked one flat
candidate list against every cell's bundle, so cells C/D -- whose
`nishishinjuku` bundle was not in that list -- matched zero blocks and were
FAILED, which would have blocked Task 15 and the whole C/D half of the
campaign. Absence of a registration is a gap in the record, not evidence of a
corrupted bundle, so the two are now distinct outcomes:

    matched              digest matches exactly one candidate  -> report it
    UNREGISTERED_BUNDLE  no candidates registered for this dir -> SKIP, named
    no_match             candidates exist, digest matches none -> FAIL
    ambiguous            digest matches two or more            -> FAIL

Only the last two are provenance faults. `no_match` is the one that matters
most: it means the bundle was edited without re-pinning, which is exactly the
silent-wrong-map failure this campaign exists to avoid.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys

import yaml

PINS = pathlib.Path(__file__).resolve().parents[1] / "pins.yaml"

# Which pin blocks may legitimately occupy each mounted bundle DIRECTORY, keyed
# by the directory's basename under ~/autoware_map. A key is either a top-level
# block name (its `sha256` field is used) or a dotted `block.field` path, which
# is how the unshifted Town10 bundle is reached: it is pinned as a field of
# `autoware_contents` by fetch_maps.sh, not as a block of its own, and copying
# that digest into a block of its own would break the mutually-distinct
# property the invariant depends on.
#
# A directory absent from this table yields UNREGISTERED_BUNDLE, so adding a
# new bundle is safe by default: it skips until someone pins it. The
# tier4-native cells' bundle is deliberately absent -- Task 13 owns what they
# mount, and preflight skips them for that reason rather than guessing.
BUNDLE_REGISTRY: dict[str, tuple[str, ...]] = {
    "town10-shifted": ("town10_pcd_shifted", "town10_pcd_refit"),
    "town10-regen": ("town10_pcd_regen",),
    "town10": ("autoware_contents.town10_pcd_sha256",),
    "nishishinjuku": ("nishishinjuku_bundle.pcd_sha256",),
}

# Host bundle directory each cell APPROACH actually mounts, for the approaches
# whose bundle is NOT the extension table's. Resolved from the launcher rather
# than from scripts/e2e/map_defaults.sh, because that table is the EXTENSION
# path's: cells/python-bridge.sh pins the UNSHIFTED ~/autoware_map/town10 for
# the E family, so resolving E through map_defaults.sh reported
# `town10_pcd_regen` -- the wrong bundle, written into the manifest as
# authoritative provenance, and the B family would have inherited the same
# mistake. `None` means "not resolvable here", which preflight treats as a skip:
#   python-bridge  -> cells/python-bridge.sh's MAP_BUNDLE_HOST (kept in step by
#                     tests/benchmarks/test_bundle_pin.py, which reads that
#                     literal out of the launcher and compares against this)
#   tier4-native   -> Task 13's $TIER4_DEMO; nothing here knows it yet
#   calibration    -> no localization stack, so no bundle to attribute
# `extension` is absent on purpose: it DOES use map_defaults.sh, so preflight
# resolves it per map from that table.
APPROACH_BUNDLE_DIR: dict[str, str | None] = {
    "python-bridge": "town10",
    "tier4-native": None,
    "calibration": None,
}

EXIT_FAIL = 2
EXIT_UNREGISTERED = 3


class BundlePinError(Exception):
    """A provenance fault: the bytes do not match the registered pin(s)."""


class BundleNotRegistered(Exception):
    """No pin block is registered for this bundle directory -- a gap in the
    record, not a fault. Separate from BundlePinError so a caller can skip
    rather than refuse; conflating the two is what turned this check into a
    blocker for every Nishi-Shinjuku run."""


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pin_digest(pins: dict, key: str) -> str | None:
    """The digest a key spec points at: `block` -> that block's `sha256`, or
    `block.field` -> that field. A miss at any level returns None rather than
    raising, so one absent block cannot mask a legitimate match elsewhere."""
    block, _, field = key.partition(".")
    entry = pins.get(block)
    if not isinstance(entry, dict):
        return None
    value = entry.get(field or "sha256")
    return value if isinstance(value, str) else None


def installed_bundle_key(pins: dict, digest: str, keys) -> str:
    """The single key in `keys` whose pinned digest equals `digest`.

    Pure, so the invariant is unit-testable with no map on disk. Raises
    `BundlePinError` naming the digest on zero matches and naming every
    colliding key on more than one -- both are registration faults, and
    neither is repaired here.
    """
    keys = tuple(keys)
    matches = [k for k in keys if pin_digest(pins, k) == digest]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise BundlePinError(
            f"installed bundle sha256 {digest} matches none of this bundle's "
            f"registered pins ({', '.join(keys)}). The bundle was changed "
            f"without re-pinning: record its provenance, or reinstall a "
            f"pinned bundle."
        )
    raise BundlePinError(
        f"installed bundle sha256 {digest} matches MORE THAN ONE pin "
        f"({', '.join(matches)}); a duplicated registration makes the run's "
        f"bundle ambiguous. Remove the duplicate."
    )


def bundle_key_for_dir(pins: dict, bundle_dir: str, digest: str) -> str:
    """As `installed_bundle_key`, but scoped to the candidates registered for
    `bundle_dir`. Raises `BundleNotRegistered` when that directory has none."""
    keys = BUNDLE_REGISTRY.get(bundle_dir)
    if not keys:
        raise BundleNotRegistered(
            f"no pin block is registered for bundle directory '{bundle_dir}' "
            f"(registered: {', '.join(sorted(BUNDLE_REGISTRY))}). This "
            f"bundle's provenance is not recorded, so a run cannot be "
            f"attributed to it -- add it to pins.yaml and BUNDLE_REGISTRY."
        )
    return installed_bundle_key(pins, digest, keys)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pcd", help="path to the installed pointcloud_map.pcd")
    p.add_argument(
        "--bundle-dir",
        default=None,
        help="bundle directory basename to scope the check to "
        "(default: the parent directory's name)",
    )
    p.add_argument("--pins", default=str(PINS), help="pins.yaml path")
    args = p.parse_args(argv)

    path = pathlib.Path(args.pcd)
    if not path.is_file():
        print(f"BUNDLE PIN FAIL: {path} is not a file", file=sys.stderr)
        return EXIT_FAIL
    bundle_dir = args.bundle_dir or path.parent.name
    pins = yaml.safe_load(open(args.pins))
    try:
        key = bundle_key_for_dir(pins, bundle_dir, sha256_file(path))
    except BundleNotRegistered as exc:
        # Exit code distinct from the fault path so preflight can SKIP it.
        print(f"BUNDLE PIN SKIP: {exc}", file=sys.stderr)
        return EXIT_UNREGISTERED
    except BundlePinError as exc:
        print(f"BUNDLE PIN FAIL: {exc}", file=sys.stderr)
        return EXIT_FAIL
    print(key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
