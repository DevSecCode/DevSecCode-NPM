#!/usr/bin/env node
// Resolves the platform-specific @devseccode/scanner-<platform>-<arch> sibling
// package (one of which is installed via optionalDependencies) and execs the
// bundled native binary with the caller's argv passed through verbatim. The
// npm package exposes both `devseccode` and the shorter `dsc` alias.
//
// The PyInstaller-built binary speaks the public CLI directly; there is no
// JS-side argument translation.

"use strict";

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const SUPPORTED = new Set([
  "darwin-arm64",
  // "darwin-x64" -- Intel Mac. Not built in this release; GitHub retired the
  // macos-13 runner pool and no hosted Intel Mac runner is available.
  // Intel Mac users get the unsupported-platform error below until we
  // either set up a self-hosted runner or drop Intel Mac support.
  "linux-x64",
  "linux-arm64",
  "win32-x64",
]);

function resolveBinary() {
  const platform = process.platform;
  const arch = process.arch;
  const key = `${platform}-${arch}`;

  if (!SUPPORTED.has(key)) {
    return {
      error:
        `\n@devseccode/scanner: no prebuilt binary for ${key}.\n` +
        `Supported platforms: ${[...SUPPORTED].join(", ")}.\n`,
    };
  }

  const pkgName = `@devseccode/scanner-${platform}-${arch}`;
  const binName = platform === "win32" ? "dsc.exe" : "dsc";
  const relBin = path.posix.join("bin", binName);

  // Try the published optionalDependency first.
  try {
    return { binPath: require.resolve(`${pkgName}/${relBin}`) };
  } catch (_) {
    // fall through to local-dev lookup
  }

  // Fallback: when running from a checkout (smoke tests, CI), the platform
  // package may live alongside this one under packages/scanner-<key>/. Resolve
  // relative to __dirname so the lookup works without a registry roundtrip.
  const localCandidate = path.resolve(
    __dirname,
    "..",
    "..",
    `scanner-${key}`,
    relBin,
  );
  if (fs.existsSync(localCandidate)) {
    return { binPath: localCandidate };
  }

  return {
    error:
      `\n@devseccode/scanner: cannot find the ${pkgName} package.\n` +
      `This usually means the optional dependency was skipped by your\n` +
      `package manager. Reinstall with the matching platform/arch:\n` +
      `  npm install ${pkgName}\n`,
  };
}

const { binPath, error } = resolveBinary();
if (error) {
  process.stderr.write(error);
  process.exit(1);
}

// PyInstaller --onefile binaries unpack to a temp dir on first invocation;
// `inherit` keeps stdin/stdout/stderr fully transparent so terminal output,
// SARIF JSON, and progress bars all behave exactly like the native binary.
const child = spawn(binPath, process.argv.slice(2), { stdio: "inherit" });

child.on("error", (err) => {
  process.stderr.write(`@devseccode/scanner: failed to spawn ${binPath}: ${err.message}\n`);
  if (err.code === "EACCES") {
    process.stderr.write(
      `The binary is not executable. Try:\n  chmod +x ${binPath}\n`,
    );
  }
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    // Re-raise the signal in our own process so shells see the original
    // termination reason (e.g. ^C produces a Ctrl-C exit, not a generic 1).
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
