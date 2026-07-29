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

## ROS 2 wire visibility — verdict (Task 9)

**RESOLVED. Rung 1 of the pre-registered ladder: a config-level fix.**
The fork's native ROS 2 topics ARE on the wire and ARE measurable from
a stock `bench-observer:universe-devel` container. No observer variant
is needed, no image is rebuilt, and B's M1/M2 are measurable. P1
Verdict 8.4's "invisible to every `ros2` CLI" is reproduced exactly —
but by the _consumer's_ transport configuration, not by anything in
the fork.

Both directions were measured, and they behave the same way:
sensing **out** of the fork (matrix rows 1–11 below) and control **in**
to it (the ingress table further down, assayed by ego motion). Both
fail with shared memory on and both work with `udp_only.xml`.

Evidence run: tier4 editor `-game` Town10HD_Opt `--ros2
-carla-rpc-port=3000 -RenderOffScreen -nosound`, engine BuildId
`4210e602-78ec-46e1-8f2f-03fadbe036a3` (matches `pins.yaml`), one
VLP16 LiDAR spawned through the CARLA API with the fork's own
`autoware_demo.py` attributes (`ros_name=velodyne_top`,
`ros_topic_name=/sensing/lidar/top/pointcloud_raw_ex`,
`sensor_tick=0.1`) plus `enable_for_ros()`. CARLA-API-side cadence
over the same run: **10.002 Hz** (3300 frames).

### Root cause — two independent faults, both consumer-side

1. **Shared memory.** Every fork publisher builds its participant from
   `PARTICIPANT_QOS_DEFAULT`, so Fast-DDS 2.11.2's builtin transports
   (SHM + UDPv4) apply and the participant announces its **user-data
   locators as SHM only** (`kind=16`); metatraffic stays on UDPv4.
   A Fast-DDS **2.6.11** reader (ROS 2 Humble — the observer image and
   the Autoware image both) with SHM enabled therefore selects the SHM
   locator, and 2.11.2's SHM segment protocol is not interoperable
   with 2.6.11's. The result is the confusing shape P1 hit: discovery
   and endpoint matching **succeed** (`ros2 topic list` and
   `ros2 topic info -v` show the publisher with correct type and QoS)
   while **no sample ever arrives**. Turning SHM off on the consumer
   forces UDPv4 and data flows at full rate.
2. **The harness's default observer transport.** `--rmw
rmw_cyclonedds_cpp` with `docker/cyclonedds.xml` (interfaces pinned
   to `lo`) sees **nothing at all** against the fork — no topic list
   entry, no echo, no rate. That is verbatim "invisible to every
   `ros2` CLI", and it is the campaign's own default.

A third, purely environmental trap sits on top of both: this host's
login shell exports `ROS_DOMAIN_ID=123` and
`RMW_IMPLEMENTATION=rmw_cyclonedds_cpp` (`~/.zshrc:126-127`). Any
probe run from a login shell without overriding them lands on domain
123 with Cyclone and sees nothing, whatever the transport. Export
`ROS_DOMAIN_ID=0` in every shell and pass it into every container.

**The fork cannot be reconfigured from its own side.** Neither
`FASTRTPS_DEFAULT_PROFILES_FILE` nor `FASTDDS_BUILTIN_TRANSPORTS`
reaches its participants: `create_participant` selects the
XML-derived default QoS by **pointer identity** with
`PARTICIPANT_QOS_DEFAULT`, and every fork publisher copies that object
before setting `.name()`, which loses the identity. Measured, not
inferred — a stand-in publisher using the fork's exact code shape kept
announcing SHM locators under both env knobs, and switched to UDPv4
only when built from `get_default_participant_qos()`. So the fix has
to be applied at the consumer, which is what the matrix below does.

### Transport matrix (live fork, `/sensing/lidar/top/pointcloud_raw_ex`)

`LIST` = `ros2 topic list` shows it; `ECHO` = `ros2 topic echo --once`
returns; `RATE` = `ros2 topic hz`. The `ros2` daemon is stopped in
every cell first, so no cell is a cached negative.

`LHO` is `ROS_LOCALHOST_ONLY`. Rows 1–7 run in the observer image
`bench-observer:universe-devel`; rows 8–11 run in the exact pinned
`autoware_universe_devel.digest` image cell B launches Autoware from.
Both are ROS 2 Humble with Fast-DDS 2.6.11.

| #   | rmw      | profile          | LHO | domain  | LIST | ECHO | RATE       |
| --- | -------- | ---------------- | --- | ------- | ---- | ---- | ---------- |
| 1   | fastrtps | none (SHM on)    | 0   | 0       | yes  | no   | —          |
| 2   | fastrtps | `udp_only.xml`   | 0   | 0       | yes  | yes  | **10.006** |
| 3   | fastrtps | none (SHM on)    | 1   | 0       | no   | no   | —          |
| 4   | fastrtps | `udp_only.xml`   | 1   | 0       | yes  | yes  | 10.071     |
| 5   | cyclone  | `cyclonedds.xml` | 0   | 0       | no   | no   | —          |
| 6   | cyclone  | none             | 0   | 0       | yes  | yes  | 10.020     |
| 7   | fastrtps | `udp_only.xml`   | 0   | **123** | no   | no   | —          |
| 8   | fastrtps | none (SHM on)    | 0   | 0       | yes  | no   | —          |
| 9   | fastrtps | `udp_only.xml`   | 0   | 0       | yes  | yes  | **10.070** |
| 10  | cyclone  | `cyclonedds.xml` | 0   | 0       | no   | no   | —          |
| 11  | cyclone  | none             | 0   | 0       | no   | yes  | 9.930      |

Rows 6 and 11 work only because Cyclone with no profile binds a
routable interface (`wlp130s0f0`) — they make the measurement depend
on the host's wireless NIC and on Cyclone's graph being flaky for
bare-DDS publishers (row 11 receives data while `topic list` denies
the topic exists). Do not use them.

Row 9 answers only half of the campaign's decision question: it is
**egress** (fork → consumer). A closed loop also needs **ingress**
(Autoware → fork), and the mechanism above is not automatically
symmetric — see the next section, which measures it.

### Control ingress (Autoware → fork) — measured, and it decides the GO

The fork's _subscribers_ build their participants exactly as its
publishers do (`AutowareSubscriber.cpp:94-97`,
`CarlaEgoVehicleControlSubscriber.cpp:51-54`: copy
`PARTICIPANT_QOS_DEFAULT`, then `.name()`), so the same reasoning had
to be checked in the writer→reader direction: a `udp_only.xml` Autoware
**writer** has no SHM transport at all, and if the fork's readers
announced SHM-only locators it could never reach them. Cell B's
`control_topic: /control/command/control_cmd` travels exactly that
path.

**They do not.** Unlike the participants' default (user-data) locators,
the fork's _reader_ announcements carry **both** a UDPv4 loopback
locator and a SHM one:

```text
[EDP-reader] topic="rt/control/command/control_cmd"
             type="autoware_control_msgs::msg::dds_::Control_"
               reader-uni  kind=1 127.0.0.1:7415
               reader-uni  kind=16 :7419
```

so a UDP-only writer has something to send to. Confirmed physically,
not by inspection: a `role_name=hero` ego makes `ActorDispatcher` call
`ROS2::AddActorCallback`, which constructs `AutowareController` and its
readers on `/control/command/control_cmd` (RELIABLE, TRANSIENT_LOCAL,
KEEP_LAST 1); `ROS2.cpp:121-130` then applies
`longitudinal.acceleration` straight through
`ApplyVehicleAccelerationControl` with no engage or gear gating. So ego
speed is a direct assay of delivery. Publishing
`autoware_control_msgs/msg/Control` with `acceleration: 2.0` at 10 Hz
from the pinned Autoware image, the two arms back to back. Each row
states its own publish window, because the two differ:

| Autoware-side transport       | publish window | ego result                                     | verdict           |
| ----------------------------- | -------------- | ---------------------------------------------- | ----------------- |
| fastrtps, no profile (SHM on) | 15 s           | never leaves rest: 0.000 m/s, 0.001 m          | **not delivered** |
| fastrtps + `udp_only.xml`     | 12 s           | 15.93 m/s and 61.6 m by 8 s after motion onset | **delivered**     |

The `udp_only` arm accelerates at 1.99 m/s² against a commanded
2.0 m/s² (1.936 → 3.920 → 5.915 → 7.928 → 9.938 → 11.937 → 13.919 →
15.927 m/s on consecutive seconds).

**What this pairing controls, precisely.** Both arms ran inside one
`spawn_ego.py` process against **actor id 27**, with no teardown, respawn
or world reset between them: that process logs a single `READY` line, and
its CARLA-API LiDAR frame counter runs monotonically 10 → 890 across
both — the SHM-on arm at frames 240–450, the `udp_only` arm at frames
580–730. Across 89 sampled seconds the log contains exactly **one**
rest-to-motion transition, and it is in the `udp_only` arm. Actor,
blueprint, spawn pose, CARLA process, engine build, map, sim tick and the
published message bytes are therefore all held fixed, and the
Autoware-side transport is the only variable.

**What it does not control.** Arm order is fixed, not randomised: SHM-on
ran first, `udp_only` second, so this pair alone does not exclude a
warm-up effect — a separate earlier `udp_only` run on a **different**
actor (id 25) does, having accelerated identically from a cold ego
(0 → 19.09 m/s, 80.7 m, same 2.00 m/s² slope). There is one replicate per
arm, not n ≥ 10; this is a delivered / not-delivered determination, not a
metric measurement, and nothing downstream scores it as one. The unequal
publish windows are immaterial in the direction that matters: the failing
arm got the **longer** one.

**So ingress fails and succeeds under exactly the same conditions as
egress, and the same one-line fix cures both.** With
`FASTRTPS_DEFAULT_PROFILES_FILE=udp_only.xml` on the Autoware side,
cell B's closed loop is feasible in **both** directions and the spec's
joint-failure clause is not triggered. Without it, an Autoware stack
would come up, match every endpoint, and drive nothing — the ego would
sit still while the logs looked healthy.

### The invocation cells B / B-hf / B45 (and D) must use

The cell id is **positional**, and `--arm` is required
(`run.sh:70-72,89`); `run.sh --cell B …` exits 2 with the usage block.

```bash
bash benchmarks/run.sh B --arm static --rmw rmw_fastrtps_cpp --shm off
```

`run.sh` maps `--rmw rmw_fastrtps_cpp --shm off` to
`--dds-profile benchmarks/observer/config/udp_only.xml` and mounts it
as `FASTRTPS_DEFAULT_PROFILES_FILE` in the observer container, which
is exactly the configuration measured in rows 2/4/9. Do NOT pass
`--shm on` (row 1: records nothing) and do NOT leave the Cyclone
default (row 5: records nothing). The recorded `observer_env` is:

```json
{
  "image": "bench-observer:universe-devel",
  "rmw": "rmw_fastrtps_cpp",
  "shm": "off",
  "topics_file": "B.yaml"
}
```

The **Autoware side of a B-family cell needs the same treatment, and
for the closed loop it is not optional**: Task 13's launch must give
the Autoware container `ROS_DOMAIN_ID=0`,
`RMW_IMPLEMENTATION=rmw_fastrtps_cpp` and
`FASTRTPS_DEFAULT_PROFILES_FILE` pointing at `udp_only.xml`
(bind-mounted). Without it, sensing does not arrive (row 8) **and**
control does not arrive (ingress table above) — both silently, with
every endpoint matched. Because that switches the DUT's own middleware
transport for the B family only, it is a registered confound; see
`benchmarks/README.md`, "Known confounds".

Acceptance check, run live: the stock `bench_observer` binary, invoked
exactly as `run.sh` invokes it, with `B.yaml`'s LiDAR row, recorded
**243 rows in 24 s (10.1 Hz)** into `observer.csv` with plausible
`size_bytes` (64–76 KB) plus 1711 `/clock` rows. Topic names on the
wire are exactly the ones `observer_topics/B*.yaml` already register —
no correction was needed.

### Limits of what the wire exposes

`ros2 node list` returns **empty**: the fork publishes as a bare DDS
application (`_CREATED_BY_BARE_DDS_APP_`), so no ROS graph node exists
for CARLA. Anything that enumerates nodes, or that needs node
parameters or lifecycle, will find nothing on the CARLA side. Topic-
level introspection is unaffected. With one LiDAR the fork's whole
published set is `/clock`, `/tf`,
`/sensing/lidar/top/pointcloud_raw_ex` (`/rosout`,
`/parameter_events` come from the consumer).

### Refuted hypotheses (kept with what refuted them)

- **"Fast-DDS version gap 2.11.2 vs Jazzy 2.14.6."** Refuted. Host
  ROS 2 Jazzy with `rmw_fastrtps_cpp` and SHM **on** both lists and
  receives (9.979 Hz). 2.11.2↔2.14.6 SHM interoperates; only
  2.11.2↔2.6.11 does not — so the version gap is real but points at
  **Humble**, the opposite of the standing note.
- **"Use Humble instead of Jazzy."** Refuted, and actively harmful:
  Humble is precisely the version whose SHM cannot read 2.11.2's.
- **"`WITH_ROS2` is not compiled into the editor build."** Refuted.
  `libUnrealEditor-Carla.so` carries `NEEDED
libcarla-ros2-native.so` and 121 undefined `carla::ros2::*` symbols.
- **"The fork hardcodes a transport, interface whitelist or
  `SHM_DEFAULT`."** Refuted. `grep -rn
"TransportDescriptor\|whitelist\|SHM_DEFAULT\|useBuiltinTransports"
LibCarla/source/carla/ros2/` returns **zero** matches; participant
  QoS is stock `PARTICIPANT_QOS_DEFAULT`.
- **"The participant never reaches the wire."** Refuted without a
  packet capture: the `UnrealEditor` PID owns 21 UDP sockets including
  `0.0.0.0:7400` (SPDP) and `7410`–`7417`, creates 12
  `/dev/shm/fastrtps_*` segments, and an independent raw participant
  observes its SPDP **and** its EDP writer announcements for
  `rt/clock`, `rt/tf` and `rt/sensing/lidar/top/pointcloud_raw_ex`
  (type `sensor_msgs::msg::dds_::PointCloud2_`).
- **"SPDP present but endpoint matching fails."** Refuted: matching
  succeeds in every cell that lists the topic; only the SHM-locator
  data path fails.
- **"The fork's Fast-DDS 2.11.2 SHM path is broken."** Refuted. A raw
  2.11.2 subscriber takes 200 samples in 20 s straight off the live
  fork over SHM.

### Reproducing the raw 2.11.2 probe

Not committed — rung 1 fired, so no `bench-observer-fastdds211` image
exists. Should a later task need a version-matched subscriber, it
links only already-built artifacts (no fork or engine rebuild):
Fast-DDS 2.11.2 and headers from
`~/src/carla-autoware-native/Build/Ros2Native/install`, the fork's
generated typesupport from
`LibCarla/source/carla/ros2/types/{PointCloud2,Header,Time,PointField}
{,PubSubTypes}.cpp`, compiled with the **UE5 sysroot clang and
libc++** — `Build/Ros2Native/install/lib/libfastrtps.so.2.11.2`
exports `std::__1::` symbols, so a stock `g++`/libstdc++ build cannot
link it. Two traps cost real time and are worth repeating: attach the
participant listener with `StatusMask::none()`, because a participant
listener with an active mask claims
`SubscriberListener::on_data_on_readers` and thereby suppresses
`DataReaderListener::on_data_available` (the probe then reports zero
samples on a working wire); and `DataWriter::write(void*)` returns
`bool`, not `ReturnCode_t`, so an unchecked `!=` comparison hides
write failures.
