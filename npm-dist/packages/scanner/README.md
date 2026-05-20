# @devseccode/scanner

Gamified local security CLI for hunting common code vulnerabilities from npm.
It ships as a prebuilt single-file binary, so users do not need Python,
OpenGrep, or a DevSecCode IDE install to get started.

## Install

No npm login is required for the public package.

```bash
# One-shot security hunt:
npx @devseccode/scanner hunt .

# Global install:
npm install -g @devseccode/scanner
devseccode hunt .

# Project-local install, recommended for CI:
npm install --save-dev @devseccode/scanner
npx devseccode scan . --format sarif --output devseccode.sarif
```

## Supported platforms

The parent package declares one `optionalDependencies` entry per platform.
`npm` installs only the package that matches your machine; the rest are
skipped by the `os` / `cpu` fields.

| Target          | Package                                |
| --------------- | -------------------------------------- |
| macOS Apple Si  | `@devseccode/scanner-darwin-arm64`         |
| Linux x86_64    | `@devseccode/scanner-linux-x64`            |
| Linux arm64     | `@devseccode/scanner-linux-arm64`          |
| Windows x86_64  | `@devseccode/scanner-win32-x64`            |

Intel Mac (`darwin-x64`) is not built for this release. Alpine / musl Linux is
not supported; use a glibc image such as Debian or Ubuntu in CI.

## Quick Start

```bash
# Start the gamified path:
devseccode hunt .

# See the public quest map:
devseccode quests

# Emit SARIF for GitHub Code Scanning:
devseccode scan . --format sarif --output devseccode.sarif

# Emit JSON for local tooling:
devseccode scan . --format json --output devseccode-findings.json

# List the public rule subset:
devseccode list-rules

# Explain a rule:
devseccode explain deva.cwe-89.python-sql-injection

# Initialize a .dsc.yml file:
devseccode init
```

`devseccode --help` lists every public subcommand; `devseccode <subcommand>
--help` documents the flags for each one. `dsc` remains available as a short
alias for existing users and scripts.

## What's Included

This public CLI intentionally includes a focused subset of DevSecCode's local
scanner:

- A `hunt` command with Shield Score, rank, and next-quest guidance
- High-signal SAST rules for common web, secrets, crypto, XML, and
  infrastructure risks
- Terminal, JSON, SARIF, and JUnit output
- Configurable fail thresholds for CI
- Local-only execution with no telemetry or code upload

The full DevSecCode IDE adds the complete rule library, compliance mapping,
SBOM and dependency intelligence, git-history analysis, signed evidence
packages, OSCAL/POA&M outputs, and guided remediation workflows.

## Privacy

`devseccode hunt` and `devseccode scan` are fully local. No code, telemetry,
or analytics leaves your machine.

## License

Proprietary -- All Rights Reserved. Installing or using this package means
you accept the DevSecCode End User License Agreement in [LICENSE](./LICENSE).
Redistribution, modification, reverse engineering, and use to build a
competing product are not permitted.
