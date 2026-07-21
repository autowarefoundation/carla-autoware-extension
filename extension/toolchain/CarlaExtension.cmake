# The dlopened extension MUST use the same UE-bundled clang + STATIC libc++ as
# CARLA core, or the C++ runtime mismatches at the ABI seam. We consume CARLA's
# own toolchain file so the compiler and libc++ pin stay in lockstep.
if(NOT DEFINED ENV{CARLA_ROOT})
  message(FATAL_ERROR "CARLA_ROOT is not set (path to ~/src/carla-autoware-integration)")
endif()
include($ENV{CARLA_ROOT}/CMake/Toolchain.cmake)
