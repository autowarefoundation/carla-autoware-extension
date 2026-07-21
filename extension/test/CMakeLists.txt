# GTest ABI note: the system libgtest-dev package (and a plain
# find_package(GTest REQUIRED) resolving to it) is built against the distro's
# default libstdc++, but toolchain/CarlaExtension.cmake forces UE-clang +
# STATIC libc++ for this whole project, so linking extension_tests against
# that system GTest fails with undefined references into libstdc++'s
# std::string/std::ostream symbols (verified: `undefined reference to
# std::ostream::_M_insert<double>`, `std::__cxx11::basic_string<...>
# ::_M_dispose()`, etc.). CARLA core hits the identical constraint and
# resolves it by building googletest from source with its own toolchain
# (CMake/Dependencies.cmake, FetchContent + BUILD_GMOCK/INSTALL_GTEST OFF).
# We do the same: reuse CARLA_ROOT's already-fetched googletest source
# (pinned to v1.14.0 by CARLA_GTEST_TAG) when present, so no network fetch
# is needed and the pin tracks CARLA's own; fall back to fetching that same
# pinned tag when CARLA_ROOT has no prebuilt _deps tree (e.g. a fresh CI
# checkout). Either path is compiled by OUR build with OUR toolchain, so the
# resulting GTest::gtest/GTest::gtest_main targets share our libc++ ABI.
set(CARLA_GTEST_SRC ${CARLA_ROOT}/Build/Development/_deps/googletest-src)
set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
if(EXISTS ${CARLA_GTEST_SRC}/CMakeLists.txt)
  add_subdirectory(${CARLA_GTEST_SRC} ${CMAKE_CURRENT_BINARY_DIR}/googletest-build EXCLUDE_FROM_ALL)
else()
  include(FetchContent)
  FetchContent_Declare(googletest
    URL https://github.com/google/googletest/archive/refs/tags/v1.14.0.zip)
  FetchContent_MakeAvailable(googletest)
endif()

add_executable(extension_tests test_smoke.cpp)
target_include_directories(extension_tests PRIVATE ${CMAKE_SOURCE_DIR}/include)
target_link_libraries(extension_tests PRIVATE GTest::gtest_main carla-autoware-extension)
add_test(NAME extension_tests COMMAND extension_tests)
