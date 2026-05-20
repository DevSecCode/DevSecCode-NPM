#!/usr/bin/env bash
# Copy the freshly-built binary into the platform's npm package and stamp
# both the parent and platform package.json files with the canonical
# version pulled from engine/src/dsc/version.py.
#
# Usage:
#   bash npm-dist/scripts/assemble-platform-pkg.sh <target>
#
# Where <target> is one of darwin-arm64, darwin-x64, linux-x64,
# linux-arm64, win32-x64. The binary must already exist at
# npm-dist/build/<target>/dsc (or dsc.exe).

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
NPM_DIST="$ROOT/npm-dist"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <target>" >&2
  exit 2
fi
TARGET="$1"
case "$TARGET" in
  darwin-arm64|darwin-x64|linux-x64|linux-arm64|win32-x64) ;;
  *) echo "assemble-platform-pkg: unknown target '$TARGET'" >&2; exit 2 ;;
esac

VERSION="$(bash "$NPM_DIST/scripts/version.sh")"

PKG_DIR="$NPM_DIST/packages/scanner-$TARGET"
if [[ ! -d "$PKG_DIR" ]]; then
  echo "assemble-platform-pkg: package dir $PKG_DIR not found" >&2
  exit 1
fi

BIN_NAME="dsc"
[[ "$TARGET" == win32-* ]] && BIN_NAME="dsc.exe"
BIN_SRC="$NPM_DIST/build/$TARGET/$BIN_NAME"
BIN_DST="$PKG_DIR/bin/$BIN_NAME"

if [[ ! -f "$BIN_SRC" ]]; then
  echo "assemble-platform-pkg: binary $BIN_SRC missing -- run build-binary.sh $TARGET first" >&2
  exit 1
fi

mkdir -p "$PKG_DIR/bin"
# Remove the gitkeep so it doesn't ship in the tarball.
rm -f "$PKG_DIR/bin/.gitkeep"
cp "$BIN_SRC" "$BIN_DST"
chmod +x "$BIN_DST" || true

# Re-stamp the version in this platform package.json. We do it with a Python
# one-liner instead of sed so we don't choke on different JSON formatting.
python3 - "$PKG_DIR/package.json" "$VERSION" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
data["version"] = version
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

echo "==> Assembled $PKG_DIR (version=$VERSION, binary=$BIN_DST)"
