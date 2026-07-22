#!/usr/bin/env bash
# Regenerate the REP-2011 RIHS01 type hash for one Autoware / geometry_msgs
# message from the committed `.msg` closure under extension/msg/**, so the
# goldens in extension/src/messages/AwGoldens.inc and
# extension/src/publishers/GeoGoldens.inc can be reproduced and audited.
#
# WHY NOT THE PINNED HUMBLE CONTAINER (docs/environment.md):
#   RIHS01 / the REP-2011 type-description tooling (rosidl_generator_type_description)
#   landed in ROS 2 Iron; it does NOT exist in Humble, so the Autoware
#   `universe-devel` (humble) image physically cannot compute these hashes -- it
#   has no `.json` type descriptions and `ros2 interface` has no hash subcommand.
#   The pinned Humble image is the SOURCE of the `.msg` inputs (extracted once
#   into extension/msg/**); it is not where the hash is computed. A RIHS01 hash
#   is a pure function of the recursive message definition (REP-2011), i.e. it is
#   DISTRO-INVARIANT, so building the same committed `.msg` closure under any
#   Iron+ rosidl toolchain yields the exact hash Humble puts on the wire. This is
#   the method the goldens were originally computed with and is corroborated in
#   docs/g0-report.md (canonical hashes cross-checked against Jazzy's own
#   distro-shipped REP-2011 JSON). We pin osrf/ros:jazzy-desktop as that
#   toolchain here -- the same image the original computation used.
#
# METHOD (do not "improve" it -- byte-for-byte reproducibility is the point):
#   1. Copy the target `.msg` and EVERY sibling `.msg` in its package dir into a
#      throwaway colcon interface package. Siblings are required because Autoware
#      messages reference same-package types by bare name (e.g. Control -> bare
#      `Lateral`/`Longitudinal`; PoseStamped -> bare `Pose`), and rosidl only
#      resolves those if the sibling files are present in the same package.
#   2. Auto-detect external package deps (e.g. std_msgs, builtin_interfaces) from
#      "pkg/Type field" declarations and wire them into package.xml/CMakeLists.
#   3. `colcon build` inside osrf/ros:jazzy-desktop; rosidl emits a REP-2011
#      type-description JSON alongside each message.
#   4. Read hash_string for the fully-qualified type out of that JSON.
#
# USAGE:
#   extension/scripts/compute_type_hash.sh <pkg>/msg/<TypeName> [msg_dir]
#
#   <pkg>/msg/<TypeName>  Full ROS 2 type name, e.g. autoware_vehicle_msgs/msg/VelocityReport
#   [msg_dir]             Directory holding <TypeName>.msg + its siblings.
#                         Defaults to <repo>/extension/msg/<pkg>.
#
# OUTPUT (stdout): a single `RIHS01_<64 hex>` line -- must match the committed
#   `#define AW_GOLDEN_<TypeName>` in the corresponding `.inc`.
#
# EXAMPLES:
#   extension/scripts/compute_type_hash.sh autoware_vehicle_msgs/msg/VelocityReport
#   extension/scripts/compute_type_hash.sh geometry_msgs/msg/PoseStamped
#
# Requires Docker on the host (this launches its own jazzy container; it does NOT
# run inside the Autoware container). No local ROS 2 install is needed.
set -euo pipefail

readonly JAZZY_IMAGE="osrf/ros:jazzy-desktop"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
readonly SCRIPT_DIR REPO_ROOT

usage() {
  cat >&2 <<'EOF'
Usage: compute_type_hash.sh <pkg>/msg/<TypeName> [msg_dir]
  e.g. compute_type_hash.sh autoware_vehicle_msgs/msg/VelocityReport
       compute_type_hash.sh geometry_msgs/msg/PoseStamped
Prints the RIHS01 hash to stdout (compare against AwGoldens.inc / GeoGoldens.inc).
EOF
  exit "${1:-0}"
}

[[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]] && usage 0
[[ $# -lt 1 || $# -gt 2 ]] && usage 1

readonly ROS_TYPE="$1"

# --- Preflight (named, fail-loud) --------------------------------------------
if ! [[ "$ROS_TYPE" =~ ^[a-zA-Z_][a-zA-Z0-9_]*/msg/[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
  echo "PREFLIGHT FAIL: type must be '<pkg>/msg/<TypeName>', got: ${ROS_TYPE}" >&2
  exit 1
fi
readonly PKG_NAME="${ROS_TYPE%%/msg/*}"
readonly TYPE_NAME="${ROS_TYPE##*/}"
readonly MSG_DIR="${2:-${REPO_ROOT}/extension/msg/${PKG_NAME}}"

command -v docker >/dev/null 2>&1 \
  || { echo "PREFLIGHT FAIL: docker not on PATH" >&2; exit 1; }
docker info >/dev/null 2>&1 \
  || { echo "PREFLIGHT FAIL: docker daemon not reachable" >&2; exit 1; }
[[ -d "$MSG_DIR" ]] \
  || { echo "PREFLIGHT FAIL: msg dir not found: ${MSG_DIR}" >&2; exit 1; }
[[ -f "${MSG_DIR}/${TYPE_NAME}.msg" ]] \
  || { echo "PREFLIGHT FAIL: ${TYPE_NAME}.msg not found in ${MSG_DIR}" >&2; exit 1; }

# The jazzy toolchain image is large (~2.6 GB). Pull it explicitly & loudly on a
# fresh machine rather than letting `docker run` pull silently mid-build.
if ! docker image inspect "$JAZZY_IMAGE" >/dev/null 2>&1; then
  echo "NOTE: ${JAZZY_IMAGE} not present locally; pulling it (one-time, ~2.6 GB) ..." >&2
  docker pull "$JAZZY_IMAGE" \
    || { echo "PREFLIGHT FAIL: could not pull ${JAZZY_IMAGE}" >&2; exit 1; }
fi

# --- Assemble a throwaway interface package ----------------------------------
WS="$(mktemp -d)"
trap 'rm -rf "$WS"' EXIT
PKG_DIR="${WS}/src/${PKG_NAME}"
mkdir -p "${PKG_DIR}/msg"
cp "${MSG_DIR}"/*.msg "${PKG_DIR}/msg/"          # every sibling (bare-name refs)

python3 - "$PKG_NAME" "$PKG_DIR" <<'PYEOF'
import glob, os, re, sys

pkg_name, pkg_dir = sys.argv[1:]
msg_files = sorted(glob.glob(os.path.join(pkg_dir, "msg", "*.msg")))

# External deps = "otherpkg/Type field" lines (not same-package bare refs).
deps = set()
for path in msg_files:
    for line in open(path):
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^([a-zA-Z_]\w*)/[a-zA-Z_]\w*(\[.*?\])?\s+\w", line)
        if m and m.group(1) != pkg_name:
            deps.add(m.group(1))
deps = sorted(deps)

with open(os.path.join(pkg_dir, "package.xml"), "w") as f:
    f.write('<?xml version="1.0"?>\n<package format="3">\n')
    f.write(f"  <name>{pkg_name}</name>\n  <version>0.0.1</version>\n")
    f.write("  <description>Throwaway package for RIHS01 hash computation</description>\n")
    f.write("  <maintainer email=\"tmp@tmp.invalid\">tmp</maintainer>\n  <license>Apache-2.0</license>\n")
    f.write("  <buildtool_depend>ament_cmake</buildtool_depend>\n")
    f.write("  <depend>rosidl_default_generators</depend>\n")
    for d in deps:
        f.write(f"  <depend>{d}</depend>\n")
    f.write("  <member_of_group>rosidl_interface_packages</member_of_group>\n</package>\n")

msg_entries = "\n".join(f'  "msg/{os.path.basename(p)}"' for p in msg_files)
find_pkgs = "\n".join(f"find_package({d} REQUIRED)" for d in deps)
rosidl_deps = ("  DEPENDENCIES " + " ".join(deps)) if deps else ""
with open(os.path.join(pkg_dir, "CMakeLists.txt"), "w") as f:
    f.write(f"cmake_minimum_required(VERSION 3.8)\nproject({pkg_name})\n")
    f.write("find_package(ament_cmake REQUIRED)\n")
    f.write("find_package(rosidl_default_generators REQUIRED)\n")
    f.write(find_pkgs + ("\n" if find_pkgs else ""))
    f.write("rosidl_generate_interfaces(${PROJECT_NAME}\n")
    f.write(msg_entries + "\n")
    f.write(rosidl_deps + ("\n" if rosidl_deps else ""))
    f.write(")\nament_package()\n")
PYEOF

# --- Build inside jazzy and read the REP-2011 hash out of the JSON -----------
echo "[hash] building ${ROS_TYPE} in ${JAZZY_IMAGE} ..." >&2
docker run --rm \
  --volume="${WS}:/ws" \
  --user="$(id -u):$(id -g)" \
  --env=HOME=/tmp \
  "$JAZZY_IMAGE" \
  bash -c "
    set -eo pipefail
    # setup.bash reads vars unset on a fresh container; only enable nounset after.
    source /opt/ros/jazzy/setup.bash
    set -u
    cd /ws
    colcon --log-base /tmp/colcon-log build --packages-select ${PKG_NAME} \
      --cmake-args -DCMAKE_BUILD_TYPE=Release >/tmp/colcon-out.txt 2>&1 \
      || { echo 'ERROR: colcon build failed:' >&2; cat /tmp/colcon-out.txt >&2; exit 1; }
    JSON=/ws/install/${PKG_NAME}/share/${PKG_NAME}/msg/${TYPE_NAME}.json
    [[ -f \"\$JSON\" ]] || { echo \"ERROR: type-description JSON not found: \$JSON\" >&2; exit 1; }
    python3 -c '
import json, sys
data = json.load(open(sys.argv[1]))
for entry in data[\"type_hashes\"]:
    if entry[\"type_name\"] == sys.argv[2]:
        print(entry[\"hash_string\"]); sys.exit(0)
sys.exit(1)
' \"\$JSON\" '${ROS_TYPE}' \
      || { echo \"ERROR: ${ROS_TYPE} not present in \$JSON\" >&2; exit 1; }
  "
