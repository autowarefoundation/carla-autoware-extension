#!/usr/bin/env bash
# Repack the UE-tree libc++ (headers + x86_64 static libs + license/provenance)
# into ue5-libcxx.tar.gz for hosting as a GitHub Release asset. Run by a UE
# licensee on a machine with a UE source checkout; the CI image build then
# needs NO access to the (private) UE repository.
#
# EULA note: Engine/Source/ThirdParty/Unix/LibCxx is Third Party Software
# (Epic's own libcxx.tps), licensed UIUC/MIT dual (libcxx_License.txt) with
# Apache-2.0 WITH LLVM-exception headers; the UE EULA states third-party
# license terms take precedence on any inconsistency, and those licenses
# grant redistribution. Epic ships the build recipe (BuildLibCxx.sh) in the
# publicly downloadable native toolchain tarball. See docs/toolchain-image.md.
set -euo pipefail

UE_ROOT="${UE_ROOT:-$HOME/src/UnrealEngine}"
OUT_DIR="${OUT_DIR:-/tmp/ue5-libcxx}"
TRIPLE="x86_64-unknown-linux-gnu"

TP="$UE_ROOT/Engine/Source/ThirdParty"
[ -d "$TP/Unix/LibCxx/include" ] \
  || { echo "PREFLIGHT FAIL: $TP/Unix/LibCxx/include missing (set UE_ROOT to a UE checkout)"; exit 1; }
[ -f "$TP/Unix/LibCxx/lib/Unix/$TRIPLE/libc++.a" ] \
  || { echo "PREFLIGHT FAIL: libc++.a for $TRIPLE missing under $TP/Unix/LibCxx/lib"; exit 1; }
[ -f "$TP/Unix/LibCxx/libcxx.tps" ] \
  || { echo "PREFLIGHT FAIL: libcxx.tps missing (provenance metadata required)"; exit 1; }
[ -f "$TP/Licenses/libcxx_License.txt" ] \
  || { echo "PREFLIGHT FAIL: Licenses/libcxx_License.txt missing (license text required)"; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/Unix/LibCxx/lib/Unix" "$STAGE/Licenses"
cp -a "$TP/Unix/LibCxx/include"            "$STAGE/Unix/LibCxx/include"
cp -a "$TP/Unix/LibCxx/lib/Unix/$TRIPLE"   "$STAGE/Unix/LibCxx/lib/Unix/$TRIPLE"
cp -a "$TP/Unix/LibCxx/libcxx.tps"         "$STAGE/Unix/LibCxx/libcxx.tps"
cp -a "$TP/Licenses/libcxx_License.txt"    "$STAGE/Licenses/libcxx_License.txt"
cp -a "$TP/Licenses/libcxx_License.txt"    "$STAGE/Unix/LibCxx/libcxx_License.txt"
UE_SHA="$(git -C "$UE_ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
cat > "$STAGE/Unix/LibCxx/PROVENANCE.md" <<EOF
# Provenance

Repacked from an Unreal Engine source checkout (Engine/Source/ThirdParty/Unix/LibCxx,
UE commit $UE_SHA) by scripts/toolchain/make_libcxx_tarball.sh in
autowarefoundation/carla-autoware-extension. Contents are LLVM libc++/libc++abi
(headers: Apache-2.0 WITH LLVM-exception; license: libcxx_License.txt, UIUC/MIT dual),
built by Epic's publicly distributed BuildLibCxx.sh. x86_64 only.
EOF

mkdir -p "$OUT_DIR"
tar -C "$STAGE" -czf "$OUT_DIR/ue5-libcxx.tar.gz" Unix Licenses
(cd "$OUT_DIR" && sha256sum ue5-libcxx.tar.gz | tee ue5-libcxx.tar.gz.sha256)
echo "OK: wrote $OUT_DIR/ue5-libcxx.tar.gz"
