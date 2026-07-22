#!/usr/bin/env bash
# Meant to be SOURCED, never executed directly (the shebang above is only so
# editors/shellcheck treat this as bash). Source before building CARLA/the
# extension, or before a Phase B live run, for a consistent set of exports.
# `scripts/phase_b/run_phase_b.sh` pins ROS_DOMAIN_ID and CYCLONEDDS_URI itself
# (so it stays correct even if this file was never sourced); this file exists
# so a human shell matches the harness instead of drifting via the login
# shell's ROS_DOMAIN_ID=123 (see CLAUDE.md), which would otherwise split CARLA
# onto a different DDS domain than the `autoware` container and no topic would
# ever be discovered.
export CARLA_ROOT="${CARLA_ROOT:-$HOME/src/carla-autoware-integration}"
export CARLA_UNREAL_ENGINE_PATH="${CARLA_UNREAL_ENGINE_PATH:-$HOME/src/UnrealEngine}"
export ROS_DOMAIN_ID=0
export CYCLONEDDS_URI="file://$HOME/src/carla-autoware-extension/docker/cyclonedds.xml"
