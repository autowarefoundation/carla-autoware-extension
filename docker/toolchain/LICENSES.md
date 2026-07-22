# Licenses and provenance of this image

This image contains **only third-party open-source software**. It contains no
Unreal Engine "Engine Code" or "Engine Tools" as defined by the Unreal Engine
EULA.

## 1. Native clang/sysroot toolchain (`/unreal-engine/Engine/Extras/ThirdPartyNotUE/...`)

Downloaded at build time from Epic's public CDN
(`https://cdn.unrealengine.com/Toolchain_Linux/`), which requires no
authentication or EULA acceptance. The UE EULA states that software under
`/Engine/Extras/ThirdPartyNotUE/` "is not itself Licensed Technology and is
instead licensed to you directly by its authors." Contents: clang 18.1.0rc
built from a public llvm-project commit (Apache-2.0 WITH LLVM-exception) and a
crosstool-NG GNU sysroot. The tarball bundles, and this image preserves, the
component license texts (`share/licenses/`) and the full corresponding sources
and build scripts (`build/`) for the GPL/LGPL components (gcc, glibc, binutils,
linux headers, mpfr, gmp, isl, gettext, libiconv, ncurses, zlib, zstd,
crosstool-ng). Do not strip these directories from derived images.

## 2. libc++ / libc++abi bundle (`/unreal-engine/Engine/Source/ThirdParty/Unix/LibCxx/`)

LLVM libc++/libc++abi headers and x86_64 static libraries as shipped in the
Unreal Engine source tree, repacked by
`scripts/toolchain/make_libcxx_tarball.sh`. License: UIUC/MIT dual
(`libcxx_License.txt`, included) with Apache-2.0 WITH LLVM-exception headers;
Epic's TPS metadata (`libcxx.tps`) and `PROVENANCE.md` ride alongside. The UE
EULA provides that third-party license terms take precedence over the EULA on
any inconsistency, and these licenses grant redistribution.

## 3. Everything else

Ubuntu 24.04 base plus distro packages (build-essential, ninja-build, cmake,
git, curl), under their respective Ubuntu/upstream licenses.

Full analysis: `docs/toolchain-image.md` in
<https://github.com/autowarefoundation/carla-autoware-extension>
