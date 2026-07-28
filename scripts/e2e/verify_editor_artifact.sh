#!/usr/bin/env bash
# Assert the editor plugin .so the simulator loads is newer than the CARLA
# HEAD commit. `carla-unreal` (no -editor) leaves this .so stale (a known
# trap: carla-unreal builds the plugin but does not refresh the
# editor .so); a stale .so runs pre-port UE code and silently drops newly
# added publishers.
#
# Then assert the ENGINE BuildId the Carla modules were built against still
# matches the engine's current one. These are two independent staleness axes and
# the mtime check above does NOT cover the second: a UE rebuild that relinks any
# engine module stamps a fresh BuildId into the engine manifest, and UE then
# REFUSES to load every project/plugin module carrying the old one. The failure
# is a "modules are missing or built with a different engine version" message box
# (auto-answered "No" when headless) followed by "Exiting abnormally", ~2 minutes
# into a boot, with no map and no extension ever loaded -- which reads like
# anything but a stale build. Measured 2026-07-27: four engine modules including
# libUnrealEditor-Engine.so were relinked, and every live run aborted this way
# on every map until carla-unreal-editor was rebuilt.
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

# BuildId check. Skipped (not failed) when the engine path or either manifest is
# absent, so this script keeps working standalone and on a layout that does not
# have them; run_e2e.sh always exports CARLA_UNREAL_ENGINE_PATH, so the real
# live path is always covered.
ENGINE_MODULES="${CARLA_UNREAL_ENGINE_PATH:-}/Engine/Binaries/Linux/UnrealEditor.modules"
PROJECT_MODULES="$CARLA_ROOT/Unreal/CarlaUnreal/Binaries/Linux/UnrealEditor.modules"
if [ -z "${CARLA_UNREAL_ENGINE_PATH:-}" ] || [ ! -f "$ENGINE_MODULES" ] || [ ! -f "$PROJECT_MODULES" ]; then
  echo "SKIP: engine BuildId check (CARLA_UNREAL_ENGINE_PATH unset or manifests missing)"
  exit 0
fi
build_id() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("BuildId",""))' "$1"; }
ENGINE_ID="$(build_id "$ENGINE_MODULES")"
PROJECT_ID="$(build_id "$PROJECT_MODULES")"
if [ -n "$ENGINE_ID" ] && [ -n "$PROJECT_ID" ] && [ "$ENGINE_ID" != "$PROJECT_ID" ]; then
  echo "PREFLIGHT FAIL: engine BuildId $ENGINE_ID != Carla module BuildId $PROJECT_ID." >&2
  echo "  The engine was rebuilt after the Carla editor modules; UE will refuse to" >&2
  echo "  load them and abort the -game boot before loading any map." >&2
  echo "  -> rebuild target carla-unreal-editor before any live run." >&2
  exit 1
fi
echo "OK: engine and Carla module BuildId agree ($PROJECT_ID)"
