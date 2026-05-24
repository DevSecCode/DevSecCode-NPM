"""Full-screen overlay screens for the play-menu surfaces.

Quests, hunter stats, init, CI hint, and the IDE upsell all share a
single overlay helper: a prompt_toolkit full-screen Application that
takes over the alt-screen, draws Rich-rendered content at the top,
and dismisses on q / esc / enter. When the user is in a real terminal
this stops the menu choices from "stacking" beneath the previous
output — each surface gets its own screen.

In non-TTY (CI, pipe) we skip prompt_toolkit entirely and just print
the same Rich renderable to stderr so scripts and `| less` users
still see the content.
"""

from __future__ import annotations

import os
import shutil
import sys
from io import StringIO
from typing import Iterable

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from rich.columns import Columns
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dsc.gamification.characters import get_character
from dsc.gamification.deva import ACCENT_COLOR, CATCHPHRASE, GLOW_COLOR, active_portrait, deva_portrait
from dsc.gamification.profile import Profile
from dsc.version import __version__


_DEFAULT_HINT = "press q · esc · enter to close"


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def _terminal_width() -> int:
    size = shutil.get_terminal_size(fallback=(100, 30))
    return max(60, size.columns)


def _render_to_ansi(renderable: RenderableType, *, width: int) -> str:
    """Render a Rich renderable to an ANSI-escaped string for prompt_toolkit."""
    buf = StringIO()
    console = Console(
        file=buf,
        force_terminal=True,
        color_system="standard",
        width=width,
        highlight=False,
        soft_wrap=False,
    )
    console.print(renderable)
    return buf.getvalue()


def show_overlay(
    title: str,
    renderable: RenderableType,
    *,
    hint: str = _DEFAULT_HINT,
) -> None:
    """Display `renderable` in a full-screen prompt_toolkit overlay.

    Falls back to a plain stderr print when the env isn't interactive.
    """
    if not _is_interactive():
        console = Console(file=sys.stderr, highlight=False)
        console.print(renderable)
        return

    width = _terminal_width()
    ansi_body = _render_to_ansi(renderable, width=width)

    kb = KeyBindings()

    @kb.add("q")
    @kb.add("escape")
    @kb.add("enter")
    @kb.add("c-c")
    @kb.add("c-d")
    def _(event):
        event.app.exit()

    content_window = Window(
        FormattedTextControl(
            text=ANSI(ansi_body),
            focusable=True,
        ),
        wrap_lines=False,
        always_hide_cursor=True,
    )

    def _status_text():
        return FormattedText([
            ("fg:ansimagenta bold", f"  {title}  "),
            ("", "    "),
            ("fg:ansibrightblack", hint),
        ])

    status_window = Window(
        FormattedTextControl(text=_status_text),
        height=Dimension.exact(1),
    )

    layout = HSplit([content_window, status_window])

    app = Application(
        layout=Layout(layout),
        key_bindings=kb,
        full_screen=True,
        mouse_support=False,
    )
    try:
        app.run()
    except (KeyboardInterrupt, EOFError):
        pass


# --- panel renderers --------------------------------------------------
# Each surface builds its content as a Rich renderable. Callers can
# either pass it straight to `show_overlay` (TUI) or print it to a
# regular console (non-TTY) — same renderable either way.


_QUESTS: tuple[tuple[str, str, str], ...] = (
    (
        "First Blood",
        "Hardcoded secrets",
        "Find committed credentials before attackers do.",
    ),
    (
        "Injection Hunter",
        "SQLi, XSS, command injection, path traversal",
        "Clear the classic web-app traps.",
    ),
    (
        "Crypto Clean-up",
        "Weak crypto and cleartext transport",
        "Retire risky primitives and unsafe channels.",
    ),
    (
        "Container Guard",
        "Dockerfile and Kubernetes checks",
        "Harden deployment config before it ships.",
    ),
    (
        "Boss Fight",
        "SARIF in CI",
        "Make the build fail on high-severity findings.",
    ),
)


def render_quests_panel() -> Panel:
    # Two-line-per-quest layout keeps the goal text readable on
    # narrow terminals where a three-column grid would otherwise wrap
    # every word individually.
    rows: list = []
    rows.append(Text("The public campaign — what the free rules catch.", style="dim"))
    rows.append(Text(""))
    for quest, focus, goal in _QUESTS:
        line1 = Text()
        line1.append(quest, style=f"bold {ACCENT_COLOR}")
        line1.append("   ", style="dim")
        line1.append(focus, style="bold")
        line2 = Text()
        line2.append("    ↳ ", style="dim")
        line2.append(goal, style="dim")
        rows.append(line1)
        rows.append(line2)
        rows.append(Text(""))
    rows.append(Text("Start here:    ", style="dim", end=""))
    rows.append(Text("devseccode hunt .", style="bold"))
    rows.append(Text("CI boss fight: ", style="dim", end=""))
    rows.append(
        Text(
            "devseccode scan . --format sarif --output devseccode.sarif",
            style="bold",
        )
    )

    return Panel(
        Group(*rows),
        title=Text("QUEST MAP", style=f"bold {ACCENT_COLOR}"),
        title_align="left",
        border_style=ACCENT_COLOR,
        padding=(1, 2),
    )


def render_stats_panel(profile: Profile) -> RenderableType:
    """Hunter profile panel — character portrait + level/XP/achievement stats.

    Achievements appear as a sibling panel when any are unlocked, so the
    main panel stays uncluttered for newer players.
    """
    char = get_character(profile.hunter_class)
    portrait_text, portrait_color = active_portrait(profile.hunter_class)

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column(no_wrap=True)

    table.add_row("Hunter", Text(f"{char.glyph} {char.name}", style=f"bold {char.accent_color}"))
    table.add_row("Title", Text(char.title, style=f"italic {char.accent_color}"))
    table.add_row("Catchphrase", Text(f"\"{char.catchphrase}\"", style="italic"))
    table.add_row(
        "Level",
        Text(f"{profile.level}  ({profile.xp_into_level}/100 XP)", style="bold"),
    )
    table.add_row("Total XP", str(profile.total_xp))
    table.add_row("Hunts completed", str(profile.hunts_completed))
    table.add_row("Unique rules triggered", str(len(profile.unique_rules)))
    table.add_row("Achievements", str(len(profile.achievements)))

    # Streak.
    streak_val = getattr(profile, "current_streak", 0)
    longest_val = getattr(profile, "longest_streak", 0)
    streak_text = Text()
    streak_text.append(str(streak_val), style="bold bright_yellow" if streak_val >= 7 else "bold")
    if longest_val > 0:
        streak_text.append(f"  (best: {longest_val})", style="dim")
    table.add_row("Streak", streak_text)

    # Difficulty.
    diff = getattr(profile, "difficulty", "normal")
    diff_style = {"easy": "green", "hard": "bold red"}.get(diff, "dim")
    table.add_row("Difficulty", Text(diff.upper(), style=diff_style))

    # Active title (loot).
    active = getattr(profile, "active_title", None)
    loot_list = getattr(profile, "loot", [])
    if active:
        from dsc.gamification.profile import get_loot_info
        info = get_loot_info(active)
        title_display = info[0] if info else active
        table.add_row("Title", Text(title_display, style="bold bright_cyan"))
    if loot_list:
        table.add_row("Loot collected", str(len(loot_list)))

    table.add_row("Profile created", profile.created_at or "—")
    table.add_row("Last hunt", profile.last_hunt_at or "—")

    portrait = Text(portrait_text, style=portrait_color)
    main_panel = Panel(
        Columns([portrait, table], equal=False, expand=False, padding=(0, 4)),
        title=Text("HUNTER PROFILE", style=f"bold {char.accent_color}"),
        title_align="left",
        border_style=char.accent_color,
        padding=(1, 2),
    )

    if not profile.achievements:
        return main_panel

    from dsc.gamification.achievements import get_achievement
    ach_table = Table.grid(padding=(0, 2))
    ach_table.add_column(style="bright_yellow", no_wrap=True)
    ach_table.add_column(no_wrap=True)
    ach_table.add_column(style="dim")
    for key in profile.achievements:
        ach = get_achievement(key)
        if ach is None:
            continue
        ach_table.add_row(ach.glyph, Text(ach.title, style="bold"), ach.description)
    achievements_panel = Panel(
        ach_table,
        title=Text("ACHIEVEMENTS UNLOCKED", style="bold bright_yellow"),
        title_align="left",
        border_style="bright_yellow",
        padding=(1, 2),
    )
    return Group(main_panel, Text(""), achievements_panel)


def render_init_panel(*, target_path: str, already_existed: bool, force: bool) -> Panel:
    body = Text()
    if already_existed and not force:
        body.append("Config already exists at\n", style="dim")
        body.append(f"  {target_path}\n\n", style="bold")
        body.append(
            "Pass --force to overwrite. Existing rules / ignores will be lost.",
            style="yellow",
        )
        border = "yellow"
        title = "INIT — SKIPPED"
    else:
        body.append("Wrote ", style="dim")
        body.append(target_path, style=f"bold {ACCENT_COLOR}")
        body.append("  ✓\n\n", style="bright_green bold")
        body.append(
            "The config controls scan paths, ignored directories, language\n"
            "coverage, and the severity threshold for `hunt` / `scan`.\n\n",
            style="dim",
        )
        body.append("Next:\n", style="bold")
        body.append("  Edit ", style="dim")
        body.append(".dsc.yml", style="bold")
        body.append(" to tune the scope for this repo, then\n", style="dim")
        body.append("  run ", style="dim")
        body.append("devseccode hunt .", style="bold")
        border = ACCENT_COLOR
        title = "INIT"
    return Panel(
        body,
        title=Text(title, style=f"bold {border}"),
        title_align="left",
        border_style=border,
        padding=(1, 2),
    )


def render_ci_mode_panel() -> Panel:
    body = Text()
    body.append("Scriptable scan that exits non-zero when findings cross\n", style="dim")
    body.append("the severity threshold. Drop this into a CI step.\n\n", style="dim")
    body.append("  devseccode scan . --format sarif --output devseccode.sarif --fail-on high\n", style="bold")
    body.append("\nThe SARIF file uploads cleanly to GitHub Code Scanning.\n", style="dim")
    body.append("\nUse ", style="dim")
    body.append("--format junit", style="bold")
    body.append(" for CI systems that consume JUnit XML, or ", style="dim")
    body.append("--format json", style="bold")
    body.append("\nfor a structured payload you can post-process yourself.", style="dim")
    return Panel(
        body,
        title=Text("CI MODE", style=f"bold {ACCENT_COLOR}"),
        title_align="left",
        border_style=ACCENT_COLOR,
        padding=(1, 2),
    )


def render_ide_panel() -> Panel:
    body = Text()
    body.append("DevSecCode public CLI is the ", style="dim")
    body.append("starter campaign", style=f"bold {ACCENT_COLOR}")
    body.append(": local security hunts, focused rules,\n", style="dim")
    body.append("and CI-friendly reports.\n\n", style="dim")
    body.append("DevSecCode IDE", style=f"bold {GLOW_COLOR}")
    body.append(" unlocks the full campaign:\n\n", style="dim")
    items = [
        ("Complete rule library", "every detector, every CWE family"),
        ("Compliance mapping", "HIPAA / PCI / SOC 2 / NIST / FedRAMP / ISO / CMMC"),
        ("Audit-grade evidence", "OSCAL AR + signed evidence packages"),
        ("POA&M generation", "open-finding plans of action and milestones"),
        ("Git-history scanning", "find credentials buried in past commits"),
        ("SBOM + OSV enrichment", "CycloneDX / SPDX, dependency CVEs"),
        ("Guided remediation", "AI-assisted fixes inside your editor"),
        ("Pentesting toolkit", "offensive security workflows, exploit validation, attack surface mapping"),
    ]
    for title, desc in items:
        body.append("  • ", style=ACCENT_COLOR)
        body.append(title, style="bold")
        body.append(" — ", style="dim")
        body.append(desc, style="dim")
        body.append("\n")
    body.append("\nLearn more: ", style="dim")
    body.append("https://devseccode.com", style=f"bold underline {ACCENT_COLOR}")
    return Panel(
        body,
        title=Text("DEVSECCODE IDE", style=f"bold {GLOW_COLOR}"),
        title_align="left",
        border_style=GLOW_COLOR,
        padding=(1, 2),
    )


# --- public show_* shortcuts -----------------------------------------

def show_quests() -> None:
    show_overlay("QUEST MAP", render_quests_panel())


def show_stats(profile: Profile) -> None:
    show_overlay("HUNTER PROFILE", render_stats_panel(profile))


def show_init_result(*, target_path: str, already_existed: bool, force: bool) -> None:
    show_overlay(
        "INIT",
        render_init_panel(
            target_path=target_path,
            already_existed=already_existed,
            force=force,
        ),
    )


def show_ci_mode() -> None:
    show_overlay("CI MODE", render_ci_mode_panel())


def show_ide() -> None:
    show_overlay("DEVSECCODE IDE", render_ide_panel())


def render_last_report_panel() -> Panel:
    """Render the stored last-hunt report as a Rich panel."""
    from dsc.gamification.report_store import load_report

    report = load_report()
    if report is None:
        body = Text("No report saved yet. Run a hunt first!", style="yellow")
        return Panel(
            body,
            title=Text("LAST REPORT", style="bold yellow"),
            title_align="left",
            border_style="yellow",
            padding=(1, 2),
        )

    body = Text()
    # Header
    if report.gate_passed:
        body.append("QUEST COMPLETE  ", style="bold white on green")
    else:
        body.append("QUEST FAILED  ", style="bold white on red")
    body.append(f"  {report.total_findings} encounters", style="bold")
    body.append(f"\n\nTimestamp:  ", style="dim")
    body.append(report.timestamp, style="bold")
    body.append(f"\nTargets:   ", style="dim")
    body.append(", ".join(report.targets) or "—", style="bold")
    body.append(f"\nFiles:     ", style="dim")
    body.append(str(report.files_scanned), style="bold")
    body.append(f"\nDuration:  ", style="dim")
    body.append(f"{report.duration_ms / 1000.0:.2f}s", style="bold")

    # Shield score
    stars = {"S": "*****", "A": "**** ", "B": "***  ", "C": "**   ", "D": "*    "}.get(report.shield_rank, "*")
    body.append(f"\n\nSHIELD     ", style="dim")
    body.append(stars, style="bold bright_yellow")
    body.append(f"  {report.shield_score}/100", style="bold")
    body.append(f"  Rank {report.shield_rank}", style=f"bold {ACCENT_COLOR}")

    # Severity breakdown
    if report.findings_by_severity:
        body.append("\n\nSEVERITY BREAKDOWN\n", style="bold dim")
        sev_colors = {"CRITICAL": "bold red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "blue", "INFO": "dim"}
        for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            count = report.findings_by_severity.get(sev, 0)
            if count:
                body.append(f"  {sev:<10}", style=sev_colors.get(sev, ""))
                body.append(f" {count}\n", style="bold")

    # XP
    body.append(f"\nXP Earned: ", style="dim")
    body.append(f"+{report.xp_earned}", style="bold bright_yellow")
    body.append(f"  Level: ", style="dim")
    body.append(str(report.level_after), style="bold")

    # Achievements
    if report.new_achievements:
        body.append("\n\nNEW ACHIEVEMENTS\n", style="bold bright_yellow")
        from dsc.gamification.achievements import get_achievement
        for key in report.new_achievements:
            ach = get_achievement(key)
            if ach:
                body.append(f"  {ach.glyph} {ach.title}", style="bold")
                body.append(f" — {ach.description}\n", style="dim")

    # Finding details summary (first 10)
    if report.finding_details:
        body.append(f"\nFINDINGS ({report.total_findings} total)\n", style="bold dim")
        for i, det in enumerate(report.finding_details[:15]):
            sev_style = {"CRITICAL": "bold red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "blue"}.get(det.get("severity", ""), "dim")
            body.append(f"  {det.get('severity', ''):>8}", style=sev_style)
            body.append(f"  {det.get('file', '')}:{det.get('line', '')}", style="bold")
            body.append(f"  {det.get('rule_id', '')}\n", style="dim")
        if len(report.finding_details) > 15:
            body.append(f"  ... and {len(report.finding_details) - 15} more\n", style="dim")

    body.append("\n\nTip: ", style="dim")
    body.append("Use 'Save Report' from the menu to export as JSON.", style="italic dim")

    return Panel(
        body,
        title=Text("LAST HUNT REPORT", style=f"bold {ACCENT_COLOR}"),
        title_align="left",
        border_style=ACCENT_COLOR,
        padding=(1, 2),
    )


def show_last_report() -> None:
    show_overlay("LAST REPORT", render_last_report_panel())


def render_leaderboard_panel(profile: Profile) -> Panel:
    """Personal best shield scores per target."""
    from pathlib import Path as _P

    body = Text()
    if not profile.best_scores:
        body.append("No scores recorded yet. Run a hunt to set your first record!", style="yellow")
        return Panel(
            body,
            title=Text("LEADERBOARD", style=f"bold {ACCENT_COLOR}"),
            title_align="left",
            border_style=ACCENT_COLOR,
            padding=(1, 2),
        )

    body.append("PERSONAL BEST SCORES\n\n", style="bold dim")

    # Sort by score descending.
    sorted_scores = sorted(profile.best_scores.items(), key=lambda kv: -kv[1])
    for i, (target, score) in enumerate(sorted_scores, start=1):
        # Letter rank.
        if score >= 95: rank = "S"
        elif score >= 85: rank = "A"
        elif score >= 70: rank = "B"
        elif score >= 50: rank = "C"
        else: rank = "D"

        rank_style = {"S": "bold bright_yellow", "A": "bold green", "B": "yellow", "C": "red", "D": "bold red"}.get(rank, "")

        # Shorten the path for display.
        try:
            display = str(_P(target).name) or target
        except Exception:
            display = target

        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, "  ")
        body.append(f"  {medal} ", style="")
        body.append(f"{score:>3}/100", style="bold")
        body.append(f"  Rank ", style="dim")
        body.append(rank, style=rank_style)
        body.append(f"  {display}\n", style="bold")

    # Summary stats.
    body.append(f"\n  Targets scored: {len(profile.best_scores)}", style="dim")
    body.append(f"  ·  Longest streak: {profile.longest_streak}d", style="dim")
    body.append(f"  ·  Current streak: {profile.current_streak}d", style="dim")

    return Panel(
        body,
        title=Text("LEADERBOARD", style=f"bold {ACCENT_COLOR}"),
        title_align="left",
        border_style=ACCENT_COLOR,
        padding=(1, 2),
    )


def show_leaderboard(profile: Profile) -> None:
    show_overlay("LEADERBOARD", render_leaderboard_panel(profile))
