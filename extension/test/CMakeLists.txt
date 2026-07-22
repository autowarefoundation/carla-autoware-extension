# System GTest (libgtest-dev): the build uses the stock toolchain, so the
# distro's prebuilt libraries link cleanly — no from-source build needed.
find_package(GTest REQUIRED)

add_executable(extension_tests test_smoke.cpp test_messages.cpp test_status_publishers.cpp
  test_gnss_pose.cpp test_control_conversion.cpp test_engage.cpp test_init.cpp)
# src/ is added so the tests can reach implementation-detail headers (e.g.
# publishers/StatusPublishers.h) that live next to their .cpp rather than
# under the public include tree; include/ arrives via extension-objects.
target_include_directories(extension_tests PRIVATE ${CMAKE_SOURCE_DIR}/src)
target_link_libraries(extension_tests PRIVATE GTest::gtest_main extension-objects)
add_test(NAME extension_tests COMMAND extension_tests)
