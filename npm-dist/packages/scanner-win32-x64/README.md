# @devseccode/scanner-win32-x64

> **Don't install this package directly.** Install
> [`@devseccode/scanner`](https://www.npmjs.com/package/@devseccode/scanner)
> instead — it auto-resolves this platform package for 64-bit Windows.

This package ships the prebuilt `devseccode.exe` binary for `win32-x64`
(x86_64 Windows 10 or newer). It is listed as an `optionalDependency`
of `@devseccode/scanner`, so `npm` only downloads the platform variant
that matches your OS and CPU.

## What's inside

- `bin/dsc.exe` — the standalone DevSecCode public CLI binary. Built
  via PyInstaller from
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
On Windows, the wrapper resolves `dsc.exe` instead of `dsc`.

## License

Proprietary — see the `LICENSE` file shipped in this tarball, also
reproduced in [the parent
package](https://www.npmjs.com/package/@devseccode/scanner). Installing
or using this package means you accept the DevSecCode End User License
Agreement.
