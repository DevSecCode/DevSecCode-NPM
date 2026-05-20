#!/usr/bin/env bash
# Pre-publish "clean install as a new user" test.
#
# What this exercises:
#   1. PyInstaller produces a working native binary for the host platform.
#   2. assemble-platform-pkg.sh stamps the right version and stages the binary.
#   3. `npm pack` produces tarballs whose contents match the published files[].
#   4. `npm install <tgz>` into a clean temp dir resolves the parent's
#      optionalDependency entry to the host-platform sibling tarball.
#   5. `node_modules/.bin/devseccode` runs and produces real scanner output.
#
# What this does NOT exercise:
#   - Network registry resolution. The parent's optionalDependencies entries
#     reference npm-registered versions, but with both tarballs side by side
#     in the install command, npm satisfies them from the local tgz.
#   - macOS notarization / Gatekeeper. Local pack + install never touches
#     codesign. For Gatekeeper testing, install a notarized binary on a
#     fresh Mac.
#   - True registry-side resolution -- use test-with-verdaccio.sh for that.
#
# Usage:
#   bash npm-dist/scripts/test-local-install.sh
#
# Requires: python3.10+ with venv, npm 8+, ~2 min on first run (PyInstaller).

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
NPM_DIST="$ROOT/npm-dist"
ENGINE_DIR="$ROOT/engine"

infer_target() {
  local os arch
  case "$(uname -s)" in
    Darwin)  os="darwin" ;;
    Linux)   os="linux" ;;
    *) echo "test-local-install: unsupported host OS" >&2; exit 1 ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) arch="x64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) echo "test-local-install: unsupported host arch" >&2; exit 1 ;;
  esac
  echo "${os}-${arch}"
}

TARGET="$(infer_target)"
echo "==> Host target: $TARGET"

#
# Phase 1: build the binary if it doesn't already exist. Pass --rebuild
# to force a fresh PyInstaller run.
#
BIN_NAME="dsc"
[[ "$TARGET" == win32-* ]] && BIN_NAME="dsc.exe"
STAGED_BIN="$NPM_DIST/packages/scanner-$TARGET/bin/$BIN_NAME"
FORCE_REBUILD="${REBUILD:-0}"
if [[ "${1:-}" == "--rebuild" ]]; then FORCE_REBUILD=1; fi

if [[ ! -f "$STAGED_BIN" || "$FORCE_REBUILD" == "1" ]]; then
  VENV="$ENGINE_DIR/.venv"
  if [[ ! -d "$VENV" ]]; then
    echo "==> Creating $VENV"
    python3 -m venv "$VENV"
  fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  if ! python -c "import PyInstaller" >/dev/null 2>&1; then
    # --no-cache-dir bypasses the pip HTTP cache, which on this machine is
    # throwing "Cache entry deserialization failed" warnings (a known pip
    # symptom after a pip version change -- harmless but spammy and slow).
    # Run `pip cache purge` once outside this script if you want a clean
    # cache for other projects.
    #
    # Skipping the [dev] extras: PyInstaller doesn't need pytest, ruff,
    # mypy, black, twine, pre-commit, or jsonschema to build the binary.
    # Roughly 3x faster install.
    echo "==> Installing engine + PyInstaller into venv (~30-60s, no cache, runtime deps only)"
    pip install --no-cache-dir --upgrade pip
    pip install --no-cache-dir -e "$ENGINE_DIR"
    pip install --no-cache-dir pyinstaller
  fi

  echo "==> Building dsc binary (PyInstaller, ~1-2 min)"
  PYTHON="$VENV/bin/python" bash "$NPM_DIST/scripts/build-binary.sh" "$TARGET"

  echo "==> Assembling scanner-$TARGET package"
  bash "$NPM_DIST/scripts/assemble-platform-pkg.sh" "$TARGET"
else
  echo "==> Reusing existing binary at $STAGED_BIN"
  echo "    (pass --rebuild or set REBUILD=1 to force a fresh PyInstaller run)"
fi

#
# Phase 3: pack + install into a throwaway directory as if you were a user.
#
echo "==> Packing parent + scanner-$TARGET tarballs"
PACK_DIR="$(mktemp -d)"
trap 'rm -rf "$PACK_DIR"' EXIT
( cd "$NPM_DIST/packages/scanner"            && npm pack --pack-destination "$PACK_DIR" >/dev/null )
( cd "$NPM_DIST/packages/scanner-$TARGET"    && npm pack --pack-destination "$PACK_DIR" >/dev/null )
ls -la "$PACK_DIR"/*.tgz

PARENT_TGZ="$(ls "$PACK_DIR"/devseccode-scanner-[0-9]*.tgz | head -n1)"
PLATFORM_TGZ="$(ls "$PACK_DIR"/devseccode-scanner-"$TARGET"-*.tgz | head -n1)"

INSTALL_DIR="$PACK_DIR/install"
mkdir -p "$INSTALL_DIR"
( cd "$INSTALL_DIR" && npm init -y >/dev/null )

echo "==> npm install in $INSTALL_DIR"
( cd "$INSTALL_DIR" && npm install --no-fund --no-audit "$PLATFORM_TGZ" "$PARENT_TGZ" )

DEVSECCODE="$INSTALL_DIR/node_modules/.bin/devseccode"
DSC_ALIAS="$INSTALL_DIR/node_modules/.bin/dsc"
echo "==> Resolved devseccode: $DEVSECCODE"
if [[ ! -x "$DEVSECCODE" ]]; then
  echo "FAIL: $DEVSECCODE missing or not executable"
  ls -la "$INSTALL_DIR/node_modules/.bin/" || true
  exit 1
fi
if [[ ! -x "$DSC_ALIAS" ]]; then
  echo "FAIL: $DSC_ALIAS alias missing or not executable"
  ls -la "$INSTALL_DIR/node_modules/.bin/" || true
  exit 1
fi

#
# Phase 4: actually run the scanner.
#
echo "==> devseccode --version"
"$DEVSECCODE" --version

if [[ -d "$ROOT/resources/sample-vulns" ]]; then
  echo "==> devseccode hunt resources/sample-vulns (first 40 lines)"
  "$DEVSECCODE" hunt "$ROOT/resources/sample-vulns" --no-cache --fail-on critical 2>&1 | sed -n '1,40p'
fi

echo
echo "==> All phases passed. The local-install test simulates the user flow:"
echo "      npm install @devseccode/scanner   (resolves both tarballs)"
echo "      devseccode --version"
echo "    For the closer-to-real registry test, run test-with-verdaccio.sh next."
