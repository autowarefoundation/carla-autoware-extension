#!/usr/bin/env bash
# Fetch Town10 map assets at the pinned autoware-contents revision.
# Usage: fetch_maps.sh [--record]  (--record: write sha256s into pins.yaml)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PINS="$SCRIPT_DIR/../pins.yaml"
REV=$(python3 -c "import yaml; print(yaml.safe_load(open('$PINS'))['autoware_contents']['revision'])")
DEST="$HOME/autoware_map/town10"
BASE="https://bitbucket.org/carla-simulator/autoware-contents/raw/$REV/maps"

# Download to .part siblings and only rename into place once the checksums are
# settled. Verifying AFTER writing the final names meant a changed upstream
# artifact installed and only then failed, leaving a bundle that is half old
# and half new -- which localizes silently against the wrong pointcloud. The
# .part files live in $DEST so the rename is same-filesystem.
mkdir -p "$DEST"
curl -fL "$BASE/point_cloud_maps/Town10HD.pcd" -o "$DEST/pointcloud_map.pcd.part"
curl -fL "$BASE/vector_maps/lanelet2/Town10HD.osm" -o "$DEST/lanelet2_map.osm.part"

PCD=$(sha256sum "$DEST/pointcloud_map.pcd.part" | cut -d' ' -f1)
OSM=$(sha256sum "$DEST/lanelet2_map.osm.part" | cut -d' ' -f1)

RECORD="${1:-}"
if [[ "$RECORD" == "--record" ]]; then
  python3 - "$PINS" "$PCD" "$OSM" <<'EOF'
import sys, yaml
pins_path, pcd, osm = sys.argv[1:4]
pins = yaml.safe_load(open(pins_path))
pins["autoware_contents"]["town10_pcd_sha256"] = pcd
pins["autoware_contents"]["town10_osm_sha256"] = osm
yaml.safe_dump(pins, open(pins_path, "w"), sort_keys=False)
EOF
else
  python3 - "$PINS" "$PCD" "$OSM" <<'EOF'
import sys, yaml
pins_path, pcd, osm = sys.argv[1:4]
p = yaml.safe_load(open(pins_path))["autoware_contents"]
assert p["town10_pcd_sha256"] == pcd, "pcd sha mismatch"
assert p["town10_osm_sha256"] == osm, "osm sha mismatch"
print("checksums ok")
EOF
fi

# Only reached when the checksums recorded or matched (set -e + the asserts
# above), so the bundle is replaced atomically per file, never half-written.
mv "$DEST/pointcloud_map.pcd.part" "$DEST/pointcloud_map.pcd"
mv "$DEST/lanelet2_map.osm.part" "$DEST/lanelet2_map.osm"
printf 'projector_type: Local\n' >"$DEST/map_projector_info.yaml"
