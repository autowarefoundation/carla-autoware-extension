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
# fail SILENTLY. This file exists so the mapping lives in exactly one place and
# every script derives from it rather than re-typing a default.
#
# carla_autoware_map_defaults <map-name> sets, for the caller to consume:
#   MAP_DEFAULT_DIR          container-side Autoware bundle ("" = unknown map)
#   MAP_DEFAULT_GRID_CENTRE  map-frame "X Y" centre for dummy_perception's
#                            all-free occupancy grid, or "" to centre it on the
#                            ego's live pose.
#
# On MAP_DEFAULT_GRID_CENTRE: Nishi-Shinjuku carries a baked constant that
# predates this table, and its live gate could not be re-run in the session that
# introduced the table, so it keeps that exact constant rather than silently
# moving ~7.5 m to the live ego pose. Maps without such a constant centre the
# grid on the ego, which is the more correct behaviour and what any new map
# should use.

carla_autoware_map_defaults() {
  case "$1" in
    NishishinjukuMap)
      MAP_DEFAULT_DIR=/autoware_map/nishishinjuku
      MAP_DEFAULT_GRID_CENTRE="81377.34 49916.93"
      ;;
    Town10HD_Opt)
      MAP_DEFAULT_DIR=/autoware_map/town10
      MAP_DEFAULT_GRID_CENTRE=""
      ;;
    *)
      MAP_DEFAULT_DIR=""
      MAP_DEFAULT_GRID_CENTRE=""
      ;;
  esac
}
