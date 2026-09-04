#!/usr/bin/env bash
# Meant to be SOURCED. The single per-map table for the E2E harness.
#
# Three things have to agree on which map is being driven, and none of them
# announces a disagreement:
#   the CARLA map          -- what the editor loads and the runner targets
#   the Autoware bundle    -- MAP_DIR, which launch_autoware.sh passes as
#                             map_path:= and dummy_perception.py reads its
#                             traffic-light groups from
#   the converter offset   -- CARLA_AUTOWARE_MAP, read by the extension .so
# Getting the bundle wrong localizes against another map's pointcloud; getting
# the traffic-light source wrong publishes another map's signals as green. Both
# fail SILENTLY.
#
# WHAT THIS FILE GUARANTEES, exactly: every SHELL entry point of the harness
# derives its per-map values from the table below instead of re-typing them --
# run_e2e.sh, launch_autoware.sh and arm_closed_loop.sh all source this file,
# and an unknown map name is refused loudly in each rather than defaulted.
#
# WHAT IT DOES NOT COVER: scripts/e2e/dummy_perception.py runs container-side
# under rclpy, where a bash function cannot be sourced, so it keeps two module
# constants as BARE-INVOCATION fallbacks -- DEFAULT_MAP (from $MAP_DIR, itself
# exported by the callers above) and EGO_X/EGO_Y, which duplicate
# Nishi-Shinjuku's MAP_DEFAULT_GRID_CENTRE below. arm_closed_loop.sh always
# overrides both (MAP_DIR via the container environment, the centre via
# --ego-xy), so they apply only to a hand-run node -- but they are duplicates,
# and keeping them in step with this table is manual.
#
# carla_autoware_map_defaults <map-name> sets, for the caller to consume:
#   MAP_DEFAULT_DIR          container-side Autoware bundle ("" = unknown map)
#   MAP_DEFAULT_GRID_CENTRE  map-frame "X Y" centre for dummy_perception's
#                            all-free occupancy grid, or "" to centre it on the
#                            ego's live pose.
#   MAP_DEFAULT_GOAL         map-frame route goal "X Y Z QZ QW" for
#                            arm_closed_loop.sh ("" = no goal registered).
#
# On MAP_DEFAULT_GRID_CENTRE: Nishi-Shinjuku carries a baked constant that
# predates this table, and its live gate could not be re-run in the session that
# introduced the table, so it keeps that exact constant rather than silently
# moving ~7.5 m to the live ego pose. Maps without such a constant centre the
# grid on the ego, which is the more correct behaviour and what any new map
# should use.
#
# On MAP_DEFAULT_GOAL: both goals were picked from map geometry alone, never
# from a driven trajectory, so the strict 1.0 m G2 gate stays honest
# (Nishi-Shinjuku: 23.3 m into lanelet 226; Town10HD_Opt: lanelet 1942, the end
# of the 420 m geometry-scored route -- docs/running-e2e.md). A goal in the
# wrong map's frame is 81 km outside the other's and fails loudly, so this entry
# is not preventing a silent failure; it is closing the last per-map knob that
# still had to be typed by hand next to three that no longer do.

# Every assignment below is an OUTPUT for the caller to read; this file is only
# ever sourced, so shellcheck cannot see those uses and reports each one as
# SC2034. (Pre-existing: the same warning applied before MAP_DEFAULT_GOAL was
# added.)
# shellcheck disable=SC2034
carla_autoware_map_defaults() {
  case "$1" in
    NishishinjukuMap)
      MAP_DEFAULT_DIR=/autoware_map/nishishinjuku
      MAP_DEFAULT_GRID_CENTRE="81377.34 49916.93"
      MAP_DEFAULT_GOAL="81571.616 50019.827 42.07 0.090888 0.995861"
      ;;
    Town10HD_Opt)
      MAP_DEFAULT_DIR=/autoware_map/town10
      MAP_DEFAULT_GRID_CENTRE=""
      MAP_DEFAULT_GOAL="-101.021 55.014 0.0 -0.910299 0.413952"
      ;;
    *)
      MAP_DEFAULT_DIR=""
      MAP_DEFAULT_GRID_CENTRE=""
      MAP_DEFAULT_GOAL=""
      ;;
  esac
}
