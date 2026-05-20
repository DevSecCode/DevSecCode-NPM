#!/usr/bin/env bash
# Vendor the pinned OpenGrep binary for the host platform.
# Run as part of bootstrap.sh and CI.
set -euo pipefail

VERSION="v1.20.0"

cd "$(dirname "$0")"
mkdir -p bin

TARGET="bin/opengrep"

case "$(uname -s)/$(uname -m)" in
  "Darwin/arm64")  ASSET="opengrep_osx_arm64" ;;
  "Darwin/x86_64") ASSET="opengrep_osx_x86" ;;
  "Linux/x86_64")  ASSET="opengrep_manylinux_x86" ;;
  "Linux/aarch64") ASSET="opengrep_manylinux_aarch64" ;;
  MINGW*/x86_64 | MSYS*/x86_64 | CYGWIN*/x86_64)
    ASSET="opengrep_windows_x86.exe"
    TARGET="bin/opengrep.exe"
    ;;
  *)
    echo "unsupported platform: $(uname -sm)" >&2
    exit 1
    ;;
esac

URL="https://github.com/opengrep/opengrep/releases/download/${VERSION}/${ASSET}"

if [[ -x "$TARGET" ]]; then
  installed_version=$("$TARGET" --version 2>/dev/null | head -1 || true)
  if [[ "${installed_version}" == "${VERSION#v}" ]]; then
    echo "OpenGrep ${VERSION} already installed at $TARGET"
    exit 0
  fi
  echo "replacing existing OpenGrep ($installed_version -> ${VERSION})"
fi

echo "downloading $URL"
curl -sL --fail -o "$TARGET" "$URL"
chmod +x "$TARGET"

echo "verifying..."
"$TARGET" --version
echo "OpenGrep $VERSION installed at $TARGET"
