"""Lightweight import detector for the hunt map.

Goal: build a {file_path: [imported_file_paths]} graph so the TUI can
draw edges between files. This is the dumbest-possible implementation
that still reads ~90% of typical projects:

  * Regex scan for `import X` / `from X import` / `import "X"` /
    `import X from "Y"` / `require("X")`.
  * Resolve the import string against the importing file's directory
    first, then against the scan target root.
  * Try common file extensions per language.
  * Match against the set of files we already know about (from the
    scan result + a quick walk of the scan target).

External imports (stdlib, npm packages, go modules from elsewhere)
are reported separately so the inspect modal can surface them
informationally without cluttering the graph with non-existent nodes.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# --- regex patterns ---------------------------------------------------
# Kept tight intentionally — these run line-by-line and we'd rather
# under-detect than confidently extract garbage.

_PY_IMPORT = re.compile(
    r"^\s*(?:from\s+(\.+\w[\w.]*|\w[\w.]*)\s+import|import\s+(\w[\w.]*))",
    re.MULTILINE,
)
_JS_IMPORT = re.compile(
    r"""(?:^|\s)(?:import\b[^'"]*from\s*|import\s*|require\s*\(\s*)['"]([^'"]+)['"]""",
    re.MULTILINE,
)
# Go has single-line and block-import forms. We grab the strings inside
# `import ( ... )` blocks too.
_GO_SINGLE = re.compile(r'^\s*import\s+(?:[\w.]+\s+)?"([^"]+)"\s*$', re.MULTILINE)
_GO_BLOCK = re.compile(r"^\s*import\s*\(\s*([\s\S]*?)\s*\)\s*$", re.MULTILINE)
_GO_BLOCK_LINE = re.compile(r'(?:[\w.]+\s+)?"([^"]+)"')


# Extensions to try when resolving an import string to a real file.
# Order matters: we prefer .py over .pyi, .ts over .tsx etc.
_EXT_BY_LANG: dict[str, tuple[str, ...]] = {
    "python":     (".py",),
    "javascript": (".js", ".jsx", ".mjs", ".cjs"),
    "typescript": (".ts", ".tsx", ".d.ts", ".js"),
    "go":         (".go",),
}


@dataclass
class ImportGraph:
    """Resolved import edges between files in the scan target.

    `edges[a]` is the set of file paths that `a` imports (one-way edges).
    `externals[a]` is the set of non-resolvable import strings (stdlib,
    npm packages, go modules outside the workspace) for informational
    display in the inspect modal.
    """
    edges: dict[str, set[str]] = field(default_factory=dict)
    externals: dict[str, set[str]] = field(default_factory=dict)

    def imports_of(self, file_path: str) -> list[str]:
        return sorted(self.edges.get(file_path, set()))

    def importers_of(self, file_path: str) -> list[str]:
        """Inverted edge lookup. Linear in graph size; fine for our scale."""
        result: list[str] = []
        for src, dests in self.edges.items():
            if file_path in dests:
                result.append(src)
        return sorted(result)

    def externals_of(self, file_path: str) -> list[str]:
        return sorted(self.externals.get(file_path, set()))


# --- main entry -------------------------------------------------------

def build_graph(
    files: list[str],
    *,
    target_roots: list[Path],
) -> ImportGraph:
    """Build the import graph across `files`.

    Returns an ImportGraph keyed by absolute file paths (matching the
    `Finding.file_path` shape so the TUI can join on file path directly).
    """
    abs_files = [str(Path(f).resolve()) for f in files]
    file_set = set(abs_files)
    roots = [Path(r).resolve() for r in target_roots]

    graph = ImportGraph()
    for abs_path in abs_files:
        lang = _guess_lang(abs_path)
        if not lang:
            continue
        try:
            content = Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        imports = _extract_imports(content, lang)
        local: set[str] = set()
        external: set[str] = set()
        for raw in imports:
            resolved = _resolve_import(
                raw,
                lang=lang,
                importer=Path(abs_path),
                file_set=file_set,
                roots=roots,
            )
            if resolved is None:
                external.add(raw)
            else:
                # Don't self-edge — a file importing itself isn't useful.
                if resolved != abs_path:
                    local.add(resolved)
        if local:
            graph.edges[abs_path] = local
        if external:
            graph.externals[abs_path] = external

    return graph


def walk_target_files(targets: list[Path], *, max_files: int = 2000) -> list[str]:
    """Enumerate source files under each target.

    Used to bring 1-hop import neighbors into the graph even when those
    neighbors had no findings (so the player can still "navigate" to them).
    Capped so a giant repo doesn't blow up the map.
    """
    seen: set[str] = set()
    out: list[str] = []
    exts = {ext for exts in _EXT_BY_LANG.values() for ext in exts}
    for root in targets:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden + node_modules etc. — match what the scanner ignores.
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {
                "node_modules", "vendor", "build", "dist", "__pycache__",
                ".git", ".venv", "venv",
            }]
            for fn in filenames:
                if any(fn.endswith(ext) for ext in exts):
                    full = str(Path(dirpath, fn).resolve())
                    if full not in seen:
                        seen.add(full)
                        out.append(full)
                        if len(out) >= max_files:
                            return out
    return out


# --- internals --------------------------------------------------------

def _guess_lang(path: str) -> str | None:
    p = path.lower()
    if p.endswith(".py"):
        return "python"
    if p.endswith((".ts", ".tsx", ".d.ts")):
        return "typescript"
    if p.endswith((".js", ".jsx", ".mjs", ".cjs")):
        return "javascript"
    if p.endswith(".go"):
        return "go"
    return None


def _extract_imports(content: str, lang: str) -> list[str]:
    out: list[str] = []
    if lang == "python":
        for m in _PY_IMPORT.finditer(content):
            out.append(m.group(1) or m.group(2))
    elif lang in ("javascript", "typescript"):
        for m in _JS_IMPORT.finditer(content):
            out.append(m.group(1))
    elif lang == "go":
        for m in _GO_SINGLE.finditer(content):
            out.append(m.group(1))
        for m in _GO_BLOCK.finditer(content):
            block = m.group(1)
            for sub in _GO_BLOCK_LINE.finditer(block):
                out.append(sub.group(1))
    return [s for s in out if s]


def _resolve_import(
    raw: str,
    *,
    lang: str,
    importer: Path,
    file_set: set[str],
    roots: list[Path],
) -> str | None:
    """Try to resolve `raw` to an absolute file path in `file_set`.

    Returns None if it can't — meaning it's almost certainly an external
    import (stdlib, package, third-party module).
    """
    candidates = _candidate_paths(raw, lang=lang, importer=importer, roots=roots)
    for cand in candidates:
        resolved = str(cand.resolve())
        if resolved in file_set:
            return resolved
    return None


def _candidate_paths(
    raw: str,
    *,
    lang: str,
    importer: Path,
    roots: list[Path],
) -> list[Path]:
    exts = _EXT_BY_LANG.get(lang, ())
    out: list[Path] = []

    if lang == "python":
        # Dotted form: 'foo.bar.baz' or '.foo' / '..foo.bar'
        if raw.startswith("."):
            # Relative: count leading dots, walk up that many directories.
            dots = len(raw) - len(raw.lstrip("."))
            tail = raw[dots:]
            parent = importer.parent
            for _ in range(dots - 1):
                parent = parent.parent
            base = parent / tail.replace(".", "/") if tail else parent
        else:
            # Absolute (project-rooted). Try each scan root.
            parts = raw.split(".")
            base = None
            for root in roots:
                cand = root / "/".join(parts)
                if cand.exists() or cand.with_suffix(".py").exists():
                    base = cand
                    break
            if base is None:
                # Best-guess: importer's package root.
                base = importer.parent / "/".join(parts)
        for ext in exts:
            out.append(base.with_suffix(ext))
        out.append(base / "__init__.py")
        out.append(base)
        return out

    if lang in ("javascript", "typescript"):
        # JS imports are paths. Relative start with . or ..
        if raw.startswith("."):
            base = (importer.parent / raw).resolve()
        else:
            # Bare specifier (`'express'`, `'react'`) is almost always external;
            # we don't have a node_modules resolver. Skip.
            return []
        for ext in exts:
            out.append(base.with_suffix(ext))
        for ext in exts:
            out.append(base / f"index{ext}")
        out.append(base)
        return out

    if lang == "go":
        # Go imports are paths within the module. Without parsing go.mod,
        # the practical heuristic: take the last path component and try to
        # find a .go file by that name in the scan target. Imperfect — it'll
        # over-match for common package names — but good enough for the map.
        for root in roots:
            cand_dir = root / raw
            if cand_dir.exists():
                # Pick any .go file in that dir.
                for child in cand_dir.iterdir():
                    if child.suffix == ".go":
                        out.append(child)
        return out

    return []
