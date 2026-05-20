#!/usr/bin/env bash
# Publish every assembled platform package to npm, then the parent.
#
# All packages publish with --access public. The package remains proprietary
# via LICENSE, but public npm access keeps `npx @devseccode/scanner scan .`
# frictionless for first-time users.
#
# CRITICAL: the platform packages must be on the registry BEFORE the
# parent, otherwise the parent's optionalDependencies fail to resolve on
# first npx invocation.
#
# Requires NODE_AUTH_TOKEN (or `npm login`) to be configured. CI sets it
# via the npm setup-node action.
#
# Usage:
#   bash npm-dist/scripts/publish-all.sh             # all platforms + parent
#   bash npm-dist/scripts/publish-all.sh --dry-run   # show what would publish

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
NPM_DIST="$ROOT/npm-dist"

DRY_RUN_FLAGS=()
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN_FLAGS=("--dry-run")
fi

publish_dir() {
  local dir="$1"
  if [[ ! -f "$dir/package.json" ]]; then
    echo "publish-all: $dir is missing package.json -- skip" >&2
    return 0
  fi
  echo "==> npm publish $dir"
  ( cd "$dir" && npm publish --access public "${DRY_RUN_FLAGS[@]}" )
}

# Platform packages first.
for target in darwin-arm64 darwin-x64 linux-x64 linux-arm64 win32-x64; do
  pkg="$NPM_DIST/packages/scanner-$target"
  # Only publish if the binary is actually present -- protects against
  # publishing an empty wrapper if one build leg failed.
  bin_name="dsc"
  [[ "$target" == win32-* ]] && bin_name="dsc.exe"
  if [[ ! -f "$pkg/bin/$bin_name" ]]; then
    echo "publish-all: $pkg has no binary; skipping" >&2
    continue
  fi
  publish_dir "$pkg"
done

# Then the parent so optionalDependencies always resolve.
publish_dir "$NPM_DIST/packages/scanner"

echo "==> Done."
