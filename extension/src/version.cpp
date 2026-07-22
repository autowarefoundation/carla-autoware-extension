#include "carla/ros2/extension/CarlaRos2Extension.h"

extern "C" unsigned carla_autoware_extension_abi_version() {
  return CARLA_ROS2_EXTENSION_API_VERSION;
}
