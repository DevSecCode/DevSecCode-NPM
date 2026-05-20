#!/usr/bin/env bash
# Stamp the canonical version from engine/src/dsc/version.py into the
# parent @devseccode/scanner package.json, including every optionalDependency
# pin so the parent always references the platform packages at the exact
# same version we're publishing.
#
# Called by the GHA `publish` job before `npm publish` runs in
# packages/scanner/.

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
NPM_DIST="$ROOT/npm-dist"
VERSION="$(bash "$NPM_DIST/scripts/version.sh")"

python3 - "$NPM_DIST/packages/scanner/package.json" "$VERSION" <<'PY'
import json, sys
path, version = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
data["version"] = version
deps = data.get("optionalDependencies") or {}
for k in list(deps):
    deps[k] = version
data["optionalDependencies"] = deps
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

echo "==> Stamped parent package.json with version=$VERSION"
