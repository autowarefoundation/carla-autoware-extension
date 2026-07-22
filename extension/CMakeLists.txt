cmake_minimum_required(VERSION 3.20)
project(carla_autoware_extension CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ROS 2 (Jazzy) message packages + fastcdr, installed via apt and resolved
# through the sourced ROS environment (source /opt/ros/jazzy/setup.bash).
find_package(fastcdr REQUIRED)
find_package(autoware_control_msgs REQUIRED)
find_package(autoware_vehicle_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
set(ROS_MSG_LIBS
  fastcdr
  autoware_control_msgs::autoware_control_msgs__rosidl_typesupport_cpp
  autoware_control_msgs::autoware_control_msgs__rosidl_typesupport_fastrtps_cpp
  autoware_vehicle_msgs::autoware_vehicle_msgs__rosidl_typesupport_cpp
  autoware_vehicle_msgs::autoware_vehicle_msgs__rosidl_typesupport_fastrtps_cpp
  geometry_msgs::geometry_msgs__rosidl_typesupport_cpp
  geometry_msgs::geometry_msgs__rosidl_typesupport_fastrtps_cpp)

# OBJECT library so the unit tests can link the implementation directly: the
# shared library below hides every symbol except the two exported C entry
# points (version.map), which would otherwise make the internals unlinkable
# from the test binary.
add_library(extension-objects OBJECT
  src/version.cpp
  src/messages/RosIdl.cpp
  src/publishers/StatusPublishers.cpp
  src/publishers/GnssPosePublisher.cpp
  src/subscribers/ControlSubscribers.cpp
  src/engage/EngageStateMachine.cpp
  src/ExtensionInit.cpp
)
set_target_properties(extension-objects PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(extension-objects PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_link_libraries(extension-objects PUBLIC ${ROS_MSG_LIBS})

add_library(carla-autoware-extension SHARED $<TARGET_OBJECTS:extension-objects>)
target_link_libraries(carla-autoware-extension PRIVATE ${ROS_MSG_LIBS})
# Export ONLY the C ABI entry points: the rosidl/fastcdr internals stay local
# so they can never cross-bind against same-named symbols inside the
# carla-server host process (which bundles its own fastcdr).
target_link_options(carla-autoware-extension PRIVATE
  -Wl,--version-script=${CMAKE_CURRENT_SOURCE_DIR}/version.map)
set_target_properties(carla-autoware-extension PROPERTIES
  OUTPUT_NAME carla-autoware-extension)

enable_testing()
add_subdirectory(test)
