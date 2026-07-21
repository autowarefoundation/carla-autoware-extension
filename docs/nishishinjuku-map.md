# Nishi-Shinjuku map assets (Phase B)

E2E gates G1-G3 run on the AWSIM v2.0.0 Nishi-Shinjuku map.

## Autoware side (`~/autoware_map/nishishinjuku`, not committed)

- Source: AWSIM v2.0.0 `Shinjuku-Map.zip`, 129,585,415 bytes,
  <https://github.com/autowarefoundation/AWSIM/releases/download/v2.0.0/Shinjuku-Map.zip>
- Files: lanelet2_map.osm, pointcloud_map.pcd, pointcloud_map_metadata.yaml, map_projector_info.yaml
- Projector: MGRS, grid 54SUE, vertical_datum WGS84 (triangulated across converter conf,
  fixture lanelet2 mgrs_code, DA_MGRS_Shinjuku UE asset, AWSIM docs).
- License: CC BY-NC 4.0 (LICENSE shipped in the zip; data referenced in place, never committed).

## CARLA side (`Content/`, per-worktree, git-ignored, not committed)

- Prebuilt AWSIM->UE5 content pack + converter OpenDRIVE (`NishishinjukuMap.xodr`, ~6.06 MB).
- MGRS 54SUE; converter offset x=81655.73 y=50137.43 z=42.49998
  (autoware_lanelet2_to_opendrive conf/map/nishishinjuku.yaml).

## Non-goal (future work)

Town10 + lanelet2 auto-generation (CARLA .xodr -> lanelet2) is out of Phase B scope. No
CARLA(.xodr)->lanelet2 reverse converter exists: `autoware_lanelet2_to_opendrive` only
converts Lanelet2 -> OpenDRIVE, not the other direction. The reusable scaffolding for a
future reverse converter is that same package's tag-mapping tables, MGRS projection
utilities, and the `analyze` QC harness.
