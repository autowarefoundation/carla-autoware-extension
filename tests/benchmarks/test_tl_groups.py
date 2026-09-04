"""Unit tests for gen_tl_groups.py: the CLI that derives a map's committed
traffic-light-group YAML (Task 7 -- what makes dummy_perception.py's
--tl-groups path identical in every campaign cell), plus regression pins on
the two YAMLs actually committed under benchmarks/config/tl_groups/.

The committed-file assertions read the checked-in YAMLs directly rather than
re-parsing ~/autoware_map/*/lanelet2_map.osm, so this suite stays hermetic
(no host map-bundle dependency) while still pinning REAL derived values: the
groups lists below are exactly what
``python3 benchmarks/injector/gen_tl_groups.py --lanelet2
~/autoware_map/<map>/lanelet2_map.osm --out
benchmarks/config/tl_groups/<Map>.yaml`` produced from the real bundles
(Town10HD_Opt: 168 lanelets, 0 traffic-light regulatory elements;
NishishinjukuMap: 164, matching docs/e2e-report.md's live-measured count).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from benchmarks.injector.gen_tl_groups import build_arg_parser, main, tl_group_ids

CONFIG_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "config" / "tl_groups"


def _load_committed(map_name: str) -> dict:
    with open(CONFIG_DIR / f"{map_name}.yaml") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Committed YAMLs: regression pins on the real generated values.
# ---------------------------------------------------------------------------


def test_town10_committed_groups_is_empty():
    """Town10's lanelet2 export carries no regulatory elements at all (168
    lanelets, all subtype=road -- docs/running-e2e.md); the committed file
    must say so explicitly rather than being silently absent."""
    doc = _load_committed("Town10HD_Opt")
    assert doc["map"] == "Town10HD_Opt"
    assert doc["groups"] == []


def test_nishishinjuku_committed_groups_has_164_entries():
    """docs/e2e-report.md records the live G2 run forcing "all 164 map
    traffic-light groups as GREEN"; the committed file must reproduce that
    exact count from the same map bundle."""
    doc = _load_committed("NishishinjukuMap")
    assert doc["map"] == "NishishinjukuMap"
    assert len(doc["groups"]) == 164


def test_nishishinjuku_committed_groups_are_sorted_unique_ints():
    doc = _load_committed("NishishinjukuMap")
    groups = doc["groups"]
    assert all(isinstance(g, int) for g in groups)
    assert groups == sorted(groups)
    assert len(set(groups)) == len(groups)


# ---------------------------------------------------------------------------
# tl_group_ids: a synthetic-osm unit case (distinct from
# tests/e2e/test_dummy_perception.py's coverage of the same function via its
# benchmarks.injector.dummy_perception re-export).
# ---------------------------------------------------------------------------


def _osm(tmp_path, lanelet_ids, traffic_light_ids):
    parts = ["<?xml version='1.0' encoding='UTF-8'?>", "<osm version='0.6'>"]
    for rel_id in lanelet_ids:
        parts.append(f"<relation id='{rel_id}'><tag k='type' v='lanelet'/></relation>")
    for rel_id in traffic_light_ids:
        parts.append(
            f"<relation id='{rel_id}'>"
            f"<tag k='type' v='regulatory_element'/>"
            f"<tag k='subtype' v='traffic_light'/></relation>"
        )
    parts.append("</osm>")
    path = tmp_path / "lanelet2_map.osm"
    path.write_text("\n".join(parts))
    return str(path)


def test_tl_group_ids_synthetic_osm_dedups_nothing_and_sorts(tmp_path):
    path = _osm(tmp_path, lanelet_ids=[10, 11, 12, 13], traffic_light_ids=[55, 5, 900, 5001])
    assert tl_group_ids(path) == [5, 55, 900, 5001]


# ---------------------------------------------------------------------------
# CLI: --lanelet2/--out surface and the filename-stem-as-map-name convention.
# ---------------------------------------------------------------------------


def test_cli_writes_map_name_from_out_filename_stem_and_groups(tmp_path):
    osm = _osm(tmp_path, lanelet_ids=[1, 2], traffic_light_ids=[3020, 21, 700])
    out = tmp_path / "SomeOtherMap.yaml"
    rc = main(["--lanelet2", osm, "--out", str(out)])
    assert rc == 0
    doc = yaml.safe_load(out.read_text())
    assert doc == {"map": "SomeOtherMap", "groups": [21, 700, 3020]}


def test_cli_writes_empty_groups_for_a_signal_free_map(tmp_path):
    osm = _osm(tmp_path, lanelet_ids=[1, 2, 3], traffic_light_ids=[])
    out = tmp_path / "SignalFreeMap.yaml"
    rc = main(["--lanelet2", osm, "--out", str(out)])
    assert rc == 0
    doc = yaml.safe_load(out.read_text())
    assert doc == {"map": "SignalFreeMap", "groups": []}


def test_cli_requires_lanelet2_and_out():
    with pytest.raises(SystemExit) as exc_info:
        build_arg_parser().parse_args([])
    assert exc_info.value.code == 2
