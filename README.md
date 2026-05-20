# DevSecCode -- npm distribution

Source repo for the public `@devseccode/scanner` npm package: a local-first
gamified security CLI intended as the low-friction entry point for DevSecCode.
End users install one npm package and run `devseccode hunt .` with no Python
toolchain and no npm login.

The npm package is intentionally smaller than DevSecCode IDE. It ships a
focused public rule subset and basic terminal/JSON/SARIF/JUnit outputs.
The full IDE keeps the complete rule library, compliance mapping, SBOM,
evidence packages, POA&M, git-history analysis, and remediation workflows.

## For Users

```bash
npx @devseccode/scanner hunt .                             # one-shot
npm install -g @devseccode/scanner && devseccode --help    # global
devseccode scan . --format sarif --output devseccode.sarif
```

Supported platforms in v0.4.1: macOS Apple Silicon, Linux (x64 + arm64),
Windows x64. Intel Mac (`darwin-x64`) is not built because GitHub retired
the macos-13 hosted runner. See
[`npm-dist/packages/scanner/README.md`](./npm-dist/packages/scanner/README.md) for
the published landing page.

## Repo Layout

```
engine/         Python source -- built into per-platform binaries by PyInstaller
npm-dist/       npm packaging -- parent shim + platform packages + scripts
.github/        Release workflow (.github/workflows/release-npm.yml)
resources/
  sample-vulns/ Tiny fixtures used by pre-publish test scripts
DISTRIBUTION_PLAN.md
LICENSE.txt
```

## How a Release Flows

1. Bump `engine/src/dsc/version.py`.
2. Tag `npm-vX.Y.Z` where the version matches exactly.
3. `release-npm.yml` builds one binary per platform via PyInstaller,
   optionally codesigns + notarizes macOS binaries, then publishes the
   platform packages first and parent `@devseccode/scanner` last.

Detailed runbook: [`npm-dist/README.md`](./npm-dist/README.md).

## License

Proprietary -- All Rights Reserved. See [LICENSE.txt](./LICENSE.txt) for
the full End User License Agreement.
