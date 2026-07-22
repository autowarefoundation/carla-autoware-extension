# UE5 toolchain image — provenance, EULA analysis, and operating procedures

This document is the reference for `ghcr.io/autowarefoundation/carla-ue5-toolchain`, the container image that supplies the UE5-bundled clang/libc++ toolchain the `extension/` C++ build needs. It records what the image contains and deliberately excludes, the EULA analysis behind publishing it, the procedures for rebuilding the image and regenerating its LibCxx release asset, the merge order that gates when the `cpp-tests` CI job goes live, and the ready-to-paste release description for the `ue5-libcxx-v1` GitHub Release.

## 1. What the image is

**Name and tags:** `ghcr.io/autowarefoundation/carla-ue5-toolchain`, published as `:24.04` (a moving tag, repointed by every `build-toolchain-image` dispatch) and `:24.04-<sha12>` (immutable, suffixed with the first 12 characters of the commit SHA that triggered the build). `ci.yaml`'s `cpp-tests` job is pinned to the moving `:24.04` tag for now; a follow-up commit may switch it to a specific immutable digest once one exists.

**What it contains:**

- Ubuntu 24.04 (`noble`) base plus `build-essential`, `ninja-build`, `cmake` (3.28.3, which satisfies the extension's `cmake_minimum_required(3.20)` floor, so no separate Kitware install is needed), `git`, `curl`, `ca-certificates`.
- Epic's public-CDN clang/sysroot toolchain (`native-linux-v23_clang-18.1.0-rockylinux8.tar.gz`, sha256-pinned), extracted under `/unreal-engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/`, with `share/licenses/` and `build/` (the GPL/LGPL corresponding sources and build scripts for gcc, glibc, binutils, linux headers, mpfr, gmp, isl, gettext, libiconv, ncurses, zlib, zstd, crosstool-ng) intentionally kept in place.
- The UE-tree libc++/libc++abi bundle (`ue5-libcxx.tar.gz`, sha256-pinned, downloaded from this repository's `ue5-libcxx-v1` GitHub Release), extracted under `/unreal-engine/Engine/Source/ThirdParty/Unix/LibCxx/`, including its license text, Epic's `libcxx.tps` metadata, and a `PROVENANCE.md`.
- RHEL-style `/lib64` and `/usr/lib64` symlink shims: the Rocky-Linux-8-built clang's linker scripts expect those absolute paths, while Ubuntu keeps the same libraries under `/lib/x86_64-linux-gnu/` and `/usr/lib/x86_64-linux-gnu/`.
- `ENV CARLA_UNREAL_ENGINE_PATH=/unreal-engine`, so `extension/toolchain/CarlaExtension.cmake` resolves the toolchain with no further configuration.

**What it deliberately excludes:**

- **Engine Code and Engine Tools** — no UE source, no editor, no compiled UE binaries. Only the two third-party-OSS pieces above are UE-tree-derived, and both fall outside the UE EULA's "Licensed Technology" definition (see the EULA analysis below).
- **OpenSSL from the UE tree** — the extension build never resolves or links it (`extension/toolchain/CarlaExtension.cmake` and CARLA's `CMake/Toolchain.cmake` reach only the clang sysroot and `LibCxx`), so it was dropped from the design outright rather than analyzed for shipping.
- **conda, SDL, Vulkan, and CARLA-wheel tooling** — none of these are needed to build `libcarla-autoware-extension.so`.
- **`Linux_SDK.json`** — never shipped. Only the toolchain version string it would have pinned (`v23_clang-18.1.0-rockylinux8`) is carried, as a plain Dockerfile `ARG` rather than a copyrightable file.

**Provenance pointer:** every image ships `/LICENSES.md` (copied in from `docker/toolchain/LICENSES.md` at build time), with the same per-artifact breakdown and a pointer back to this document for the full analysis.

## 2. EULA analysis

The current Unreal Engine End User License Agreement, Section 6.b ("Third Party Software"), draws the line this image relies on:

> "Third Party Software that is only bundled with the Licensed Technology as independent, standalone software can be found in the installation directory for each engine version under the /Engine/Extras/ThirdPartyNotUE/ sub-folder. This Third Party Software is not itself Licensed Technology and is instead licensed to you directly by its authors under the license terms provided in the /Engine/Extras/ThirdPartyNotUE/ sub-folder."

The same section then states which terms govern when the EULA and a third-party license disagree:

> "In the case of additional license terms, the additional license terms will take precedence over any inconsistencies with the terms of this License with regard to the Third Party Software licensed under those additional license terms."

Per-artifact verdicts:

1. **Epic CDN clang/sysroot toolchain tarball** (`native-linux-v23_clang-18.1.0-rockylinux8.tar.gz`) — low risk. It installs under `/Engine/Extras/ThirdPartyNotUE/`, which the first quote above carves out of "Licensed Technology" entirely. Contents verified locally: clang 18.1.0rc built from a public `llvm-project` commit (Apache-2.0 WITH LLVM-exception) plus a crosstool-NG GNU sysroot that bundles the full corresponding sources (gcc-13.2.0, glibc-2.28, binutils-2.40, linux-4.18.20, mpfr, gmp, isl, gettext, libiconv, ncurses, zlib, zstd, crosstool-ng) together with their license texts (`share/licenses/`) and build scripts (`build/`) — a redistribution-compliance kit by construction. Condition, carried into the Dockerfile and `LICENSES.md`: never strip `share/licenses/` or `build/` from the published image, since keeping them in place is how the GPL/LGPL corresponding-source obligation is met.
2. **UE-tree `LibCxx/` (headers plus `libc++.a`/`libc++abi.a`)** — low risk, conditioned. Epic's own `libcxx.tps` classifies it as Third Party Software, so the second quote above governs: its license — UIUC/MIT dual per `libcxx_License.txt`, with Apache-2.0 WITH LLVM-exception headers — takes precedence over the EULA on any inconsistency, and that license explicitly permits redistribution. Epic also ships `BuildLibCxx.sh` (the script that builds these artifacts from LLVM sources) inside the very same publicly downloadable CDN toolchain tarball as item 1, underscoring that the build recipe itself is not confidential. Condition: bundle `libcxx_License.txt`, `libcxx.tps`, and a provenance note (`PROVENANCE.md`) in both the release tarball and the image — done by `scripts/toolchain/make_libcxx_tarball.sh` and `docker/toolchain/Toolchain.Dockerfile`.
3. **OpenSSL from the UE tree** — dropped from the design. The extension build never resolves or links it, so there is no artifact to analyze or ship.
4. **`Linux_SDK.json`** — never shipped. Only the version string it would have pinned is carried, as a Dockerfile `ARG`, which is a fact rather than a copyrightable artifact.

**Residual risk:** the EULA's definition of "Engine Tools" has a broad third prong — "other software that may be used to develop standalone products based on the Licensed Technology" — and an extreme reading could try to stretch that prong over the toolchain. The explicit `/Engine/Extras/ThirdPartyNotUE/` carve-out quoted above defeats that reading for item 1, and item 2's own Third-Party-Software classification defeats it for item 2: neither artifact is Engine Code, an editor, or a Developer/Editor-folder module, the other two prongs of the same "Engine Tools" definition. Community precedent agrees with this reading: Unreal Containers documents that the EULA forbids distributing container images containing Engine Tools through publicly-accessible registries, but that restriction is scoped to images that include Engine Tools in the first place — an image with no Unreal Engine materials falls outside it entirely, and this image's only UE-tree-derived content is items 1 and 2 above, both third-party OSS carved out or classified as such by the EULA itself. Non-blocking option, left to AWF's judgment: notify Epic's licensing contact before flipping the GHCR package public. This is not a condition of the analysis above, just a courtesy AWF may choose to extend.

Sources: [UE EULA](https://www.unrealengine.com/eula/unreal), [UE EULA (PDF)](https://cdn2.unrealengine.com/unreal-engine-end-user-license-agreement-d2812e10c642.pdf), [Unreal Containers: EULA Restrictions](https://unrealcontainers.com/docs/obtaining-images/eula-restrictions), [UE Native Toolchain docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/native-toolchain?application_version=4.27).

## 3. Rebuild procedure

To rebuild and republish the image — for a toolchain version bump, a LibCxx tarball update, or any other Dockerfile change:

1. Edit `docker/toolchain/Toolchain.Dockerfile`: bump `TOOLCHAIN_VERSION`/`TOOLCHAIN_SHA256` for a new Epic CDN toolchain release, and/or `LIBCXX_URL`/`LIBCXX_SHA256` for a new LibCxx tarball (see the tarball regeneration procedure below). Both downloads in the Dockerfile fail loudly on a sha256 mismatch, so the pin must match the actual asset before the build will succeed.
2. Commit and merge the Dockerfile change to `main` through the normal PR process.
3. Dispatch `build-toolchain-image` (`.github/workflows/build-toolchain-image.yml`, `workflow_dispatch`-only) from the Actions tab. It builds and pushes both the moving `:24.04` tag and the immutable `:24.04-<sha12>` tag to `ghcr.io/autowarefoundation/carla-ue5-toolchain` using `GITHUB_TOKEN` with `packages: write` — no UE checkout and no additional secrets are needed anywhere in the workflow.
4. **First time only:** a freshly created GHCR package defaults to private. An organization admin must flip it public from the GitHub UI: on the package's page, **Package settings** → **Danger Zone** → **Change visibility**. This must happen before the Phase B stack (which activates `cpp-tests`) merges, since every `cpp-tests` run pulls the image anonymously.

## 4. Tarball regeneration

The LibCxx release asset is produced offline, by a UE licensee, on a machine with a full Unreal Engine source checkout — the CI image build itself never touches the (private) UE repository.

1. On that machine, set `UE_ROOT` to the UE checkout (default `$HOME/src/UnrealEngine`) and run `bash scripts/toolchain/make_libcxx_tarball.sh`. The script preflights that `Engine/Source/ThirdParty/Unix/LibCxx/include`, the `x86_64-unknown-linux-gnu` `libc++.a`, `libcxx.tps`, and `Licenses/libcxx_License.txt` all exist under `UE_ROOT`, and refuses to pack if any is missing.
2. It stages `Unix/LibCxx/{include,lib/Unix/x86_64-unknown-linux-gnu}`, `libcxx.tps`, `libcxx_License.txt` (both under `Licenses/` and alongside `LibCxx/`), and a generated `PROVENANCE.md` recording the source UE commit, then writes `ue5-libcxx.tar.gz` and `ue5-libcxx.tar.gz.sha256` to `OUT_DIR` (default `/tmp/ue5-libcxx`).
3. Upload `ue5-libcxx.tar.gz` as an asset on the `ue5-libcxx-v1` GitHub Release on `autowarefoundation/carla-autoware-extension` (create the release if it does not exist yet, using the template in the next section as its description).
4. Update `LIBCXX_SHA256` in `docker/toolchain/Toolchain.Dockerfile` to the value printed by the script (also written to `ue5-libcxx.tar.gz.sha256`), then follow the rebuild procedure above to publish a new image with the updated tarball.

The tarball is byte-reproducible: the script pipes a deterministic `tar` invocation (`--sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner`) through `gzip -n` (no embedded timestamp), so regenerating it from the same UE checkout reproduces the exact bytes, and therefore the same `LIBCXX_SHA256`, every time.

## 5. Merge-order note

The image mechanism and the code that depends on it are deliberately decoupled, and they land in this order:

1. **PR A** — the toolchain-image mechanism (`docker/toolchain/`, `scripts/toolchain/`, `build-toolchain-image.yml`, the `cpp-tests` job in `ci.yaml`, and this document) — merges to `main` on its own. Its new `cpp-tests` job stays dormant: a `detect` job checks `git ls-files extension/` and exposes `has_ext` as a job output, and `cpp-tests` carries `needs: detect` plus `if: needs.detect.outputs.has_ext == 'true'` at the job level. Because `extension/` does not exist on `main` yet, `has_ext` resolves to `false` and the whole `cpp-tests` job — including its `container:` — is skipped outright; no toolchain image is pulled. This is a job-level gate, not a step-level guard: a step-level `if` (such as `hashFiles('extension/**') != ''` on individual steps) cannot stop the job's `container:` from being pulled at job initialization, since container pull happens before any step's `if` is evaluated, so only gating the whole job keeps the mechanism truly dormant.
2. **Release asset upload** — the `ue5-libcxx-v1` release is created and the LibCxx tarball from the tarball-regeneration procedure is attached.
3. **Image build and public flip** — `build-toolchain-image` is dispatched, and the resulting GHCR package is flipped public.
4. **The Phase B PR stack (#7–#11) and the ddsc-link-removal PR** merge afterward. Only once the stack lands does `extension/` exist on `main`, at which point `cpp-tests` stops being dormant.

Two consequences follow from this order. First, `cpp-tests` stays dormant for the entire time the stack PRs are open and being tested: each stack PR's CI runs against a merge ref built from its own stacked base, which predates PR A, so none of the stack PRs individually execute the new job — it is dormant on every one of them, not merely skipped once. Second, the first push to `main` after the full stack merges is therefore the actual canary: it is the first CI run where `extension/**` is non-empty, where the public image is pulled anonymously with no secrets involved, and where `cpp-tests` is expected to build the extension and pass 67/67 GTest cases end-to-end for the first time on this repository's own infrastructure.

## Release-body template (ue5-libcxx-v1)

Paste the block below as-is into the `ue5-libcxx-v1` GitHub Release description, filling in the sha256 line first.

```markdown
This asset (`ue5-libcxx.tar.gz`) is a repacked copy of the UE-tree libc++/libc++abi headers and x86_64 static libraries (`Engine/Source/ThirdParty/Unix/LibCxx`), produced by `scripts/toolchain/make_libcxx_tarball.sh`, for use by the `ghcr.io/autowarefoundation/carla-ue5-toolchain` CI toolchain image.
It is EULA-safe: Epic's own `libcxx.tps` classifies `Engine/Source/ThirdParty/Unix/LibCxx` as Third Party Software, not Engine Code or Engine Tools, and the UIUC/MIT dual license text (`libcxx_License.txt`) is included in this tarball.
The Unreal Engine EULA states that additional third-party license terms take precedence over the EULA on any inconsistency with regard to that Third Party Software, and the libc++/libc++abi license grants redistribution.
The build recipe for these artifacts, `BuildLibCxx.sh`, is itself publicly distributed by Epic inside the same CDN-hosted native toolchain tarball this image downloads, so nothing about the recipe or the artifacts here is confidential.
This tarball contains no Unreal Engine Code and no Engine Tools: only the third-party libc++/libc++abi build output, its license text, Epic's TPS metadata, and a provenance note.
SHA256: <fill at upload time from scripts/toolchain/make_libcxx_tarball.sh output>
Sources: [UE EULA](https://www.unrealengine.com/eula/unreal), [UE EULA (PDF)](https://cdn2.unrealengine.com/unreal-engine-end-user-license-agreement-d2812e10c642.pdf), [Unreal Containers: EULA Restrictions](https://unrealcontainers.com/docs/obtaining-images/eula-restrictions), [UE Native Toolchain docs](https://dev.epicgames.com/documentation/en-us/unreal-engine/native-toolchain?application_version=4.27).
```
