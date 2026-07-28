#!/usr/bin/env bash
# Fetch CARLA 0.9.15 and the gezp CARLA Python client wheel (bridge approach).
# Usage: fetch_bridge_deps.sh [--record]  (--record: write sha256s into pins.yaml)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PINS="$SCRIPT_DIR/../pins.yaml"
VENDOR_DIR="$SCRIPT_DIR/../docker/vendor"
CARLA_URL=$(python3 -c "import yaml; print(yaml.safe_load(open('$PINS'))['carla_0915']['url'])")
WHEEL_URL=$(python3 -c "import yaml; print(yaml.safe_load(open('$PINS'))['gezp_wheel']['url'])")
TARBALL="$HOME/carla-0915.tar.gz"
EXTRACT_DIR="$HOME/carla-0915"
WHEEL_FILE="$VENDOR_DIR/$(basename "$WHEEL_URL")"

# Nothing is INSTALLED before its checksum is settled. Extracting first (and
# writing the wheel under its final name) meant a changed upstream artifact
# landed in $EXTRACT_DIR / $VENDOR_DIR and only then failed, leaving a
# poisoned tree behind. The tarball keeps its stable path so --continue-at can
# still resume a multi-GB download; it is a staging file, not the install.
# The wheel's .part sibling is in $VENDOR_DIR, so its rename is same-filesystem
# and resumable too.
mkdir -p "$VENDOR_DIR"
curl -fL --continue-at - "$CARLA_URL" -o "$TARBALL"
curl -fL --continue-at - "$WHEEL_URL" -o "$WHEEL_FILE.part"

CARLA_SHA=$(sha256sum "$TARBALL" | cut -d' ' -f1)
WHEEL_SHA=$(sha256sum "$WHEEL_FILE.part" | cut -d' ' -f1)

RECORD="${1:-}"
if [[ "$RECORD" == "--record" ]]; then
  python3 - "$PINS" "$CARLA_SHA" "$WHEEL_SHA" <<'EOF'
import sys, yaml
pins_path, carla_sha, wheel_sha = sys.argv[1:4]
pins = yaml.safe_load(open(pins_path))
pins["carla_0915"]["sha256"] = carla_sha
pins["gezp_wheel"]["sha256"] = wheel_sha
yaml.safe_dump(pins, open(pins_path, "w"), sort_keys=False)
EOF
else
  python3 - "$PINS" "$CARLA_SHA" "$WHEEL_SHA" <<'EOF'
import sys, yaml
pins_path, carla_sha, wheel_sha = sys.argv[1:4]
p = yaml.safe_load(open(pins_path))
assert p["carla_0915"]["sha256"] == carla_sha, "carla tarball sha mismatch"
assert p["gezp_wheel"]["sha256"] == wheel_sha, "gezp wheel sha mismatch"
print("checksums ok")
EOF
fi

# Only reached when the checksums recorded or matched (set -e + the asserts
# above), so the extraction runs on a VERIFIED tarball and the wheel appears
# under its final name only once it is the pinned one.
mkdir -p "$EXTRACT_DIR"
tar -xzf "$TARBALL" -C "$EXTRACT_DIR"
mv "$WHEEL_FILE.part" "$WHEEL_FILE"
