"""The pins.yaml one-block invariant, given consumers and tests.

benchmarks/pins.yaml registers that the file installed at a map's mounted
bundle path hashes to the digest of EXACTLY ONE pin block. Task 11 registered
that in prose with nothing checking it; benchmarks/scripts/bundle_pin.py and
benchmarks/scripts/preflight.sh are the consumers that make it enforceable, and
these are the tests that keep it from becoming a blocker instead of a check.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from benchmarks.scripts.bundle_pin import (
    APPROACH_BUNDLE_DIR,
    BUNDLE_REGISTRY,
    BundleNotRegistered,
    BundlePinError,
    bundle_key_for_dir,
    installed_bundle_key,
    pin_digest,
)
from benchmarks.scripts.cell_info import load_cells_doc

REPO = pathlib.Path(__file__).resolve().parents[2]
PINS = yaml.safe_load((REPO / "benchmarks" / "pins.yaml").read_text())

ALL_KEYS = tuple(k for keys in BUNDLE_REGISTRY.values() for k in keys)


def test_every_registered_key_resolves_to_a_64_hex_digest():
    """A key that does not resolve (renamed block, moved field) would silently
    shrink the candidate set and let an unpinned bundle look legitimate."""
    for key in ALL_KEYS:
        digest = pin_digest(PINS, key)
        assert digest is not None, key
        assert re.fullmatch(r"[0-9a-f]{64}", digest), (key, digest)


def test_all_registered_bundle_digests_are_mutually_distinct():
    """The invariant is only satisfiable if no two pins carry identical bytes:
    two keys with one digest would make an installed bundle ambiguous."""
    digests = [pin_digest(PINS, k) for k in ALL_KEYS]
    assert len(set(digests)) == len(digests), digests


@pytest.mark.parametrize("bundle_dir,keys", sorted(BUNDLE_REGISTRY.items()))
def test_each_registered_digest_resolves_within_its_own_bundle_dir(bundle_dir, keys):
    for key in keys:
        assert bundle_key_for_dir(PINS, bundle_dir, pin_digest(PINS, key)) == key


def test_a_changed_bundle_is_refused_by_name():
    """Bytes matching none of a REGISTERED bundle's pins is the fault this
    check exists for -- the bundle was edited without re-pinning. The message
    names the digest, the only handle an operator has on a file whose
    provenance is exactly what is missing."""
    with pytest.raises(BundlePinError, match="matches none of this bundle's"):
        bundle_key_for_dir(PINS, "town10-regen", "0" * 64)


def test_a_duplicated_registration_is_refused_rather_than_repaired():
    """Two keys pinning one digest is a registration fault. Reported, naming
    both, instead of resolved by picking one -- picking would attribute the run
    to a bundle nobody chose."""
    pins = {"a": {"sha256": "a" * 64}, "b": {"sha256": "a" * 64}}
    with pytest.raises(BundlePinError, match="MORE THAN ONE"):
        installed_bundle_key(pins, "a" * 64, ("a", "b"))


def test_an_unregistered_bundle_dir_is_a_separate_outcome_from_a_fault():
    """THE REGRESSION TEST for the defect this scoping fixed. An earlier
    revision checked one flat candidate list against every cell, so cells C/D's
    `nishishinjuku` bundle matched zero blocks and preflight FAILED -- which
    would have blocked Task 15 and the whole C/D half of the campaign.

    Absence of a registration is a gap in the record, not a corrupted bundle,
    so it must raise a DIFFERENT exception (which preflight turns into a skip)
    and must not be catchable as a provenance fault.
    """
    with pytest.raises(BundleNotRegistered):
        bundle_key_for_dir(PINS, "a-bundle-nobody-pinned", "0" * 64)
    # Explicitly NOT a subclass either way: preflight distinguishes them by
    # type, so a subclass relation would re-introduce the blocker.
    assert not issubclass(BundleNotRegistered, BundlePinError)
    assert not issubclass(BundlePinError, BundleNotRegistered)


def test_every_committed_cell_resolves_to_a_registered_or_skipped_bundle():
    """No cell in the matrix may land on the FAULT path merely by existing.
    Each cell's bundle either resolves (extension and tier4-native via
    map_defaults.sh, python-bridge via APPROACH_BUNDLE_DIR) or is deliberately
    unresolvable (calibration, having no localization stack).

    tier4-native moved from the second branch to the first in Task 13, when
    benchmarks/cells/tier4_autoware.sh started sourcing map_defaults.sh -- so
    the B family's bundle is now VERIFIED per map instead of skipped, and the
    A/B halves of the duel are held to the same bundle by construction.
    """
    defaults = (REPO / "scripts" / "e2e" / "map_defaults.sh").read_text()
    for cell in load_cells_doc()["cells"]:
        approach, map_name = cell["approach"], cell["map"]
        if map_name == "none":
            continue
        if approach in ("extension", "tier4-native"):
            # Both read map_defaults.sh, so every map either can be asked for
            # must have an entry there AND be registered here.
            found = re.search(
                rf"^\s+{re.escape(map_name)}\)(.*?)MAP_DEFAULT_DIR=(\S+)",
                defaults,
                re.S | re.M,
            )
            assert found, f"{cell['id']}: {map_name} has no map_defaults.sh entry"
            bundle_dir = found.group(2).rsplit("/", 1)[-1]
            assert bundle_dir in BUNDLE_REGISTRY, (cell["id"], bundle_dir)
        else:
            # Anything else must be EXPLICITLY mapped -- possibly to None,
            # which is a skip, but never left to fall through by accident.
            assert approach in APPROACH_BUNDLE_DIR, (cell["id"], approach)
            bundle_dir = APPROACH_BUNDLE_DIR[approach]
            if bundle_dir is not None:
                assert bundle_dir in BUNDLE_REGISTRY, (cell["id"], bundle_dir)


def test_the_bridge_bundle_mapping_matches_what_its_launcher_mounts():
    """APPROACH_BUNDLE_DIR duplicates a literal that lives in
    cells/python-bridge.sh, so it can drift. It exists because resolving the E
    family through map_defaults.sh attributed the EXTENSION cells' bundle to
    E -- a wrong provenance record in the manifest, which the B family would
    have inherited. This test keeps the duplicate honest: it reads the
    launcher's own MAP_BUNDLE_HOST and compares.
    """
    launcher = (REPO / "benchmarks" / "cells" / "python-bridge.sh").read_text()
    found = re.search(r'^MAP_BUNDLE_HOST="\$HOME/autoware_map/([^"]+)"', launcher, re.M)
    assert found, "cells/python-bridge.sh no longer defines MAP_BUNDLE_HOST"
    assert APPROACH_BUNDLE_DIR["python-bridge"] == found.group(1)


def test_the_tier4_launcher_resolves_its_bundle_through_map_defaults():
    """The counterpart check for the B family, and the reason `tier4-native` is
    absent from APPROACH_BUNDLE_DIR rather than mapped to a string.

    preflight.sh resolves this approach's bundle through map_defaults.sh, which
    is only correct while its launcher does the same. If tier4_autoware.sh ever
    pins a bundle of its own, the manifest's `map_bundle_pin` would report the
    extension cells' bundle as the B family's -- the exact wrong-provenance
    record that put the E family in APPROACH_BUNDLE_DIR in the first place.
    """
    launcher = (REPO / "benchmarks" / "cells" / "tier4_autoware.sh").read_text()
    assert "scripts/e2e/map_defaults.sh" in launcher
    assert "carla_autoware_map_defaults" in launcher
    assert 'MAP_DIR="${MAP_DIR:-$MAP_DEFAULT_DIR}"' in launcher
    assert "tier4-native" not in APPROACH_BUNDLE_DIR
    preflight = (REPO / "benchmarks" / "scripts" / "preflight.sh").read_text()
    assert 'elif [ "$APPROACH" = "extension" ] || [ "$APPROACH" = "tier4-native" ]' in preflight


def test_the_regen_bundle_is_the_one_the_town10_cells_are_registered_against():
    """Task 11 pointed map_defaults.sh's Town10HD_Opt at town10-regen and
    registered cells A/A-hf on the absolute branch off THAT bundle's 0.089 m
    measurement. If the default bundle moves, the branch registration in
    cells.yaml must be revisited rather than silently inherited."""
    defaults = (REPO / "scripts" / "e2e" / "map_defaults.sh").read_text()
    assert "MAP_DEFAULT_DIR=/autoware_map/town10-regen" in defaults


def test_every_evidence_directory_is_indexed_and_has_provenance():
    """benchmarks/evidence/ is where the record's recomputable claims point, so
    an unindexed directory is evidence nobody can find and an undocumented one
    is bytes without provenance. Both defeat the purpose, and both are the kind
    of drift that happens quietly as directories are added.

    Each directory must be named in the index table of evidence/README.md and
    carry either its own PROVENANCE.md or a gate-written *_summary.txt.
    """
    root = REPO / "benchmarks" / "evidence"
    index = (root / "README.md").read_text()
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        assert f"`{d.name}/`" in index, f"{d.name} is not in evidence/README.md"
        documented = (d / "PROVENANCE.md").is_file() or any(d.rglob("*_summary.txt"))
        assert documented, f"{d.name} has neither PROVENANCE.md nor a *_summary.txt"


def test_preflight_skip_reasons_are_a_closed_documented_set():
    """The skip vocabulary is what makes a skipped bundle distinguishable from a
    check that never ran, so it must stay closed and documented. If a new reason
    is added to preflight.sh without documenting it, this fails.
    """
    pf = (REPO / "benchmarks" / "scripts" / "preflight.sh").read_text()
    emitted = set(re.findall(r"bundle_skip (\S+) ", pf))
    assert emitted == {
        "no-map",
        "unknown-map",
        "unmapped-approach",
        "no-host-copy",
        "unregistered-dir",
    }, emitted
    # Every reason must also appear in the comment block that documents them,
    # so the code and its own documentation cannot drift apart.
    for reason in emitted:
        assert re.search(rf"^#\s+{re.escape(reason)}\s", pf, re.M), reason
