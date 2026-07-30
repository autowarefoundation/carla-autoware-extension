cmake_minimum_required(VERSION 3.16)
project(bench_observer)
find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rosgraph_msgs REQUIRED)
find_package(nav_msgs REQUIRED)
find_package(sensor_msgs REQUIRED)
# geometry_msgs (the typed `pose` kind's PoseWithCovarianceStamped) and
# tf2_msgs (the typed `tf` kind's TFMessage) are declared EXPLICITLY even
# though nav_msgs pulls geometry_msgs in transitively: a direct #include
# needs a direct dependency, or the build breaks the moment that transitive
# path changes.
find_package(geometry_msgs REQUIRED)
find_package(tf2_msgs REQUIRED)
# PublishedTime's package on the pinned universe-devel-cuda base (verified
# by build attempt: find_package(autoware_internal_debug_msgs) succeeds on
# that image, but the package no longer carries PublishedTime -- it moved
# to autoware_internal_msgs) is autoware_internal_msgs, not
# autoware_internal_debug_msgs as the 0.45-to-current rename might suggest.
# tier4_debug_msgs remains the fallback for the 0.45.1 base (Task 21).
find_package(autoware_internal_msgs QUIET)
find_package(tier4_debug_msgs QUIET)

add_executable(bench_observer src/bench_observer.cpp)
ament_target_dependencies(bench_observer
  rclcpp rosgraph_msgs nav_msgs geometry_msgs tf2_msgs)
if(autoware_internal_msgs_FOUND)
  target_compile_definitions(bench_observer PRIVATE BENCH_PT_AUTOWARE_INTERNAL)
  ament_target_dependencies(bench_observer autoware_internal_msgs)
elseif(tier4_debug_msgs_FOUND)
  target_compile_definitions(bench_observer PRIVATE BENCH_PT_TIER4)
  ament_target_dependencies(bench_observer tier4_debug_msgs)
endif()

add_executable(bench_pub src/bench_pub.cpp)
ament_target_dependencies(bench_pub rclcpp sensor_msgs)

install(TARGETS bench_observer bench_pub DESTINATION lib/${PROJECT_NAME})
ament_package()
