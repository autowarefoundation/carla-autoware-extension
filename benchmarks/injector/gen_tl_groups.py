#!/usr/bin/env python3
"""Derive a map's traffic-light group ids from its lanelet2 .osm, as a
committed YAML (Task 7: the injector generalization).

``dummy_perception.py``'s live lanelet2 parse (``tl_group_ids`` below, moved
here verbatim from the pre-Task-7 script) is deterministic given a fixed map
bundle, but re-parsing a 10 MB+ .osm on every injector start is still one more
thing that could differ between cells if the mounted bundle ever drifts mid
campaign. Running this CLI once per map and committing the result
(``benchmarks/config/tl_groups/<Map>.yaml``) makes the injector's traffic-light
feed identical in every cell by construction: ``dummy_perception.py
--tl-groups <yaml>`` reads the committed list instead of touching the map
bundle at all.

CLI:

    python3 benchmarks/injector/gen_tl_groups.py \\
        --lanelet2 ~/autoware_map/town10/lanelet2_map.osm \\
        --out benchmarks/config/tl_groups/Town10HD_Opt.yaml

The map name embedded in the output YAML's ``map:`` key is taken from
``--out``'s filename stem (e.g. ``Town10HD_Opt.yaml`` -> ``map:
Town10HD_Opt``), matching ``benchmarks/scripts/pick_route.py``'s
filename-stem-as-map-name convention.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


def tl_group_ids(osm_path: str) -> list[int]:
    """Traffic-light regulatory-element ids from the lanelet2 .osm (= Autoware's
    traffic_light_group_id).

    An empty result is LEGAL only when the map genuinely carries no signals --
    some maps have none at all (CARLA's Town10 export: 168 lanelets, zero
    regulatory elements), and there is then nothing to force green. It is NOT
    legal when the file yielded no lanelets either: that means the wrong path or
    a broken parse, and it must stay loud, because on a signalised map an empty
    green feed silently leaves every signal UNKNOWN and reintroduces the exact
    phantom red light this feed exists to prevent.
    """
    root = ET.parse(osm_path).getroot()
    ids = []
    lanelets = 0
    for rel in root.iter("relation"):
        tags = {t.get("k"): t.get("v") for t in rel.findall("tag")}
        if tags.get("type") == "lanelet":
            lanelets += 1
        if tags.get("type") == "regulatory_element" and tags.get("subtype") == "traffic_light":
            ids.append(int(rel.get("id")))
    if not lanelets:
        raise RuntimeError(f"no lanelet relations found in {osm_path} -- wrong map file?")
    return sorted(ids)


def build_arg_parser() -> argparse.ArgumentParser:
    """Split out from main() so the CLI surface is unit-testable without
    touching the filesystem (tests/benchmarks/test_tl_groups.py)."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lanelet2", required=True, help="path to the map's lanelet2_map.osm")
    p.add_argument(
        "--out",
        required=True,
        help="output YAML path; its filename stem becomes the doc's map: value "
        "(e.g. Town10HD_Opt.yaml -> map: Town10HD_Opt)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    ids = tl_group_ids(args.lanelet2)
    map_name = Path(args.out).stem
    doc = {"map": map_name, "groups": ids}
    with open(args.out, "w") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=None)
    print(f"{map_name}: {len(ids)} traffic-light group(s) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
