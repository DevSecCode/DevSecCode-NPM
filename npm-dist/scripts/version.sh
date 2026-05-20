#!/usr/bin/env bash
# Single source of truth: engine/src/dsc/version.py.
# Echoes the bare semver string, no leading "v".
#
# Usage:
#   . scripts/version.sh
#   echo "$DSC_VERSION"
#
# Or as a one-shot:
#   VERSION=$(bash scripts/version.sh)

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION_PY="$ROOT/engine/src/dsc/version.py"

if [[ ! -f "$VERSION_PY" ]]; then
  echo "version.sh: cannot find $VERSION_PY" >&2
  exit 1
fi

# Match: __version__ = "X.Y.Z"  (any quotes, any spacing)
DSC_VERSION="$(
  awk '/^__version__/ { gsub(/["'\'']/, "", $3); print $3; exit }' "$VERSION_PY"
)"

if [[ -z "${DSC_VERSION:-}" ]]; then
  echo "version.sh: failed to parse __version__ from $VERSION_PY" >&2
  exit 1
fi

export DSC_VERSION
echo "$DSC_VERSION"
