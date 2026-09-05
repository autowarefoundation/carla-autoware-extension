"""Inspect or set the MGRS data asset on NishishinjukuMap's world settings.

Runs INSIDE the UE editor's embedded Python (PythonScriptPlugin, -run=pythonscript).
Config comes from environment variables (UE's -run=pythonscript argument passing
is unreliable):

  MODE        inspect (default) | apply
  TARGET_MAP  /Game path of the level (default /Game/Carla/Maps/NishishinjukuMap)
  MGRS_ASSET  /Game path of the UMgrsDataAsset (default /Game/Autoware/Data/DA_MGRS_Shinjuku)

Why this exists: UWorld::RepairWorldSettings re-spawns a level's WorldSettings as
the project's class (/Script/Carla.AutowareWorldSettings) on load, with an EMPTY
MgrsDataAssetSoftPtr. Setting the pointer here and saving is the content-side
georeference CARLA's in-tree Autoware layer expects. Judge success by the
RESULT line in the log, not by the exit code (the commandlet can SIGSEGV a
worker thread at shutdown after the save has completed).
"""

import os

import unreal


def log(msg):
    unreal.log(f"[wire_mgrs_asset] {msg}")


def main():
    mode = os.environ.get("MODE", "inspect")
    target = os.environ.get("TARGET_MAP", "/Game/Carla/Maps/NishishinjukuMap")
    asset_path = os.environ.get("MGRS_ASSET", "/Game/Autoware/Data/DA_MGRS_Shinjuku")

    asset = unreal.load_asset(asset_path)
    if asset is None:
        log(f"RESULT: FAIL asset {asset_path} not found (is Content/Autoware present?)")
        return
    log(
        f"asset class={asset.get_class().get_name()} "
        f"offset={asset.get_editor_property('mgrs_offset_position')} "
        f"grid={asset.get_editor_property('mgrs_grid_zone')} "
        f"name={asset.get_editor_property('mgrs_map_name')} "
        f"georef={asset.get_editor_property('geo_reference')}"
    )

    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    if not les.load_level(target):
        log(f"RESULT: FAIL could not load {target}")
        return
    world = unreal.EditorLevelLibrary.get_editor_world()
    ws = world.get_world_settings()
    log(
        f"world_settings class={ws.get_class().get_name()} "
        f"soft_ptr={ws.get_editor_property('mgrs_data_asset_soft_ptr')}"
    )

    if mode != "apply":
        log("RESULT: INSPECT done (no changes)")
        return

    try:
        ws.set_editor_property("mgrs_data_asset_soft_ptr", asset)
    except Exception as error:  # noqa: BLE001 -- fall back to the path form
        log(f"object assignment refused ({error}); assigning SoftObjectPath")
        ws.set_editor_property("mgrs_data_asset_soft_ptr", unreal.SoftObjectPath(asset_path))
    saved = les.save_current_level()
    log(
        f"RESULT: APPLY saved={saved} soft_ptr={ws.get_editor_property('mgrs_data_asset_soft_ptr')}"
    )


main()
