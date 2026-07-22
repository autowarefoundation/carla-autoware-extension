#include <gtest/gtest.h>

#include "carla/ros2/extension/CarlaRos2Extension.h"

extern "C" unsigned carla_autoware_extension_abi_version();

TEST(smoke, abi_version_matches_header) {
  EXPECT_EQ(carla_autoware_extension_abi_version(), CARLA_ROS2_EXTENSION_API_VERSION);
  EXPECT_EQ(CARLA_ROS2_EXTENSION_API_VERSION, 1u);
}
