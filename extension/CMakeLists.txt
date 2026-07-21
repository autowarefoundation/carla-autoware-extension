cmake_minimum_required(VERSION 3.20)
project(carla_autoware_extension CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED ENV{CARLA_ROOT})
  message(FATAL_ERROR "CARLA_ROOT not set")
endif()
set(CARLA_ROOT $ENV{CARLA_ROOT})

# CARLA's own Ros2Native build vendors CycloneDDS 0.10.5 with the identical
# UE-clang + static-libc++ toolchain this project builds with (see
# toolchain/CarlaExtension.cmake); HINTS points find_library there first so we
# link the ABI-matching copy instead of whatever CycloneDDS the host's ROS 2
# distro happens to ship (falls back to default search paths if absent).
find_library(CYCLONEDDS_LIB ddsc REQUIRED
  HINTS ${CARLA_ROOT}/Build/Development/Ros2Native/install/lib)

add_library(carla-autoware-extension SHARED
  src/version.cpp
  # Message library (Task 17): PODs + CDR serializers/deserializer + RIHS01
  # type-info. The CDR codec itself (Cdr.h) is header-only, so there is no
  # src/messages/Cdr.cpp. Publishers (Task 18-19), subscribers (Task 20),
  # engage (Task 21), and the init entrypoint (Task 22) are added here as they land:
  src/messages/AutowareMessages.cpp
  src/publishers/StatusPublishers.cpp
  # src/publishers/GnssPosePublisher.cpp
  # src/subscribers/ControlSubscribers.cpp src/engage/EngageStateMachine.cpp
  # src/ExtensionInit.cpp
)
target_include_directories(carla-autoware-extension PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(carla-autoware-extension PRIVATE ${CYCLONEDDS_LIB})
set_target_properties(carla-autoware-extension PROPERTIES
  OUTPUT_NAME carla-autoware-extension)

enable_testing()
add_subdirectory(test)
