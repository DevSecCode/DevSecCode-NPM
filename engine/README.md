# DSC scanner (Python source)

Source for the `dsc` CLI that ships as the npm `@devseccode/scanner` package.
The npm distribution builds this directory into a single-file binary via
[`dsc-cli.spec`](./dsc-cli.spec); end users never need Python installed.

Layout:

- `src/dsc/` — scanner library and CLI entry point (`dsc.public_cli:main`)
- `public_rulepacks/` — curated OpenGrep `.yml` rules bundled into the binary
- `vendor/opengrep/` — OpenGrep binary fetched by `vendor/opengrep/setup.sh`
- `dsc-cli.spec` — PyInstaller spec consumed by `npm-dist/scripts/build-binary.sh`

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run the CLI directly without bundling:
python -m dsc scan ../resources/sample-vulns --format json | head

# Or build the same binary CI produces:
pip install pyinstaller
bash ../npm-dist/scripts/build-binary.sh        # auto-detects host platform
```

Python `>=3.10` is required by `pyproject.toml`. The version printed by
`dsc --version` is sourced from `src/dsc/version.py` — the single source
of truth for both the engine and the npm package versions.
