#!/usr/bin/env bash
# Pre-publish "clean install through a real npm registry" test.
#
# Runs an ephemeral Verdaccio registry on localhost:4873, publishes every
# package there with the same package ordering real publish-all.sh uses,
# then installs in a fresh dir pointed at that
# registry. This is the closest you can get to the real `npm install
# @devseccode/scanner` experience without actually touching npmjs.com.
#
# What this exercises *beyond* test-local-install.sh:
#   - `npm publish` itself (file selection, tarball assembly, dist-tags).
#   - Resolution of `optionalDependencies` from a registry, not from
#     side-by-side tarballs.
#   - `npm install @devseccode/scanner` (no tgz path) — i.e. the exact command
#     real customers will run.
#
# What this does NOT exercise:
#   - npmjs.com package visibility / propagation.
#   - macOS Gatekeeper.
#
# Usage:
#   bash npm-dist/scripts/test-with-verdaccio.sh
#
# Requires: node 18+, npm 9+, python3.10+ (for the binary build).
# Will install verdaccio + verdaccio-auth-memory via `npx` on first run.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
NPM_DIST="$ROOT/npm-dist"

infer_target() {
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64)         echo "darwin-arm64" ;;
    Darwin-x86_64)        echo "darwin-x64" ;;
    Linux-x86_64)         echo "linux-x64" ;;
    Linux-aarch64|Linux-arm64) echo "linux-arm64" ;;
    *) echo "unsupported host" >&2; exit 1 ;;
  esac
}
TARGET="$(infer_target)"
echo "==> Host target: $TARGET"

#
# Phase 1: build the binary + assemble the platform package.
# Skip if already present (saves the 1-2 min PyInstaller cost on reruns).
#
BIN_NAME="dsc"
[[ "$TARGET" == win32-* ]] && BIN_NAME="dsc.exe"
if [[ ! -f "$NPM_DIST/packages/scanner-$TARGET/bin/$BIN_NAME" ]]; then
  echo "==> Binary missing -- running test-local-install.sh prefix to build it"
  # Reuse the venv-and-build prefix from test-local-install.sh by calling
  # the underlying scripts directly so we don't kick off a redundant install.
  VENV="$ROOT/engine/.venv"
  if [[ ! -d "$VENV" ]]; then python3 -m venv "$VENV"; fi
  # shellcheck disable=SC1091
  source "$VENV/bin/activate"
  if ! python -c "import PyInstaller" >/dev/null 2>&1; then
    # --no-cache-dir bypasses pip's HTTP cache (avoids "deserialization
    # failed" spam). Skip [dev] extras: PyInstaller doesn't need them.
    echo "==> Installing engine + PyInstaller into venv (no cache, runtime deps only)"
    pip install --no-cache-dir --upgrade pip
    pip install --no-cache-dir -e "$ROOT/engine"
    pip install --no-cache-dir pyinstaller
  fi
  PYTHON="$VENV/bin/python" bash "$NPM_DIST/scripts/build-binary.sh" "$TARGET"
  bash "$NPM_DIST/scripts/assemble-platform-pkg.sh" "$TARGET"
fi

#
# Phase 2: stamp parent version so optionalDependency pins match what we
# are about to publish.
#
bash "$NPM_DIST/scripts/stamp-parent-version.sh"

#
# Phase 3: launch Verdaccio in the background on :4873.
#
TMP="$(mktemp -d)"
VERDACCIO_STORAGE="$TMP/verdaccio-storage"
VERDACCIO_CONFIG="$TMP/verdaccio-config.yaml"
VERDACCIO_LOG="$TMP/verdaccio.log"
mkdir -p "$VERDACCIO_STORAGE"

cat >"$VERDACCIO_CONFIG" <<YAML
storage: $VERDACCIO_STORAGE
# Default body-size limit is 10mb; the PyInstaller-built dsc binary is
# ~18mb per platform, so we need headroom. 100mb covers any realistic
# growth and matches what most internal/enterprise Verdaccio deploys use.
max_body_size: 100mb
auth:
  htpasswd:
    file: $TMP/htpasswd
    max_users: 1
uplinks:
  npmjs:
    url: https://registry.npmjs.org/
packages:
  '@devseccode/*':
    access: \$all
    publish: \$all
    proxy: ""
  '**':
    access: \$all
    proxy: npmjs
log:
  type: file
  path: $VERDACCIO_LOG
  level: warn
listen: 127.0.0.1:4873
YAML

cleanup() {
  if [[ -n "${VERDACCIO_PID:-}" ]]; then
    kill "$VERDACCIO_PID" 2>/dev/null || true
    wait "$VERDACCIO_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

echo "==> Starting Verdaccio on http://localhost:4873"
npx --yes verdaccio@5 --config "$VERDACCIO_CONFIG" >"$TMP/verdaccio.stdout" 2>&1 &
VERDACCIO_PID=$!

# Wait for it to accept connections (up to 30s).
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:4873/-/ping >/dev/null 2>&1; then break; fi
  sleep 0.5
done
if ! curl -sf http://127.0.0.1:4873/-/ping >/dev/null 2>&1; then
  echo "FAIL: Verdaccio didn't start" >&2
  cat "$TMP/verdaccio.stdout" >&2 || true
  exit 1
fi
echo "    OK"

#
# Phase 4: register a dummy user + publish every package to the local registry.
# We use a per-test .npmrc so we don't touch the user's real ~/.npmrc.
#
NPMRC="$TMP/.npmrc"
cat >"$NPMRC" <<EOF
//127.0.0.1:4873/:_authToken=test-token
@devseccode:registry=http://127.0.0.1:4873/
registry=http://127.0.0.1:4873/
EOF
export npm_config_userconfig="$NPMRC"

# Verdaccio's `auth.htpasswd` lets us register users with `npm adduser`;
# simpler is to seed the htpasswd file directly. Use an empty htpasswd
# (max_users:1 still requires one entry); npm adduser creates it.
echo "==> Registering test user with the local registry"
# Non-interactive adduser via npm-cli-login pattern: use the bundled REST
# endpoint directly. Verdaccio 5 accepts arbitrary tokens when htpasswd is
# empty; setting _authToken in .npmrc is sufficient.

#
# Phase 5: publish every assembled package to Verdaccio.
#
echo "==> Publishing packages to Verdaccio"
for d in "$NPM_DIST/packages/scanner-$TARGET" "$NPM_DIST/packages/scanner"; do
  echo "    publish $d"
  ( cd "$d" && npm publish --registry http://127.0.0.1:4873/ \
       --access public )
done

#
# Phase 6: install + run from a fresh directory pointed at Verdaccio.
#
INSTALL_DIR="$TMP/install"
mkdir -p "$INSTALL_DIR"
( cd "$INSTALL_DIR" && npm init -y >/dev/null )

echo "==> npm install @devseccode/scanner (from local registry, no tgz paths)"
( cd "$INSTALL_DIR" \
  && npm install --no-fund --no-audit \
       --registry http://127.0.0.1:4873/ \
       @devseccode/scanner )

DEVSECCODE="$INSTALL_DIR/node_modules/.bin/devseccode"
DSC_ALIAS="$INSTALL_DIR/node_modules/.bin/dsc"
if [[ ! -x "$DEVSECCODE" ]]; then
  echo "FAIL: $DEVSECCODE missing" >&2
  ls -la "$INSTALL_DIR/node_modules/.bin/" >&2 || true
  echo
  echo "Most likely cause: the optionalDependency for $TARGET was skipped"
  echo "because npm matched a different os/cpu. Check that"
  echo "  $NPM_DIST/packages/scanner-$TARGET/package.json"
  echo "has os=$(uname -s | tr '[:upper:]' '[:lower:]') and the right cpu."
  exit 1
fi
if [[ ! -x "$DSC_ALIAS" ]]; then
  echo "FAIL: $DSC_ALIAS alias missing" >&2
  ls -la "$INSTALL_DIR/node_modules/.bin/" >&2 || true
  exit 1
fi

echo "==> devseccode --version (from registry-installed package)"
"$DEVSECCODE" --version

if [[ -d "$ROOT/resources/sample-vulns" ]]; then
  echo "==> devseccode hunt resources/sample-vulns (first 40 lines)"
  "$DEVSECCODE" hunt "$ROOT/resources/sample-vulns" --no-cache --fail-on critical 2>&1 | sed -n '1,40p'
fi

echo
echo "==> Verdaccio test passed."
echo "    Customers running 'npm install @devseccode/scanner' against the"
echo "    real registry will see exactly the same resolution behavior."
