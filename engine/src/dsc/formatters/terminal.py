from __future__ import annotations

from collections import Counter
from io import StringIO
from pathlib import Path

from dsc.scanner.models import ScanResult, Severity

try:  # pragma: no cover - exercised in environments where rich is installed.
    from rich.console import Console
    from rich.syntax import Syntax

    _RICH_AVAILABLE = True
except Exception:  # pragma: no cover
    _RICH_AVAILABLE = False

_COLOR = {
    Severity.CRITICAL: "\033[1;31m",
    Severity.HIGH: "\033[31m",
    Severity.MEDIUM: "\033[33m",
    Severity.LOW: "\033[34m",
    Severity.INFO: "\033[2m",
}
_RESET = "\033[0m"


def _badge(sev: Severity) -> str:
    color = _COLOR.get(sev, "")
    return f"{color}{sev.name}{_RESET}"


def _summary_text(result: ScanResult) -> str:
    counts = Counter([f.severity for f in result.findings])
    total = len(result.findings)
    summary = (
        f"{total} findings "
        f"(critical={counts.get(Severity.CRITICAL, 0)}, "
        f"high={counts.get(Severity.HIGH, 0)}, "
        f"medium={counts.get(Severity.MEDIUM, 0)}, "
        f"low={counts.get(Severity.LOW, 0)}, "
        f"info={counts.get(Severity.INFO, 0)})"
    )
    duration_s = result.scan_duration_ms / 1000.0
    return f"{summary}. Scanned {result.files_scanned} files in {duration_s:.2f}s."


def _guess_lexer(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".java": "java",
        ".go": "go",
        ".rb": "ruby",
        ".rs": "rust",
    }.get(suffix, "text")


def _format_with_rich(result: ScanResult, *, verbose: bool) -> str:
    sev_style = {
        Severity.CRITICAL: "bold red",
        Severity.HIGH: "red",
        Severity.MEDIUM: "yellow",
        Severity.LOW: "blue",
        Severity.INFO: "dim",
    }
    capture = StringIO()
    console = Console(
        file=capture,
        force_terminal=True,
        color_system="standard",
        width=100,
    )

    if result.errors:
        console.print("[yellow]Scanner warnings/errors:[/yellow]")
        for e in result.errors:
            console.print(f"  - {e}")
        console.print()

    for f in result.findings:
        loc = f"{f.file_path}:{f.line_start}:{max(f.column, 1)}"
        style = sev_style.get(f.severity, "")
        console.print(
            f"[{style}]{f.severity.name}[/{style}] {loc} {f.rule_id} {f.message}"
        )
        if f.snippet:
            syntax = Syntax(
                f.snippet.rstrip("\n"),
                lexer=_guess_lexer(f.file_path),
                line_numbers=True,
                highlight_lines={1},
                word_wrap=True,
            )
            console.print(syntax)
        if f.fix_suggestion:
            console.print(f"[green]Fix:[/green] {f.fix_suggestion}")
        console.print()

    console.print(_summary_text(result))
    if verbose and result.detector_timings_ms:
        console.print("Detector timings (ms):")
        for detector_id, elapsed in sorted(result.detector_timings_ms.items()):
            console.print(f"  - {detector_id}: {elapsed}")
    return capture.getvalue().rstrip() + "\n"


def _format_plain(result: ScanResult, *, verbose: bool) -> str:
    # Fallback used when Rich is unavailable in the runtime environment.
    lines: list[str] = []

    if result.errors:
        lines.append(f"{_COLOR[Severity.MEDIUM]}Scanner warnings/errors:{_RESET}")
        for e in result.errors:
            lines.append(f"  - {e}")
        lines.append("")

    for f in result.findings:
        loc = f"{f.file_path}:{f.line_start}:{max(f.column, 0)}"
        lines.append(f"{_badge(f.severity)} {loc} {f.rule_id} {f.message}")
        if f.snippet:
            lines.append(f"    {f.snippet.rstrip()}")
        if f.fix_suggestion:
            lines.append(f"    Fix: {f.fix_suggestion}")
        lines.append("")

    lines.append(_summary_text(result))
    if verbose and result.detector_timings_ms:
        lines.append("Detector timings (ms):")
        for detector_id, elapsed in sorted(result.detector_timings_ms.items()):
            lines.append(f"  - {detector_id}: {elapsed}")
    return "\n".join(lines).rstrip() + "\n"


def format_terminal(result: ScanResult, *, verbose: bool = False) -> str:
    if _RICH_AVAILABLE:
        return _format_with_rich(result, verbose=verbose)
    return _format_plain(result, verbose=verbose)
