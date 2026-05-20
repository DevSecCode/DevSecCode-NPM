#!/usr/bin/env bash
# Build the slim `dsc` CLI binary for the current host platform.
#
# Usage:
#   bash npm-dist/scripts/build-binary.sh [target]
#
# `target` is one of darwin-arm64, darwin-x64, linux-x64, linux-arm64,
# win32-x64. If omitted, the script infers it from the host OS + arch.
#
# Output:
#   npm-dist/build/<target>/dsc           (Linux / macOS)
#   npm-dist/build/<target>/dsc.exe       (Windows)
#
# The CI matrix in .github/workflows/release-npm.yml calls this once per
# platform runner; local devs can also run it on their workstation to do
# an end-to-end smoke test before publishing.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ENGINE_DIR="$ROOT/engine"
NPM_DIST="$ROOT/npm-dist"

infer_target() {
  local os arch
  case "$(uname -s)" in
    Darwin)  os="darwin" ;;
    Linux)   os="linux" ;;
    MINGW*|MSYS*|CYGWIN*) os="win32" ;;
    *) echo "build-binary: unsupported host OS $(uname -s)" >&2; exit 1 ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) arch="x64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) echo "build-binary: unsupported host arch $(uname -m)" >&2; exit 1 ;;
  esac
  echo "${os}-${arch}"
}

TARGET="${1:-$(infer_target)}"
case "$TARGET" in
  darwin-arm64|darwin-x64|linux-x64|linux-arm64|win32-x64) ;;
  *)
    echo "build-binary: unknown target '$TARGET'" >&2
    echo "  supported: darwin-arm64 darwin-x64 linux-x64 linux-arm64 win32-x64" >&2
    exit 2
    ;;
esac

OUTDIR="$NPM_DIST/build/$TARGET"
mkdir -p "$OUTDIR"

cd "$ENGINE_DIR"

# Use the existing .venv if the developer set one up; otherwise expect
# `python3` to point at a 3.10+ interpreter with the engine + pyinstaller
# installed. CI explicitly does:
#   pip install -e engine/[dev]
#   pip install pyinstaller
PY="${PYTHON:-python3}"

if ! "$PY" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "build-binary: PyInstaller not installed in $($PY -c 'import sys; print(sys.executable)')" >&2
  echo "  fix: $PY -m pip install pyinstaller" >&2
  exit 1
fi

# Wipe previous build / dist so we don't ship stale artefacts.
rm -rf "$ENGINE_DIR/build" "$ENGINE_DIR/dist"

echo "==> Building dsc binary for $TARGET"
"$PY" -m PyInstaller dsc-cli.spec --noconfirm --clean

BIN_SRC="$ENGINE_DIR/dist/dsc"
BIN_NAME="dsc"
if [[ "$TARGET" == win32-* ]]; then
  BIN_SRC="$ENGINE_DIR/dist/dsc.exe"
  BIN_NAME="dsc.exe"
fi

if [[ ! -f "$BIN_SRC" ]]; then
  echo "build-binary: expected $BIN_SRC but it does not exist" >&2
  ls -la "$ENGINE_DIR/dist" >&2 || true
  exit 1
fi

cp "$BIN_SRC" "$OUTDIR/$BIN_NAME"
chmod +x "$OUTDIR/$BIN_NAME" || true

# Quick smoke test that --version works on the host (only when target == host).
HOST_TARGET="$(infer_target)"
if [[ "$TARGET" == "$HOST_TARGET" ]]; then
  echo "==> Smoke test: $OUTDIR/$BIN_NAME --version"
  "$OUTDIR/$BIN_NAME" --version
fi

echo "==> Built $OUTDIR/$BIN_NAME"
