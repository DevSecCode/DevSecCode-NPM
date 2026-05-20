# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the public `dsc` CLI used by the npm distribution.

Usage (from engine/):

    pyinstaller dsc-cli.spec --onefile

The output is dist/dsc (or dist/dsc.exe on Windows): a single-file binary
that exposes the public CLI surface from `dsc.public_cli`.

Size target after onefile + UPX: ~18 MB compressed per platform.

The curated rulepack subset rides along inside the bundle as rulepacks/.
"""

import os
from pathlib import Path

block_cipher = None

_here = Path(SPECPATH)
_scanner_src = _here / "src"
_opengrep_name = "opengrep.exe" if os.name == "nt" else "opengrep"
_opengrep_bin = _here / "vendor" / "opengrep" / "bin" / _opengrep_name
_opengrep_binaries = (
    [(str(_opengrep_bin), "vendor/opengrep/bin")]
    if _opengrep_bin.exists()
    else []
)

a = Analysis(
    [str(_scanner_src / "dsc" / "public_cli.py")],
    pathex=[str(_scanner_src)],
    binaries=_opengrep_binaries,
    datas=[
        # Curated public subset. It is mounted as rulepacks/ because
        # dsc._paths.rulepacks_expanded_dir() resolves that runtime path.
        (str(_here / "public_rulepacks"), "rulepacks"),
    ],
    hiddenimports=[
        "dsc",
        "dsc.public_cli",
        "dsc.engine",
        "dsc.engine.rulepack_loader",
        "dsc.formatters",
        "dsc.formatters.json_fmt",
        "dsc.formatters.junit",
        "dsc.formatters.sarif",
        "dsc.formatters.terminal",
        "dsc.postprocessors.base",
        "dsc.scanner",
        "dsc.scanner.engine",
        "dsc.scanner.models",
        # Public CLI gamification surface.
        "dsc.gamification",
        "dsc.gamification.achievements",
        "dsc.gamification.banner",
        "dsc.gamification.categories",
        "dsc.gamification.deva",
        "dsc.gamification.encounter",
        "dsc.gamification.explore",
        "dsc.gamification.imports",
        "dsc.gamification.layout",
        "dsc.gamification.menu",
        "dsc.gamification.profile",
        "dsc.gamification.screens",
        "dsc.gamification.summary",
        "dsc.gamification.triage",
        "dsc.gamification.tui",
        # prompt_toolkit submodules used by the TUI (questionary already
        # pulls the base package, but Application/Layout/KeyBindings
        # subpaths are dynamic and need declaring).
        "prompt_toolkit.application",
        "prompt_toolkit.application.application",
        "prompt_toolkit.formatted_text",
        "prompt_toolkit.key_binding",
        "prompt_toolkit.key_binding.bindings",
        "prompt_toolkit.layout",
        "prompt_toolkit.layout.containers",
        "prompt_toolkit.layout.controls",
        "prompt_toolkit.layout.dimension",
        "prompt_toolkit.widgets",
        "prompt_toolkit.filters",
        # tree-sitter language bindings (loaded by language registry at runtime).
        "tree_sitter",
        "tree_sitter_python",
        "tree_sitter_javascript",
        "tree_sitter_typescript",
        "tree_sitter_go",
        "tree_sitter_java",
        "tree_sitter_rust",
        # YAML preset + rulepack loader.
        "yaml",
        # Interactive play menu. questionary lazily resolves prompt_toolkit
        # subpackages — declare the ones we touch so PyInstaller doesn't
        # silently miss them.
        "questionary",
        "questionary.prompts",
        "questionary.prompts.select",
        "questionary.prompts.text",
        "prompt_toolkit",
        "prompt_toolkit.application",
        "prompt_toolkit.shortcuts",
        "prompt_toolkit.key_binding",
        "prompt_toolkit.styles",
        "wcwidth",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy transitive deps that aren't needed by the public CLI.
        # PyInstaller would otherwise pull them in just because they're
        # installed in the dev venv.
        "fastapi",
        "starlette",
        "uvicorn",
        "structlog",
        "apscheduler",
        "cryptography",
        "pydantic",
        "pydantic_core",
        # Test tooling.
        "pytest",
        "pytest_asyncio",
        "ruff",
        "mypy",
        "black",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="dsc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX shrinks the binary by ~40%. Disabled on macOS — Apple's notarization
    # service rejects UPX-packed binaries, so the CI macOS step overrides
    # `upx=False` via `pyinstaller --upx-exclude '*'` if needed.
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
