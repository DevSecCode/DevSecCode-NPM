# @devseccode/scanner-linux-arm64

> **Don't install this package directly.** Install
> [`@devseccode/scanner`](https://www.npmjs.com/package/@devseccode/scanner)
> instead — it auto-resolves this platform package for ARM64 Linux.

This package ships the prebuilt `devseccode` binary for `linux-arm64`
(ARM64 Linux running glibc — typical for AWS Graviton, Ampere, Apple
M-series under Linux, Raspberry Pi 64-bit OS, etc.). It is **not**
compatible with Alpine / musl Linux. It is listed as an
`optionalDependency` of `@devseccode/scanner`, so `npm` only downloads
the platform variant that matches your OS and CPU.

## What's inside

- `bin/dsc` — the standalone DevSecCode public CLI binary. Built via
  PyInstaller from
  [DevSecCode/DevSecCode-NPM](https://github.com/DevSecCode/DevSecCode-NPM)
  with no external Python or runtime dependency.

## Install (via the parent package)

```bash
# One-shot:
npx @devseccode/scanner hunt .

# Global:
npm install -g @devseccode/scanner
devseccode hunt .

# Project-local:
npm install --save-dev @devseccode/scanner
```

The Node wrapper in `@devseccode/scanner` (`bin/dsc.js`) detects your
platform and `require.resolve()`s this package to find the binary.

## License

Proprietary — see the `LICENSE` file shipped in this tarball, also
reproduced in [the parent
package](https://www.npmjs.com/package/@devseccode/scanner). Installing
or using this package means you accept the DevSecCode End User License
Agreement.
