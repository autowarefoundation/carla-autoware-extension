#!/usr/bin/env bash
# Run wire_mgrs_asset.py inside the UE editor commandlet.
# Usage: run_wire_mgrs_asset.sh inspect|apply <log-file>
# Needs: UE_ROOT, CARLA_UE58 (path of the CARLA worktree with a built editor).
set -euo pipefail
MODE="${1:?inspect|apply}"; LOG="${2:?log file}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${UE_ROOT:?}" "${CARLA_UE58:?}"
MODE="$MODE" TARGET_MAP="${TARGET_MAP:-/Game/Carla/Maps/NishishinjukuMap}" \
MGRS_ASSET="${MGRS_ASSET:-/Game/Autoware/Data/DA_MGRS_Shinjuku}" \
"$UE_ROOT/Engine/Binaries/Linux/UnrealEditor" "$CARLA_UE58/Unreal/CarlaUnreal/CarlaUnreal.uproject" \
  -run=pythonscript -script="$HERE/wire_mgrs_asset.py" \
  -FullStdOutLogOutput -unattended -nosplash -nosound -stdout > "$LOG" 2>&1 || true
grep '\[wire_mgrs_asset\]' "$LOG" || { echo "no script output in $LOG (editor aborted before Python?)" >&2; exit 1; }
grep -q '\[wire_mgrs_asset\] RESULT: \(INSPECT done\|APPLY saved=True\)' "$LOG"
