"""Path resolution that works both in source-tree installs and PyInstaller-frozen builds.

Six call sites used to walk `Path(__file__).resolve().parent.parent.parent.parent` to
reach the engine root. That works for source installs but breaks under PyInstaller
because module files are inside `_MEIPASS/` and walking up four levels exits the
bundle. Centralizing the lookup here lets the spec's `datas=` extract data dirs to
predictable paths under `_MEIPASS/`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def engine_root() -> Path:
    """Return the directory that contains rulepacks/, vendor/, etc.

    - Source install: engine/ (three levels up from this file).
    - PyInstaller frozen: sys._MEIPASS, the runtime extraction dir.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    # _paths.py is at engine/src/dsc/_paths.py
    # parents[0]=dsc, parents[1]=src, parents[2]=engine
    return Path(__file__).resolve().parents[2]


def rulepacks_dir() -> Path:
    return engine_root() / "rulepacks"


def rulepacks_expanded_dir() -> Path:
    return rulepacks_dir() / "_expanded"


def vendor_dir() -> Path:
    return engine_root() / "vendor"
