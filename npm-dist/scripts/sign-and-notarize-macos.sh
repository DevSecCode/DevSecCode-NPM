#!/usr/bin/env bash
# Code-sign and notarize the macOS dsc binary so Gatekeeper accepts it on
# fresh Macs. Idempotent: skips with a warning if the required env vars
# are missing (see release-npm.yml -- the workflow step is wrapped in the
# same guard so local devs can still exercise the assemble path without
# an Apple Developer account).
#
# Required env:
#   APPLE_CERT_P12          -- base64-encoded Developer ID Application .p12
#   APPLE_CERT_PASSWORD     -- password for the .p12 above
#   APPLE_ID                -- Apple ID email
#   APPLE_TEAM_ID           -- 10-char team id
#   APPLE_APP_PASSWORD      -- app-specific password for notarytool

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "sign-and-notarize-macos: must run on macOS" >&2
  exit 1
fi

TARGET="${1:-}"
case "$TARGET" in
  darwin-arm64|darwin-x64) ;;
  *) echo "sign-and-notarize-macos: bad target '$TARGET'" >&2; exit 2 ;;
esac

for v in APPLE_CERT_P12 APPLE_CERT_PASSWORD APPLE_ID APPLE_TEAM_ID APPLE_APP_PASSWORD; do
  if [[ -z "${!v:-}" ]]; then
    echo "sign-and-notarize-macos: missing required env var $v; skipping" >&2
    exit 0
  fi
done

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BINARY="$ROOT/npm-dist/build/$TARGET/dsc"
if [[ ! -f "$BINARY" ]]; then
  echo "sign-and-notarize-macos: binary $BINARY missing" >&2
  exit 1
fi

KEYCHAIN="$RUNNER_TEMP/devseccode-signing.keychain-db"
KEYCHAIN_PASSWORD="$(uuidgen)"
CERT_P12="$RUNNER_TEMP/cert.p12"
ENTITLEMENTS="$RUNNER_TEMP/entitlements.plist"

cleanup() {
  security delete-keychain "$KEYCHAIN" 2>/dev/null || true
  rm -f "$CERT_P12" "$ENTITLEMENTS"
}
trap cleanup EXIT

echo "==> Importing Developer ID certificate"
echo "$APPLE_CERT_P12" | base64 --decode >"$CERT_P12"
security create-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security set-keychain-settings -lut 21600 "$KEYCHAIN"
security unlock-keychain -p "$KEYCHAIN_PASSWORD" "$KEYCHAIN"
security import "$CERT_P12" -P "$APPLE_CERT_PASSWORD" \
  -A -t cert -f pkcs12 -k "$KEYCHAIN"
security list-keychain -d user -s "$KEYCHAIN" \
  "$(security default-keychain | tr -d '\" ')"
security set-key-partition-list -S apple-tool:,apple: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN"

# Hardened-runtime entitlements. PyInstaller --onefile needs the
# allow-unsigned-executable-memory + allow-jit entitlements because the
# bootloader maps the embedded archive as executable at startup.
cat >"$ENTITLEMENTS" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>com.apple.security.cs.allow-jit</key><true/>
  <key>com.apple.security.cs.allow-unsigned-executable-memory</key><true/>
  <key>com.apple.security.cs.disable-library-validation</key><true/>
</dict>
</plist>
PLIST

SIGNING_IDENTITY="$(
  security find-identity -v -p codesigning "$KEYCHAIN" \
    | awk -F'"' '/Developer ID Application/ { print $2; exit }'
)"
if [[ -z "$SIGNING_IDENTITY" ]]; then
  echo "sign-and-notarize-macos: no Developer ID Application identity in keychain" >&2
  security find-identity -v "$KEYCHAIN" >&2 || true
  exit 1
fi

echo "==> Codesign $BINARY with $SIGNING_IDENTITY"
codesign --force --timestamp --options runtime \
  --entitlements "$ENTITLEMENTS" \
  --sign "$SIGNING_IDENTITY" \
  "$BINARY"

codesign --verify --verbose=4 "$BINARY"

echo "==> Submitting to notarytool"
ZIP="$RUNNER_TEMP/dsc-$TARGET.zip"
ditto -c -k --keepParent "$BINARY" "$ZIP"

xcrun notarytool submit "$ZIP" \
  --apple-id "$APPLE_ID" \
  --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_PASSWORD" \
  --wait

# Stapling note: Apple's `stapler` only works on container formats
# (.app bundles, .pkg installers, .dmg images, signed zip archives).
# A standalone Mach-O binary cannot have a notarization ticket stapled
# to it -- `stapler staple` exits with Error 73 + "does not have a
# ticket stapled to it" for bare binaries. That's fine. Apple records
# the notarization ticket server-side keyed off the binary's hash, so
# Gatekeeper validates it online on first launch when needed.
#
# In practice, npm extraction does not set the com.apple.quarantine
# xattr on tarball contents, so Gatekeeper doesn't even get invoked
# when users run `devseccode` via `npm install`. The notarization is a
# belt-and-suspenders defense for the rare case a user downloads the
# tarball through a quarantining channel (Safari, etc.).
echo "==> Notarized $BINARY"
echo "    (no staple -- bare binaries cannot be stapled; Apple keeps the"
echo "    ticket server-side for online Gatekeeper validation)"
