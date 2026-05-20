# Testing the npm distribution

Two distinct "clean install as a new user" tests exist for this repo, one
**before** you publish and one **after**. They answer different questions
and you should run both.

| Phase | Question it answers | Script |
|---|---|---|
| Pre-publish, local tarballs | Does the parent shim find the platform binary when both packages are installed side by side? | `test-local-install.sh` |
| Pre-publish, local registry | Does `npm install @devseccode/scanner` (no tarball path) work end-to-end through a real registry? | `test-with-verdaccio.sh` |
| Post-publish, real user | Does it actually work for someone who's never touched this code, with no npm auth? | (manual, see below) |

---

## Pre-publish, fast path: `test-local-install.sh`

The 90% test. Run this every time you touch the shim, the build, the
PyInstaller spec, or any package metadata.

```bash
bash npm-dist/scripts/test-local-install.sh
```

What happens (in order):

1. If `engine/.venv` doesn't exist, creates one and installs the engine
   in editable mode plus PyInstaller.
2. Runs `npm-dist/scripts/build-binary.sh` for the host platform
   (~1–2 min on first run; PyInstaller caches make reruns under 30s).
3. Runs `npm-dist/scripts/assemble-platform-pkg.sh` so the binary lands
   under `npm-dist/packages/scanner-<target>/bin/`.
4. `npm pack` against the parent and the host-platform package.
5. `npm init -y` in a throwaway temp dir.
6. `npm install <platform.tgz> <parent.tgz>` — install both tarballs
   into that fresh `node_modules`.
7. Runs `node_modules/.bin/devseccode --version` and a hunt against
   `resources/sample-vulns/`.

Limit: this does **not** exercise registry resolution. Because both tarballs
are present at install time, npm satisfies the platform dependency from the
local `.tgz` rather than the registry. For that, use the Verdaccio test.

## Pre-publish, full path: `test-with-verdaccio.sh`

Spins up a [Verdaccio](https://verdaccio.org/) registry on
`localhost:4873`, publishes everything to it, then installs from it with
no tarball paths — exactly the command a customer will run.

```bash
bash npm-dist/scripts/test-with-verdaccio.sh
```

What happens:

1. Builds + assembles the host-platform binary if missing (same as
   `test-local-install.sh`).
2. Stamps the parent `package.json` so the `optionalDependencies` pins
   match the version we're about to publish.
3. Boots Verdaccio in the background via `npx verdaccio@5`. First run
   downloads ~30 MB; subsequent runs are instant.
4. Publishes the platform package to Verdaccio first, then the parent
   second — same ordering `publish-all.sh` enforces against real npm.
5. In a fresh temp dir, runs the actual customer-facing command:
   `npm install --registry http://127.0.0.1:4873/ @devseccode/scanner`.
6. Verifies the dep resolved to the correct platform sibling, then runs
   `devseccode --version` and a hunt.

If this passes, you've validated everything except npmjs.com's public
registry path.

Differences from real publish:

- Verdaccio is local, so it does not prove npmjs.com propagation or package
  visibility.
- No macOS Gatekeeper / notarization round trip.

## Post-publish: actual new-user test

After `git push origin npm-vX.Y.Z` succeeds and the release workflow shows
green, do this on a machine where you have **never** authenticated to npm --
ideally a fresh VM, a clean Docker container, or at minimum a different user
account on your laptop. The public package should install without login.

```bash
# In a brand new directory, with no ~/.npmrc:
mkdir /tmp/dsc-realworld && cd /tmp/dsc-realworld

# 1. Try npx -- the canonical first-time invocation.
npx @devseccode/scanner hunt .

# 2. And the global install path.
npm install -g @devseccode/scanner
devseccode --version
devseccode hunt /path/to/a/real/project
devseccode scan /path/to/a/real/project --format terminal

# 3. (macOS only) Verify the binary is signed by the right entity.
#    NOTE: `spctl --assess --type execute` rejects bare CLI binaries
#    with "does not seem to be an app" -- that's an spctl semantic,
#    not a security failure. The right check is `codesign`:
codesign -dvvv "$(which devseccode)" 2>&1 | grep -E 'Authority|TeamIdentifier'
# Expect:
#   Authority=Developer ID Application: Summit Wanderlust, LLC (S4X2KJ3UYL)
#   Authority=Developer ID Certification Authority
#   Authority=Apple Root CA
#   TeamIdentifier=S4X2KJ3UYL
#
# Notarization is recorded server-side; bare Mach-O binaries cannot be
# stapled. npm install does not set the com.apple.quarantine xattr, so
# Gatekeeper does not get invoked on first launch via npm.

# 4. Check install size on disk.
du -sh "$(npm root -g)/@devseccode/"
# Expect: <30 MB (one platform binary, others skipped via os/cpu)

# 6. Confirm only the right platform package was installed.
ls "$(npm root -g)/@devseccode/"
# Expect: cli, cli-<your-platform>  (and nothing else)
```

Failure signals that map to common bugs:

| Symptom | Likely cause |
|---|---|
| `npm install` fails with 403 | The package is not public on npm or the registry is pointed at a private mirror. Check npm package visibility and `.npmrc`. |
| `devseccode: command not found` after global install | npm `bin` directory not on `PATH`. Run `npm prefix -g` and add `<that>/bin` to `PATH`. |
| `devseccode --version` says "no prebuilt binary for ..." | The customer's platform/arch pair isn't in `optionalDependencies` or its sub-package wasn't published. |
| `devseccode: cannot be opened because the developer cannot be verified` (macOS) | Binary wasn't notarized. Codesigning script didn't run or `APPLE_DEVELOPER_ID_APPLICATION_CERT_P12` wasn't set in CI. |
| Installs install size > 100 MB | All platform binaries got installed instead of just one. Check that each platform `package.json` has the correct `os` / `cpu` fields. |

## Cleaning up between runs

```bash
# Delete the host binary so the next test rebuilds from scratch:
rm -f npm-dist/packages/scanner-darwin-arm64/bin/dsc           # adjust target
rm -rf npm-dist/build/

# Wipe the venv if you want a from-scratch PyInstaller run:
rm -rf engine/.venv
```

## Continuous integration

The CI matrix in `.github/workflows/release-npm.yml` runs the build leg
on every platform on `npm-v*` tag pushes, but there is **no automatic
pre-publish smoke test** in that workflow today. If you want one, the
cheapest move is to add a `workflow_dispatch` trigger to the same file
that runs `test-local-install.sh` on one runner (matrix:
`ubuntu-latest`) and gates the publish job behind its success. That's a
single PR-sized change worth doing before the first paid customer.
