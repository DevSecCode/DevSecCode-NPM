# npm distribution -- `@devseccode/scanner`

This directory holds the npm side of the public DevSecCode CLI. Users install
one package (`@devseccode/scanner`), run `devseccode hunt .`, and npm
auto-resolves the right platform-specific binary from a sibling
`optionalDependencies` entry.
Architecture is the same one esbuild, swc, biome, and ruff use.

The package is public on npm for frictionless `npx @devseccode/scanner hunt .`.
It remains proprietary under the EULA included in each package.

```
npm-dist/
├── packages/
│   ├── scanner/                    ← @devseccode/scanner (parent JS shim)
│   ├── scanner-darwin-arm64/       ← @devseccode/scanner-darwin-arm64
│   ├── scanner-linux-x64/
│   ├── scanner-linux-arm64/
│   └── scanner-win32-x64/
└── scripts/
    ├── version.sh              ← echoes engine/src/dsc/version.py
    ├── build-binary.sh         ← runs PyInstaller, lands binary in build/
    ├── assemble-platform-pkg.sh← stamps version + copies binary into package
    ├── stamp-parent-version.sh ← stamps parent + optionalDependencies pins
    ├── sign-and-notarize-macos.sh
    ├── publish-all.sh          ← platform packages first, then parent
    ├── test-local-install.sh   ← pre-publish: pack + install + run, all local
    └── test-with-verdaccio.sh  ← pre-publish: full registry simulation
```

## How a Release Flows

1. Bump `engine/src/dsc/version.py`.
2. Commit + push, then tag `npm-vX.Y.Z` where `X.Y.Z` matches the engine
   version exactly.
3. `.github/workflows/release-npm.yml` builds each platform package, signs
   macOS when Apple secrets are configured, and runs `publish-all.sh`.
4. `publish-all.sh` publishes platform packages first, parent last. Order
   matters because the parent depends on the platform packages via
   `optionalDependencies`.

## Building Locally

```bash
python3.12 -m venv engine/.venv
source engine/.venv/bin/activate
pip install -e "engine/[dev]"
pip install pyinstaller

bash npm-dist/scripts/build-binary.sh
bash npm-dist/scripts/assemble-platform-pkg.sh darwin-arm64
bash npm-dist/scripts/test-local-install.sh
```

## Things to Know

- **No Python on the user's machine.** PyInstaller bundles a CPython runtime
  and the public CLI dependencies into the binary.
- **Public rule subset only.** The npm build bundles `engine/public_rulepacks`
  as runtime `rulepacks/`; it does not bundle compliance seeds or OSCAL
  reference data.
- **No postinstall.** Install is file extraction only. No download step, shell
  hook, or node-gyp.
- **Alpine / musl Linux is not supported.** Use a glibc image such as Debian
  or Ubuntu in CI.

See `DISTRIBUTION_PLAN.md` at the repo root for the original design doc.
