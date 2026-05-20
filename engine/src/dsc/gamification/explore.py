"""Interactive code-map exploration after a hunt.

After the scan completes (in an interactive TTY), instead of dumping
every encounter card linearly, the player gets a map of the codebase
showing where the findings are. They drill into files individually,
or batch-view everything, or jump straight to the summary.

In CI / non-TTY, this module is skipped entirely — the caller renders
encounters linearly and goes straight to the summary card. The map is
TUI-only.

Layout:

  ┌─ HUNT MAP ─────────────────────────────────────────────┐
  │  Deva: Sweep complete. 7 anomalies — start anywhere.   │
  │                                                        │
  │  ●●●  /path/to/file.py            3× HIGH              │
  │  ●●   /path/to/other.js           2× MEDIUM            │
  │  ●    /path/to/dockerfile         1× HIGH              │
  └────────────────────────────────────────────────────────┘

  > Inspect file.py (3 high)
    Inspect other.js (2 medium)
    Inspect dockerfile (1 high)
    ─────
    Show all encounters at once
    ─────
    Finish hunt — show summary
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dsc.gamification import encounter
from dsc.gamification.categories import classify_finding
from dsc.gamification.deva import ACCENT_COLOR, VOICE
from dsc.scanner.models import Finding, Severity


_SEVERITY_DOT_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "blue",
    Severity.INFO: "dim white",
}

_SEVERITY_RANK = {
    Severity.CRITICAL: 5,
    Severity.HIGH: 4,
    Severity.MEDIUM: 3,
    Severity.LOW: 2,
    Severity.INFO: 1,
}

_MAX_DOTS = 5  # cap per-file dot count to keep table aligned


def _err_console() -> Console:
    return Console(file=sys.stderr, highlight=False)


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def _group_by_file(findings: Iterable[Finding]) -> dict[str, list[Finding]]:
    """Group findings by file path, preserving relative discovery order."""
    grouped: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        grouped[f.file_path].append(f)
    return grouped


def _peak_severity(findings: list[Finding]) -> Severity:
    return max((f.severity for f in findings), default=Severity.INFO)


def _format_severity_summary(findings: list[Finding]) -> Text:
    """One-line per-file summary, e.g. '2× HIGH, 1× MEDIUM'."""
    counts: dict[Severity, int] = defaultdict(int)
    for f in findings:
        counts[f.severity] += 1
    parts: list[Text] = []
    for sev in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
        n = counts.get(sev, 0)
        if n == 0:
            continue
        chunk = Text()
        chunk.append(f"{n}× ", style="bold")
        chunk.append(sev.name, style=_SEVERITY_DOT_STYLE[sev])
        parts.append(chunk)
    if not parts:
        return Text("—", style="dim")
    merged = Text()
    for i, p in enumerate(parts):
        if i:
            merged.append(", ", style="dim")
        merged.append_text(p)
    return merged


def _shortest_relative(file_path: str, targets: list[Path]) -> str:
    """Render the path relative to the nearest scan target if possible."""
    p = Path(file_path)
    best: str | None = None
    best_len = -1
    for t in targets:
        try:
            rel = p.relative_to(t)
        except ValueError:
            continue
        rel_str = str(rel)
        # Pick the longest matching root so deep targets win over shallow ones
        # (e.g. scanning ./src means we strip ./src/, not just ./).
        if len(str(t)) > best_len:
            best = rel_str
            best_len = len(str(t))
    if best is None:
        return file_path
    return best


def _render_dots(findings: list[Finding]) -> Text:
    """Stippled severity icons: one ● per finding, capped at _MAX_DOTS."""
    text = Text()
    sorted_findings = sorted(
        findings,
        key=lambda f: -_SEVERITY_RANK.get(f.severity, 0),
    )
    for i, f in enumerate(sorted_findings):
        if i >= _MAX_DOTS:
            break
        text.append("●", style=_SEVERITY_DOT_STYLE.get(f.severity, "white"))
    overflow = len(sorted_findings) - _MAX_DOTS
    if overflow > 0:
        text.append(f"+{overflow}", style="dim")
    return text


def render_map(
    findings: list[Finding],
    targets: list[Path],
    *,
    console: Console | None = None,
) -> None:
    """Render the codebase map panel to stderr."""
    console = console or _err_console()
    grouped = _group_by_file(findings)

    # Sort: highest peak severity first, then by count desc, then by path.
    files_sorted = sorted(
        grouped.items(),
        key=lambda kv: (
            -_SEVERITY_RANK.get(_peak_severity(kv[1]), 0),
            -len(kv[1]),
            kv[0],
        ),
    )

    voice = Text()
    voice.append("Deva: ", style="dim")
    voice.append(
        VOICE.scan_done_with_findings.format(n=len(findings)),
        style=f"italic {ACCENT_COLOR}",
    )

    table = Table.grid(padding=(0, 2))
    table.add_column(no_wrap=True)              # dots
    table.add_column(no_wrap=False)             # path
    table.add_column(no_wrap=True)              # severity summary
    table.add_column(no_wrap=True, style="dim") # category hint

    for path, group in files_sorted:
        # All findings in a file may not share a category; pick the
        # peak-severity finding's category as the file's family hint.
        peak = max(group, key=lambda f: _SEVERITY_RANK.get(f.severity, 0))
        category = classify_finding(peak)
        table.add_row(
            _render_dots(group),
            Text(_shortest_relative(path, targets), style="bold"),
            _format_severity_summary(group),
            Text(category.label, style="dim"),
        )

    body = [voice, Text(""), table]
    console.print()
    console.print(
        Panel(
            _stack(body),
            title=Text("HUNT MAP", style=f"bold {ACCENT_COLOR}"),
            title_align="left",
            border_style=ACCENT_COLOR,
            padding=(1, 2),
        )
    )


def _stack(parts):
    """Render a list of Rich renderables as a vertical group."""
    from rich.console import Group
    return Group(*parts)


# --- interactive loop -------------------------------------------------

_SHOW_ALL = "__all__"
_SHOW_SUMMARY = "__summary__"


def _prompt_action(questionary, files_sorted: list[tuple[str, list[Finding]]], targets: list[Path]) -> str:
    """Returns either a file_path, _SHOW_ALL, or _SHOW_SUMMARY."""
    choices = []
    for path, group in files_sorted:
        rel = _shortest_relative(path, targets)
        # questionary won't render Rich text; build a plain ANSI-free label.
        peak = _peak_severity(group)
        label = f"Inspect {rel}  ({len(group)}× {peak.name.lower()})"
        choices.append(questionary.Choice(title=label, value=path))
    choices.append(questionary.Separator())
    choices.append(questionary.Choice(title="Show all encounters at once", value=_SHOW_ALL))
    choices.append(questionary.Separator())
    choices.append(questionary.Choice(title="Finish hunt — show summary", value=_SHOW_SUMMARY))

    result = questionary.select(
        VOICE.map_prompt,
        choices=choices,
        qmark=">",
        use_arrow_keys=True,
    ).ask()
    # ^C returns None.
    if result is None:
        return _SHOW_SUMMARY
    return result


def _inspect_file(file_path: str, findings: list[Finding], *, console: Console) -> None:
    """Render the encounter cards for a single file's findings."""
    voice = Text()
    voice.append("Deva: ", style="dim")
    voice.append(
        VOICE.inspect_file.format(file=Path(file_path).name),
        style=f"italic {ACCENT_COLOR}",
    )
    console.print()
    console.print(voice)
    for i, f in enumerate(findings, start=1):
        encounter.render_encounter(f, index=i, total=len(findings), console=console)


def _inspect_all(findings: list[Finding], *, console: Console) -> None:
    voice = Text()
    voice.append("Deva: ", style="dim")
    voice.append(VOICE.inspect_all, style=f"italic {ACCENT_COLOR}")
    console.print()
    console.print(voice)
    encounter.render_all_encounters(findings, console=console)


def run_explore_session(
    findings: Iterable[Finding],
    targets: Iterable[Path],
    *,
    console: Console | None = None,
) -> None:
    """Drive the interactive map → drill-in loop.

    Returns when the user selects "Finish hunt" (or sends ^C). Caller
    then renders the summary card.

    No-op if findings is empty (nothing to explore) or if the env isn't
    interactive — both cases let the caller fall back to the linear
    encounter+summary flow.
    """
    findings = list(findings)
    targets = list(targets)
    console = console or _err_console()

    if not findings or not _is_interactive():
        return

    from dsc.gamification.menu import _try_import_questionary
    questionary = _try_import_questionary()
    if questionary is None:
        return

    grouped = _group_by_file(findings)
    files_sorted = sorted(
        grouped.items(),
        key=lambda kv: (
            -_SEVERITY_RANK.get(_peak_severity(kv[1]), 0),
            -len(kv[1]),
            kv[0],
        ),
    )

    render_map(findings, targets, console=console)

    while True:
        try:
            action = _prompt_action(questionary, files_sorted, targets)
        except KeyboardInterrupt:
            return
        if action == _SHOW_SUMMARY:
            return
        if action == _SHOW_ALL:
            _inspect_all(findings, console=console)
        else:
            file_findings = grouped.get(action, [])
            _inspect_file(action, file_findings, console=console)
        # Re-render the map so the next selection has context. The
        # scroll buffer holds the previous inspection above.
        render_map(findings, targets, console=console)
