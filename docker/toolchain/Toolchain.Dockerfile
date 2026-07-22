# Slim UE5 toolchain image for building libcarla-autoware-extension.so in CI.
# Contains ONLY third-party OSS: the Epic-distributed clang/sysroot toolchain
# (Engine/Extras/ThirdPartyNotUE — explicitly "not itself Licensed Technology"
# per the UE EULA) and the UE-tree libc++ bundle (Third Party Software whose
# own license grants redistribution). No Engine Code, no Engine Tools, no
# OpenSSL, no conda. See LICENSES.md (copied into the image) and
# docs/toolchain-image.md for the full EULA analysis and rebuild procedure.
FROM ubuntu:24.04

# noble's cmake is 3.28.3 (>= the extension's 3.20 floor) — no Kitware download.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ninja-build cmake git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG TOOLCHAIN_VERSION=v23_clang-18.1.0-rockylinux8
ARG TOOLCHAIN_SHA256=048ad147d66e45b9dcfcbc986770f8df1ccbf94de11480877e72d2b3b1b48087
# Epic CDN, publicly accessible without authentication or EULA acceptance.
# Extract EVERYTHING and keep share/licenses/ + build/ (full corresponding
# sources for the GPL/LGPL sysroot components) — stripping them would break
# the redistribution-compliance conditions this image is published under.
RUN mkdir -p /unreal-engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64 && \
    curl -fL -o /tmp/toolchain.tar.gz \
      "https://cdn.unrealengine.com/Toolchain_Linux/native-linux-${TOOLCHAIN_VERSION}.tar.gz" && \
    echo "${TOOLCHAIN_SHA256}  /tmp/toolchain.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/toolchain.tar.gz \
      -C /unreal-engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/ && \
    rm /tmp/toolchain.tar.gz

ARG LIBCXX_URL=https://github.com/autowarefoundation/carla-autoware-extension/releases/download/ue5-libcxx-v1/ue5-libcxx.tar.gz
ARG LIBCXX_SHA256=9c454632d46ba5085904368c5ee4347da2b1d277e9c74cfbf3a7a0072c96c1fc
# LibCxx bundle repacked by scripts/toolchain/make_libcxx_tarball.sh
# (license text, Epic TPS metadata, and PROVENANCE.md ride inside).
RUN mkdir -p /unreal-engine/Engine/Source/ThirdParty && \
    curl -fL -o /tmp/ue5-libcxx.tar.gz "${LIBCXX_URL}" && \
    echo "${LIBCXX_SHA256}  /tmp/ue5-libcxx.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/ue5-libcxx.tar.gz -C /unreal-engine/Engine/Source/ThirdParty/ && \
    rm /tmp/ue5-libcxx.tar.gz

# The bundled clang was built on Rocky Linux 8; its linker scripts reference
# RHEL-style absolute paths (/lib64/, /usr/lib64/). On Ubuntu these live under
# /lib/x86_64-linux-gnu/ and /usr/lib/x86_64-linux-gnu/ — symlink both styles.
RUN for f in /lib/x86_64-linux-gnu/*.so* /lib/x86_64-linux-gnu/*.a; do \
      [ -e "$f" ] && ln -sf "$f" /lib64/"$(basename "$f")" 2>/dev/null; \
    done; \
    mkdir -p /usr/lib64 && \
    for f in /usr/lib/x86_64-linux-gnu/*.so* /usr/lib/x86_64-linux-gnu/*.a /usr/lib/x86_64-linux-gnu/*.o; do \
      [ -e "$f" ] && ln -sf "$f" /usr/lib64/"$(basename "$f")" 2>/dev/null; \
    done; \
    true

COPY docker/toolchain/LICENSES.md /LICENSES.md

ENV CARLA_UNREAL_ENGINE_PATH=/unreal-engine

LABEL org.opencontainers.image.source="https://github.com/autowarefoundation/carla-autoware-extension" \
      org.opencontainers.image.description="Slim UE5 clang/libc++ toolchain (third-party OSS only) for building libcarla-autoware-extension.so" \
      org.opencontainers.image.licenses="Apache-2.0 AND NCSA AND MIT AND GPL-3.0-or-later AND LGPL-2.1-or-later"
