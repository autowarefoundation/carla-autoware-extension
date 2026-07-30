"""The pins.yaml one-block invariant, given a consumer and a test.

benchmarks/pins.yaml registers that the file installed at a map's mounted
bundle path hashes to the `sha256` of EXACTLY ONE pin block. Task 11 registered
that in prose with nothing checking it; these tests plus
benchmarks/scripts/preflight.sh are the consumers that make it enforceable.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from benchmarks.scripts.bundle_pin import (
    BUNDLE_PIN_KEYS,
    BundlePinError,
    installed_bundle_key,
)

PINS = yaml.safe_load(
    (pathlib.Path(__file__).resolve().parents[2] / "benchmarks" / "pins.yaml").read_text()
)


def test_every_registered_bundle_key_exists_and_carries_a_sha256():
    """BUNDLE_PIN_KEYS is the candidate set the invariant is checked against,
    so a key that does not exist (renamed block) or carries no `sha256` would
    silently shrink that set and let an unpinned bundle look legitimate."""
    for key in BUNDLE_PIN_KEYS:
        assert key in PINS, key
        assert isinstance(PINS[key].get("sha256"), str), key
        assert len(PINS[key]["sha256"]) == 64, key


def test_the_committed_bundle_pins_are_mutually_distinct():
    """The invariant is only satisfiable if no two blocks pin identical bytes:
    two blocks with one digest would make every installed bundle ambiguous."""
    digests = [PINS[k]["sha256"] for k in BUNDLE_PIN_KEYS]
    assert len(set(digests)) == len(digests), digests


@pytest.mark.parametrize("key", BUNDLE_PIN_KEYS)
def test_each_pinned_digest_resolves_to_its_own_key(key):
    assert installed_bundle_key(PINS, PINS[key]["sha256"]) == key


def test_an_unpinned_bundle_is_refused_by_name():
    """An unrecorded local edit must not be measurable. The message has to
    name the digest, because that is the only handle an operator has on a file
    whose provenance is precisely what is missing."""
    with pytest.raises(BundlePinError, match="matches no pin block"):
        installed_bundle_key(PINS, "0" * 64)


def test_a_duplicated_registration_is_refused_rather_than_repaired():
    """Two blocks pinning one digest is a registration fault. It is reported,
    naming both keys, instead of resolved by picking one -- picking would
    attribute the run to a bundle nobody chose."""
    pins = {
        "town10_pcd_shifted": {"sha256": "a" * 64},
        "town10_pcd_refit": {"sha256": "a" * 64},
    }
    with pytest.raises(BundlePinError, match="MORE THAN ONE"):
        installed_bundle_key(pins, "a" * 64, keys=("town10_pcd_shifted", "town10_pcd_refit"))


def test_the_regen_bundle_is_the_one_the_town10_cells_are_registered_against():
    """Task 11 pointed map_defaults.sh's Town10HD_Opt at town10-regen and
    registered cells A/A-hf on the absolute branch off THAT bundle's 0.089 m
    measurement. If the default bundle moves, the branch registration in
    cells.yaml has to be revisited rather than silently inherited."""
    defaults = (
        pathlib.Path(__file__).resolve().parents[2] / "scripts" / "e2e" / "map_defaults.sh"
    ).read_text()
    assert "MAP_DEFAULT_DIR=/autoware_map/town10-regen" in defaults
