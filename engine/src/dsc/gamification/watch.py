"""Watch mode — auto-rescan a target on file changes.

Uses a simple polling approach (stat mtime) to avoid adding
inotify/fsevents dependencies. Polls every N seconds and re-runs
the hunt if any source file changed since the last scan.

This is the lite version of the IDE's full file-watcher integration.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.text import Text

from dsc.gamification.deva import ACCENT_COLOR, VOICE
from dsc.gamification.characters import get_character


_SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".java", ".rb", ".rs",
    ".php", ".cs", ".sh", ".yml", ".yaml", ".dockerfile", ".json",
}

_IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".next", ".nuxt",
}

POLL_INTERVAL_SECONDS = 3


def _err_console() -> Console:
    return Console(file=sys.stderr, highlight=False)


def _collect_mtimes(target: Path) -> dict[str, float]:
    """Walk the target and return {path: mtime} for source files."""
    mtimes: dict[str, float] = {}
    if target.is_file():
        mtimes[str(target)] = target.stat().st_mtime
        return mtimes

    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for f in files:
            fp = Path(root) / f
            if fp.suffix.lower() in _SOURCE_EXTENSIONS or fp.name.lower() == "dockerfile":
                try:
                    mtimes[str(fp)] = fp.stat().st_mtime
                except OSError:
                    pass
    return mtimes


def _diff_mtimes(
    old: dict[str, float],
    new: dict[str, float],
) -> list[str]:
    """Return paths that were added, removed, or modified."""
    changed: list[str] = []
    for p, mtime in new.items():
        if p not in old or old[p] != mtime:
            changed.append(p)
    for p in old:
        if p not in new:
            changed.append(p)
    return changed


def run_watch(
    target_path: str,
    *,
    run_hunt_fn=None,
    poll_interval: int = POLL_INTERVAL_SECONDS,
    hunter_class: str | None = None,
) -> int:
    """Poll for file changes and re-run the hunt on each change.

    `run_hunt_fn(target_path)` is the callback that performs the actual
    hunt. If None, we import it from public_cli at call time.

    Ctrl-C exits cleanly.
    """
    console = _err_console()
    target = Path(target_path).resolve()
    char = get_character(hunter_class)

    if not target.exists():
        console.print(Text(f"Target does not exist: {target}", style="bold red"))
        return 2

    console.print()
    header = Text()
    header.append("WATCH MODE ", style=f"bold white on {char.accent_color}")
    header.append(f"  {char.glyph} {char.name}", style=f"bold {char.accent_color}")
    header.append("  ·  ", style="dim")
    header.append(f"watching {target_path}", style="bold")
    console.print(header)

    voice = Text()
    voice.append("Deva: ", style="dim")
    voice.append("I'm watching the perimeter. I'll alert you when something changes.", style=f"italic {ACCENT_COLOR}")
    console.print(voice)
    console.print()

    controls = Text()
    controls.append("  Ctrl-C", style="bold")
    controls.append("  stop watching", style="dim")
    controls.append("    Poll interval: ", style="dim")
    controls.append(f"{poll_interval}s", style="bold")
    console.print(controls)
    console.print()

    # Initial scan
    if run_hunt_fn is not None:
        console.print(Text("Running initial scan...", style=f"italic {ACCENT_COLOR}"))
        try:
            run_hunt_fn(target_path)
        except Exception as exc:
            console.print(Text(f"Scan error: {exc}", style="bold red"))

    prev_mtimes = _collect_mtimes(target)
    scan_count = 1

    try:
        while True:
            time.sleep(poll_interval)
            curr_mtimes = _collect_mtimes(target)
            changed = _diff_mtimes(prev_mtimes, curr_mtimes)

            if changed:
                scan_count += 1
                console.print()
                alert = Text()
                alert.append(f"  [{time.strftime('%H:%M:%S')}] ", style="dim")
                alert.append(f"{len(changed)} file{'s' if len(changed) != 1 else ''} changed", style=f"bold {char.accent_color}")
                alert.append(f"  — rescan #{scan_count}", style="dim")
                console.print(alert)

                # Show which files changed (up to 5)
                for p in changed[:5]:
                    console.print(Text(f"    {Path(p).name}", style="dim"))
                if len(changed) > 5:
                    console.print(Text(f"    ... and {len(changed) - 5} more", style="dim"))

                if run_hunt_fn is not None:
                    try:
                        run_hunt_fn(target_path)
                    except Exception as exc:
                        console.print(Text(f"Scan error: {exc}", style="bold red"))

                prev_mtimes = curr_mtimes
            else:
                # Heartbeat indicator every 10 polls
                pass

    except KeyboardInterrupt:
        console.print()
        farewell = Text()
        farewell.append("Deva: ", style="dim")
        farewell.append("Watch ended. Stay vigilant.", style=f"italic {ACCENT_COLOR}")
        console.print(farewell)
        console.print(Text(f"  {scan_count} scan{'s' if scan_count != 1 else ''} completed.", style="dim"))
        console.print()
        return 0
