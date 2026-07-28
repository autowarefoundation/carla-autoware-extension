# tier4-native build patches (approach B)

Two minimal source changes are required to build
`tier4/autoware-support` (the `carla-autoware-native` fork, remote name
`tier4` in `~/src/carla`) against this host's UE5 toolchain. Both lived
only as uncommitted working-tree edits in `~/src/carla-autoware-native`
until now (P1 Verdict 3 flagged this as a patch-policy gap: the extension
and python-bridge approaches both have their fixes under
`benchmarks/patches/`, tier4-native did not). This directory closes that
gap — apply both patches to reproduce the build.

```bash
cd ~/src/carla-autoware-native
git apply /path/to/benchmarks/patches/tier4-native/0001-toolchain-libm.patch
git apply /path/to/benchmarks/patches/tier4-native/0002-glibc-compat.patch
```

## Patch contents

- **`0001-toolchain-libm.patch`** — appends `-lm` to
  `CMAKE_CXX_STANDARD_LIBRARIES` in `CMake/Toolchain.cmake`. UE5's
  static `libc++.a`/`libc++abi.a` carries no `DT_NEEDED` on `libm`
  (unlike the shared `libc++.so`), so any C++ target that doesn't
  transitively pull in `m` from its own dependency graph fails to link
  with undefined `ceilf`/`floorf`/`sincosf`/`roundf`/`cosf`. This hits
  the `RecastBuilder` host tool. The CMake option
  `-Dstandard_math_library_linked_to_as_m=TRUE` does **not** substitute
  for this — it only affects a Recast/Detour link-probe, not the
  toolchain-wide standard-library list.
- **`0002-glibc-compat.patch`** — adds `LibCarla/source/carla/GlibcCompat.c`
  (a `__isoc23_strtol`/`strtoll`/`strtoul`/`strtoull` shim) plus the
  `LibCarla/CMakeLists.txt` hunk that compiles it as C11 and links it
  into `carla-server`. This is a straight port of upstream
  `815b8ba2c` (carla-simulator/carla PR #9596, in `~/src/carla`).
  `tier4/autoware-support` branched before that merge, so on a host
  with glibc >= 2.38 (where clang's implicit `_GNU_SOURCE` under
  `gnu++20` redirects `strtol()` to `__isoc23_strtol()`) the link fails
  with `ld.lld: undefined symbol: __isoc23_strtol` against UE5's
  Rocky-Linux-8 (glibc 2.17) sysroot.

  **Byte-identity of `GlibcCompat.c` against upstream `815b8ba2c` was
  verified** (`git show 815b8ba2c:LibCarla/source/carla/GlibcCompat.c |
  diff - LibCarla/source/carla/GlibcCompat.c` — empty diff, exit 0).

  **Client-archive caveat:** the shim attaches to `carla-server` only.
  `libcarla-client.a` keeps unshimmed `isoc23` references. This is
  harmless while the client links against host glibc, but it is a live
  edge if a client is ever linked inside the UE sysroot.

**Do NOT try `--sysroot=${UE_SYSROOT}` instead of the shim.** It was
tried first and rejected on evidence: the flag lands on **439 compile
lines and 0 link lines** (`add_compile_options` reaches compile rules
only), and because `CMAKE_CXX_FLAGS` stays empty, `try_compile`/
`check_symbol_exists` configure probes answer from the host's glibc
2.39 headers while every translation unit actually compiles against the
sysroot's 2.28 — a silent configure/compile divergence for what is a
four-symbol problem. The narrow shim in `0002` has no such asymmetry
and is also what upstream ships.

## Full build recipe

### 1. Worktree layout

```bash
cd ~/src/carla-autoware-native   # branch tier4/autoware-support
```

Content is not part of the git tree (gitignored). Symlink **both**
`Content/Carla` and `Content/Autoware` from the main `~/src/carla`
checkout — `Content/Autoware` is easy to miss because the plan/spec
only names `Content/Carla`, but `DA_MGRS_Shinjuku` and
`AutowareGameMode` live under `Content/Autoware`, and only the tier4
tree ships the C++ classes they derive from
(`Carla/Autoware/Data/MgrsDataAsset.h`,
`Carla/Autoware/Game/AutowareGameModeBase.{h,cpp}`):

```bash
mkdir -p Unreal/CarlaUnreal/Content
ln -sfn ~/src/carla/Unreal/CarlaUnreal/Content/Carla \
  Unreal/CarlaUnreal/Content/Carla
ln -sfn ~/src/carla/Unreal/CarlaUnreal/Content/Autoware \
  Unreal/CarlaUnreal/Content/Autoware
```

### 2. Do NOT run `CarlaSetup.sh`

The engine already exists at `CARLA_UNREAL_ENGINE_PATH`, and
`CarlaSetup.sh:97` would just reuse it — running it buys nothing and
risks re-triggering a multi-hour engine step. Likewise, the upstream
editor guide's `./Rglsetup.sh` step (Robotec GPU Lidar setup) **does
not exist on this branch** — RGL support lives on
`tier4/feature/rgl-support`, not `tier4/autoware-support`. Skip it;
nothing downstream depends on it.

### 3. Apply the two patches above, then configure

`tier4/autoware-support`'s `CMakePresets.json` sets `binaryDir` to
`${sourceDir}/Build` for **every** preset — not `Build/<presetName>`
like upstream `~/src/carla`. Every build command in this recipe uses
`Build` for that reason; `cmake --build Build/Release` (the upstream
form) is wrong here and will fail to find a build directory.

```bash
export CARLA_CCACHE=1   # required before configure AND every build
cmake --preset Release  # or whichever preset this build targets
```

### 4. Build

```bash
export CARLA_CCACHE=1   # UE5's clang wrapper only routes through
                         # ccache when this is set; forgetting it
                         # silently recompiles from scratch
cmake --build Build --target carla-unreal
cmake --build Build --target carla-unreal-editor
```

`carla-unreal-editor` depends on `carla-unreal`, so building the editor
target alone is sufficient for an editor-only rebuild; both are listed
here because a from-scratch build needs the game target too.

### 5. Known failure modes to check before assuming something deeper

- A stale `CarlaUnrealEditor` `Makefile.bin` left over from an earlier
  build (under
  `Unreal/CarlaUnreal/Intermediate/Build/Linux/x64/CarlaUnrealEditor/`)
  can break the target.
- Stale `carla-default-sky` link scripts have caused link failures in
  this tree before.
- If the editor was previously built against a different engine link,
  its `.modules` BuildId will mismatch the engine's and a `-game`
  launch aborts silently (no console, defaults to "do not rebuild").
  Compare BuildIds (see "BuildId parity" below) before debugging
  anything else.

### 6. Client-archive `isoc23` caveat (repeated from the patch note)

`libcarla-client.a` does not get the `GlibcCompat.c` shim — only
`carla-server` links it. This has never mattered because the Python
client wheel links against host glibc, not the UE sysroot. If a future
build ever links a client artifact inside the UE sysroot, this will
resurface as the same undefined-symbol failure `0002` fixes for the
server.

### 7. BuildId parity (acceptance gate)

After the rebuild, the tier4 editor's `.modules` BuildId must match the
shared engine's:

```bash
python3 - <<'EOF'
import json, glob
eng = json.load(open(glob.glob(
    "/home/youtalk/src/UnrealEngine/Engine/Binaries/Linux/"
    "UnrealEditor.modules")[0]))["BuildId"]
t4 = json.load(open(glob.glob(
    "/home/youtalk/src/carla-autoware-native/Unreal/CarlaUnreal/"
    "Plugins/Carla/Binaries/Linux/UnrealEditor.modules")[0]))["BuildId"]
print(eng, t4); assert eng == t4, "BuildId mismatch"
EOF
```

If the plugin `.modules` path has moved, locate it with
`find ~/src/carla-autoware-native -name UnrealEditor.modules`.

### 8. Boot smoke

The verified invocation runs the **shared engine's** `UnrealEditor`
binary directly, pointed at this tree's `.uproject` — there is no
project-local `CarlaUnrealEditor` executable to launch instead (the
`Binaries/Linux/CarlaUnrealEditor.target` file next to it is UBT
build metadata, not something you run):

```bash
/home/youtalk/src/UnrealEngine/Engine/Binaries/Linux/UnrealEditor \
  ~/src/carla-autoware-native/Unreal/CarlaUnreal/CarlaUnreal.uproject \
  Town10HD_Opt -game --ros2 -carla-rpc-port=<pinned-port> \
  -RenderOffScreen -nosound
```

`-nosound` is load-bearing on a headless host with no audio device —
without it startup can fail on audio init before reaching `LoadMap`.

Pin an explicit `-carla-rpc-port`: a port collision surfaces as
`SIGABRT` inside `LoadMap`, not as a clear bind error, and is easy to
misdiagnose as a build problem.

### Cleanup

- `pkill -f CarlaUE4-Linux-Shipping`, **never** `pkill -f CarlaUE4` —
  the latter self-matches the invoking shell in some setups.
- For an editor `-game` process specifically, match on the actual
  process name observed at runtime rather than guessing, and never use
  a pattern broad enough to also hit the editor of another tree (e.g.
  another worktree's `CarlaUnrealEditor`).
- A stalled sync-mode CARLA (bridge or otherwise holding the tick
  authority) may ignore `SIGTERM` — send `SIGKILL` if it does not exit.

## ROS 2 wire visibility — placeholder

**This section is a placeholder.** Task 9 (Approach B wire-visibility
diagnostic) will fill it in with its verdict on whether the tier4
fork's native ROS 2 topics are observable on the wire from this host,
and how. As of P1 (Verdict 8.4), native ROS 2 topics from this fork
were invisible to every `ros2` CLI tried on this host even though
`ROS_DOMAIN_ID`, QoS, and Fast-DDS shared memory all checked out
normal; gate (c) was measured client-side via the CARLA API as a
stand-in, not on the wire. Do not treat that stand-in as equivalent to
an on-the-wire measurement — it is exactly what Task 9 exists to
resolve.
