cmake_minimum_required(VERSION 3.20)
project(carla_autoware_extension CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT DEFINED ENV{CARLA_ROOT})
  message(FATAL_ERROR "CARLA_ROOT not set")
endif()
set(CARLA_ROOT $ENV{CARLA_ROOT})

# No DDS link: the extension performs zero direct DDS calls — every publish/
# subscribe crosses the host vtable (carla_cdr_* function pointers handed over
# by CARLA at carla_ros2_extension_init time), so the .so references no dds_*
# symbols (verify: nm -D | grep ' U dds_' is empty). Linking CycloneDDS here
# would only add a spurious DT_NEEDED entry and an unsatisfiable rpath at
# test-link time.

add_library(carla-autoware-extension SHARED
  src/version.cpp
  # Message library: PODs + CDR serializers/deserializer + RIHS01
  # type-info. The CDR codec itself (Cdr.h) is header-only, so there is no
  # src/messages/Cdr.cpp. The status/GNSS publishers, control subscribers, and
  # engage state machine follow, wired together by the init entrypoint:
  src/messages/AutowareMessages.cpp
  src/publishers/StatusPublishers.cpp
  src/publishers/GnssPosePublisher.cpp
  src/subscribers/ControlSubscribers.cpp
  src/engage/EngageStateMachine.cpp
  # Init entrypoint: the single exported carla_ros2_extension_init
  # symbol that wires all four subsystems together for the core loader.
  src/ExtensionInit.cpp
)
target_include_directories(carla-autoware-extension PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include)
set_target_properties(carla-autoware-extension PROPERTIES
  OUTPUT_NAME carla-autoware-extension)

enable_testing()
add_subdirectory(test)
