#!/usr/bin/env bash
# Assert the editor plugin .so the simulator loads is newer than the CARLA
# HEAD commit. `carla-unreal` (no -editor) leaves this .so stale (Phase A 4.1);
# a stale .so runs pre-port UE code and silently drops newly added publishers.
set -euo pipefail
CARLA_ROOT=${CARLA_ROOT:?set CARLA_ROOT to ~/src/carla-autoware-integration}
SO="$CARLA_ROOT/Unreal/CarlaUnreal/Plugins/Carla/Binaries/Linux/libUnrealEditor-Carla.so"
[ -f "$SO" ] || { echo "PREFLIGHT FAIL: $SO missing (build carla-unreal-editor)"; exit 1; }
SO_MTIME=$(stat -c %Y "$SO")
COMMIT_EPOCH=$(cd "$CARLA_ROOT" && git show -s --format=%ct HEAD)
if [ "$SO_MTIME" -lt "$COMMIT_EPOCH" ]; then
  echo "PREFLIGHT FAIL: $SO ($SO_MTIME) is OLDER than HEAD commit ($COMMIT_EPOCH)."
  echo "  -> rebuild target carla-unreal-editor before any live run."
  exit 1
fi
echo "OK: editor plugin .so is newer than HEAD ($SO_MTIME >= $COMMIT_EPOCH)"
