"""File enumeration and language detection.

Per scanner-rearchitecture-spec.md Section 3.2: this module shrinks
from 425 lines (with tree-sitter parsing, AST building, and per-file
content materialization) to ~150 lines covering only what the new
engine needs:

- ``LanguageRegistry``: extension/filename -> language id
- ``CodeFile``: thin path + language + sha tuple (no AST, no content)
- ``find_git_root``, ``parse_directory``: file enumeration with .devaignore
- ``get_changed_files``: git diff helper for diff-only scans

Tree-sitter and stdlib ast parsing are gone -- OpenGrep parses files
itself, so we no longer need the IR.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_IGNORE_DIRS = {
    ".dsc_cache",
    ".git",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}

# Auto-skip filename globs. These match files OpenGrep would
# otherwise spend minutes on -- minified / bundled JavaScript
# (one line of 9.8 million characters has been observed in real
# customer corpora and benchmark runs alike). Override by
# explicitly listing the paths in `.devaignore` with a leading
# `!` (negation), or by setting DSC_SCAN_BUNDLED_FILES=1.
DEFAULT_BUNDLED_PATTERNS = [
    "*.min.js",
    "*.min.mjs",
    "*.min.css",
    "*.bundle.js",
    "*.bundle.mjs",
    "*.chunk.js",
    "*-min.js",
    "*.js.map",
    "*.css.map",
]

# File-size and line-length pre-filter thresholds. Hand-written
# source rarely exceeds either; bundled / minified output reliably
# blows past both. Env-overridable for the rare legitimate case
# where a user wants to scan a giant generated file.
_DEFAULT_MAX_FILE_BYTES = 1024 * 1024  # 1 MB
_DEFAULT_MAX_LINE_CHARS = 5_000


def _max_file_bytes() -> int:
    raw = os.environ.get("DSC_MAX_FILE_BYTES")
    if raw and raw.isdigit():
        return int(raw)
    return _DEFAULT_MAX_FILE_BYTES


def _max_line_chars() -> int:
    raw = os.environ.get("DSC_MAX_LINE_CHARS")
    if raw and raw.isdigit():
        return int(raw)
    return _DEFAULT_MAX_LINE_CHARS


def _scan_bundled_files() -> bool:
    return os.environ.get("DSC_SCAN_BUNDLED_FILES", "").strip() in ("1", "true", "yes")


# Module-level skip log so a single scan can surface (in the SARIF
# invocations or CLI output) which files were pre-filtered. Reset
# at the top of each parse_directory call.
_PATHOLOGICAL_LOG: list[str] = []


def get_pathological_skips() -> list[str]:
    """Return the list of paths skipped by the most recent
    parse_directory call as 'rel/path (reason)' strings.
    """
    return list(_PATHOLOGICAL_LOG)


def is_pathological(path: Path) -> tuple[bool, str]:
    """Return (skip?, reason) for OpenGrep-pathological files.

    The check has two stages so the cheaper one fails fast:

      1. File size > DSC_MAX_FILE_BYTES (default 1 MB).
      2. Any line in the first 64 KB > DSC_MAX_LINE_CHARS (default
         5,000 chars). Reading 64 KB is enough to catch the
         minified-JS shape (single-line files are rejected on the
         first newline scan); we don't read more than that to keep
         the pre-filter cheap.

    We don't open files we've already decided to skip on size.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return False, ""
    if size > _max_file_bytes():
        return True, f"size={size}>{_max_file_bytes()}"

    # Cheap line-length probe: read the first chunk, look at the
    # longest run between newlines. Skip the probe entirely when the
    # file is too small to contain a line that exceeds the threshold
    # -- it's the most common case (typical source files are 2-15 KB)
    # and the open+read otherwise adds up to seconds across a workspace
    # of several thousand files.
    max_line = _max_line_chars()
    if size <= max_line:
        return False, ""
    if size == 0:
        return False, ""
    try:
        with path.open("rb") as fh:
            head = fh.read(64 * 1024)
    except OSError:
        return False, ""
    if not head:
        return False, ""
    longest = 0
    run = 0
    for byte in head:
        if byte == 0x0A:  # \n
            run = 0
        else:
            run += 1
            if run > longest:
                longest = run
    if longest > max_line:
        return True, f"max_line={longest}>{max_line}"
    return False, ""


class LanguageRegistry:
    _ext_to_lang = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".cjs": "javascript",
        ".mjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".scss": "css",
        ".md": "markdown",
        ".txt": "text",
        ".go": "go",
        ".java": "java",
        ".rb": "ruby",
        ".rs": "rust",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "ini",
        ".conf": "ini",
        ".properties": "ini",
        ".xml": "xml",
        ".tf": "terraform",
        ".gradle": "gradle",
        ".kts": "gradle",
        ".swift": "swift",
        ".m": "objc",
        ".h": "objc",
        ".plist": "plist",
        ".pbxproj": "plist",
        ".entitlements": "plist",
        ".storyboard": "xml",
        ".xib": "xml",
        ".kt": "kotlin",
        ".php": "php",
        ".cs": "csharp",
        ".dart": "dart",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
        ".scala": "scala",
    }
    _name_to_lang = {
        "dockerfile": "dockerfile",
        "docker-compose.yml": "dockercompose",
        "docker-compose.yaml": "dockercompose",
        "compose.yml": "dockercompose",
        "compose.yaml": "dockercompose",
        ".env": "ini",
        ".nvmrc": "runtime",
        ".node-version": "runtime",
        ".python-version": "runtime",
        "requirements.txt": "requirements",
        "pipfile": "toml",
        "pipfile.lock": "json",
        "poetry.lock": "toml",
        "package-lock.json": "json",
        "npm-shrinkwrap.json": "json",
        "yarn.lock": "lockfile",
        "pnpm-lock.yaml": "yaml",
        "cargo.toml": "toml",
        "cargo.lock": "lockfile",
        "go.mod": "gomod",
        "go.sum": "lockfile",
        "gemfile": "ruby",
        "gemfile.lock": "lockfile",
        "composer.json": "json",
        "composer.lock": "json",
    }

    @classmethod
    def detect_language(cls, path: Path) -> str | None:
        name = path.name.lower()
        if name in cls._name_to_lang:
            return cls._name_to_lang[name]
        if name.startswith(".env."):
            return "ini"
        return cls._ext_to_lang.get(path.suffix.lower())

    @classmethod
    def supported_extensions(cls) -> set[str]:
        return set(cls._ext_to_lang.keys())


@dataclass(frozen=True, slots=True)
class CodeFile:
    """Lightweight handle to a source file.

    The new engine pipeline (OpenGrep + RealtimeMatcher) does not need
    in-memory content, since OpenGrep parses files on demand from disk.
    The optional ``content`` and ``lines`` fields exist for legacy
    consumers (notably ``dsc.githistory.scanner``) that synthesize
    CodeFiles from commit diffs and scan the synthetic content directly.
    Such consumers will migrate to a dedicated shape during the Phase 1
    detector cleanup; until then the optional fields keep them working
    without forcing a parallel data type.
    """

    path: str
    language: str
    content: str = ""
    lines: list[str] = field(default_factory=list)
    tree: object | None = None
    parse_error: str | None = None

    def sha256(self) -> str:
        if self.content:
            return hashlib.sha256(
                self.content.encode("utf-8", errors="replace")
            ).hexdigest()
        try:
            with open(self.path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            return ""


def find_git_root(start: Path) -> Path | None:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _load_ignore_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def _match_ignore_pattern(rel_posix: str, pattern: str, *, is_dir: bool) -> bool:
    pat = pattern
    anchored = pat.startswith("/")
    if anchored:
        pat = pat.lstrip("/")

    directory_only = pat.endswith("/")
    if directory_only:
        pat = pat.rstrip("/")

    if directory_only and not (
        is_dir or rel_posix.startswith(f"{pat}/") or f"/{pat}/" in f"/{rel_posix}/"
    ):
        return False

    if anchored:
        return fnmatch.fnmatch(rel_posix, pat) or rel_posix.startswith(f"{pat}/")

    if fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(Path(rel_posix).name, pat):
        return True
    return f"/{pat}/" in f"/{rel_posix}/" or rel_posix.startswith(f"{pat}/")


def should_ignore_path(
    rel_path: Path,
    *,
    is_dir: bool,
    patterns: list[str],
) -> bool:
    rel_posix = rel_path.as_posix()
    ignored = False
    for raw in patterns:
        negated = raw.startswith("!")
        pat = raw[1:] if negated else raw
        if _match_ignore_pattern(rel_posix, pat, is_dir=is_dir):
            ignored = not negated
    return ignored


def get_changed_files(repo_root: Path) -> set[Path]:
    if not (repo_root / ".git").exists():
        return set()

    def _run(args: list[str]) -> list[str]:
        res = subprocess.run(
            args,
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            return []
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    files = set(_run(["git", "diff", "--name-only"]))
    files |= set(_run(["git", "diff", "--name-only", "--cached"]))
    files |= set(_run(["git", "ls-files", "--others", "--exclude-standard"]))
    return {Path(p) for p in files}


def collect_ignore_patterns(
    git_root: Path,
    *,
    extra: Iterable[str] | None = None,
) -> list[str]:
    patterns: list[str] = [f"{d}/" for d in sorted(DEFAULT_IGNORE_DIRS)]
    if not _scan_bundled_files():
        patterns.extend(DEFAULT_BUNDLED_PATTERNS)
    patterns.extend(_load_ignore_file(git_root / ".gitignore"))
    patterns.extend(_load_ignore_file(git_root / ".dscignore"))
    patterns.extend(_load_ignore_file(git_root / ".devaignore"))
    if extra:
        patterns.extend(extra)
    return patterns


def parse_directory(
    path: Path,
    *,
    extensions: Iterable[str] | None = None,
    extra_ignore_patterns: list[str] | None = None,
    diff_only: bool = False,
) -> list[CodeFile]:
    """Enumerate scannable files honoring ignore patterns and diff filtering."""
    root = path.resolve()
    if root.is_file():
        if extensions is not None and root.suffix.lower() not in set(extensions):
            return []
        lang = LanguageRegistry.detect_language(root)
        return [CodeFile(path=str(root), language=lang or "text")] if lang else []

    exts = set(extensions) if extensions is not None else None
    git_root = find_git_root(root) or root
    ignore_patterns = collect_ignore_patterns(git_root, extra=extra_ignore_patterns)

    changed: set[Path] | None = None
    if diff_only:
        if git_root == root and not (root / ".git").exists():
            changed = set()
        else:
            changed = get_changed_files(git_root)

    code_files: list[CodeFile] = []
    _PATHOLOGICAL_LOG.clear()
    for dirpath, dirnames, filenames in os.walk(root):
        dir_rel = Path(dirpath).resolve().relative_to(root)
        kept_dirs: list[str] = []
        for d in dirnames:
            rel = (dir_rel / d) if dir_rel != Path(".") else Path(d)
            if d in DEFAULT_IGNORE_DIRS:
                continue
            if should_ignore_path(rel, is_dir=True, patterns=ignore_patterns):
                continue
            kept_dirs.append(d)
        dirnames[:] = kept_dirs

        for fname in filenames:
            file_path = Path(dirpath) / fname
            if exts is not None and file_path.suffix.lower() not in exts:
                continue
            language = LanguageRegistry.detect_language(file_path)
            if language is None:
                continue
            rel = file_path.resolve().relative_to(root)
            if should_ignore_path(rel, is_dir=False, patterns=ignore_patterns):
                continue
            # Pre-filter pathological files (oversized or
            # minified-shape one-line monsters). OpenGrep's regex
            # engine catastrophically backtracks on these; skipping
            # at enumeration time costs us nothing for hand-written
            # code.
            skip, reason = is_pathological(file_path)
            if skip:
                _PATHOLOGICAL_LOG.append(f"{rel} ({reason})")
                continue
            if changed is not None:
                try:
                    repo_rel = file_path.resolve().relative_to(git_root)
                except ValueError:
                    repo_rel = rel
                if repo_rel not in changed:
                    continue

            code_files.append(CodeFile(path=str(file_path), language=language))

    return code_files
