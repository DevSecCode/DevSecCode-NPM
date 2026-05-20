"""End-of-hunt RPG summary card.

Renders the big stat sheet the player sees after a hunt: Shield Score
with star rank, per-category defense bars, XP earned with level-up
fanfare, and any newly unlocked achievements. Followed by a "next
quest" pointer derived from the weakest defense line.

This is the closer of the gamified UX. If you only see one piece of
the experience, this is the one that has to land.
"""

from __future__ import annotations

import sys
from typing import Iterable

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dsc.gamification.achievements import get_achievement
from dsc.gamification.categories import (
    ALL_CATEGORIES,
    DefenseCategory,
    classify_finding,
)
from dsc.gamification.deva import ACCENT_COLOR, CATCHPHRASE, VOICE
from dsc.gamification.profile import HuntRecord, Profile, XP_PER_LEVEL
from dsc.scanner.models import Finding, Severity


_SEVERITY_PENALTY = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 12,
    Severity.MEDIUM: 5,
    Severity.LOW: 2,
    Severity.INFO: 0,
}


def shield_score(findings: Iterable[Finding]) -> tuple[int, str, str]:
    """Return (score, letter_rank, star_rank).

    Score is 100 minus the severity-weighted penalty, clamped to [0, 100].
    The letter rank is the classic gamer score band; the star rank is the
    visual hint for the summary card.
    """
    penalty = sum(_SEVERITY_PENALTY.get(f.severity, 0) for f in findings)
    score = max(0, 100 - penalty)
    if score >= 95:
        return score, "S", "*****"
    if score >= 85:
        return score, "A", "**** "
    if score >= 70:
        return score, "B", "***  "
    if score >= 50:
        return score, "C", "**   "
    return score, "D", "*    "


def _category_defense(findings: list[Finding], category: DefenseCategory) -> tuple[int, int]:
    """For one category, return (defense_percent, finding_count)."""
    cat_findings = [f for f in findings if classify_finding(f).key == category.key]
    penalty = sum(_SEVERITY_PENALTY.get(f.severity, 0) for f in cat_findings)
    return max(0, 100 - penalty), len(cat_findings)


def _bar(percent: int, *, width: int = 10) -> str:
    filled = int(round((percent / 100.0) * width))
    return ("█" * filled) + ("░" * (width - filled))


def _defense_label(percent: int) -> tuple[str, str]:
    if percent >= 95:
        return "Sealed", "bright_green"
    if percent >= 80:
        return "Strong", "green"
    if percent >= 60:
        return "Holding", "yellow"
    if percent >= 30:
        return "Wounded", "red"
    return "Compromised", "bold red"


def _err_console() -> Console:
    return Console(file=sys.stderr, highlight=False)


def _quest_outcome_header(*, gate_passed: bool, total_findings: int) -> Text:
    text = Text()
    if total_findings == 0:
        text.append("QUEST COMPLETE  ", style="bold white on green")
        text.append("  All defenses held.", style="green")
        return text
    if gate_passed:
        text.append("QUEST COMPLETE  ", style="bold white on green")
        text.append(
            f"  {total_findings} encounters survived under threshold.",
            style="green",
        )
        return text
    text.append("QUEST FAILED  ", style="bold white on red")
    text.append(
        f"  {total_findings} encounters breached your gate.",
        style="red",
    )
    return text


def _deva_outcome_line(*, gate_passed: bool, total_findings: int) -> Text:
    if total_findings == 0:
        msg = VOICE.summary_clean
    elif gate_passed:
        msg = VOICE.summary_gate_passed_dirty
    else:
        msg = VOICE.summary_gate_failed
    text = Text()
    text.append("Deva: ", style="dim")
    text.append(msg, style=f"italic {ACCENT_COLOR}")
    return text


def _next_quest_pointer(findings: list[Finding], gate_passed: bool) -> Text:
    if not findings:
        text = Text()
        text.append("NEXT  ", style="bold dim")
        text.append("Wire ", style="dim")
        text.append("`devseccode scan . --format sarif`", style="bold")
        text.append(
            " into CI and unlock the Boss Fight: make builds fail on high findings.",
            style="dim",
        )
        return text

    worst = min(
        ALL_CATEGORIES,
        key=lambda cat: _category_defense(findings, cat)[0],
    )
    worst_percent, worst_count = _category_defense(findings, worst)
    text = Text()
    text.append("NEXT  ", style="bold dim")
    text.append(worst.quest_name, style="bold")
    text.append("  ·  ", style="dim")
    text.append(worst.next_quest_hint, style="dim")
    text.append(f"  ({worst_count} in this hunt)", style="dim")
    return text


def _xp_section(record: HuntRecord) -> Text:
    text = Text()
    text.append("XP        ", style="dim")
    xp_into = record.xp_after % XP_PER_LEVEL
    text.append(_bar(int(xp_into * 100 / XP_PER_LEVEL)), style="bright_yellow")
    text.append(f"  {xp_into}/{XP_PER_LEVEL}", style="bold")
    text.append("    ", style="")
    text.append(f"+{record.xp_delta} this hunt", style="bright_yellow")
    text.append("    ", style="")
    text.append(f"Lvl {record.level_before} → Lvl {record.level_after}", style="dim")
    if record.level_up:
        text.append("   ⇑ LEVEL UP!", style="bold bright_yellow")
    return text


def _defense_table(findings: list[Finding]) -> Table:
    table = Table.grid(padding=(0, 2), pad_edge=False)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)

    for cat in ALL_CATEGORIES:
        percent, count = _category_defense(findings, cat)
        label, label_style = _defense_label(percent)
        bar = _bar(percent)
        count_text = Text(f"{count} caught" if count else "clear", style="dim")
        table.add_row(
            Text(cat.label.upper(), style="dim"),
            Text(bar, style=label_style),
            Text(label, style=label_style),
            count_text,
        )
    return table


def _achievements_block(record: HuntRecord) -> list:
    if not record.new_achievements:
        return []
    rows = [Text("\nNEW ACHIEVEMENTS", style="bold bright_yellow")]
    for key in record.new_achievements:
        ach = get_achievement(key)
        if ach is None:
            continue
        line = Text()
        line.append(f"  {ach.glyph}  ", style="bold bright_yellow")
        line.append(ach.title, style="bold")
        line.append("  —  ", style="dim")
        line.append(ach.description, style="dim")
        rows.append(line)
    rows.append(Text(f"Deva: {VOICE.achievement_unlocked}", style="italic dim"))
    return rows


def render_summary(
    *,
    profile: Profile,
    record: HuntRecord,
    findings: Iterable[Finding],
    gate_passed: bool,
    duration_ms: int,
    files_scanned: int,
) -> None:
    findings = list(findings)
    console = _err_console()

    score, letter, stars = shield_score(findings)

    header = _quest_outcome_header(gate_passed=gate_passed, total_findings=len(findings))

    score_row = Text()
    score_row.append("SHIELD    ", style="dim")
    score_row.append(stars, style="bold bright_yellow")
    score_row.append(f"  {score}/100", style="bold")
    score_row.append(f"  ·  Rank {letter}", style=f"bold {ACCENT_COLOR}")

    stats_row = Text()
    stats_row.append(
        f"{len(findings)} encounter{'s' if len(findings) != 1 else ''}",
        style="bold",
    )
    stats_row.append("  ·  ", style="dim")
    stats_row.append(f"{files_scanned} file{'s' if files_scanned != 1 else ''} scanned", style="dim")
    stats_row.append("  ·  ", style="dim")
    stats_row.append(f"{duration_ms/1000.0:.2f}s", style="dim")

    body = [
        header,
        _deva_outcome_line(gate_passed=gate_passed, total_findings=len(findings)),
        Text(""),
        score_row,
        stats_row,
        Text(""),
        Text("DEFENSE BREAKDOWN", style="bold dim"),
        _defense_table(findings),
        Text(""),
        _xp_section(record),
    ]

    if record.level_up:
        body.append(Text(f"Deva: {VOICE.level_up}", style="italic dim"))

    achievements_rows = _achievements_block(record)
    if achievements_rows:
        body.extend(achievements_rows)

    body.extend([
        Text(""),
        _next_quest_pointer(findings, gate_passed),
    ])

    console.print()
    console.print(
        Panel(
            Group(*body),
            border_style=ACCENT_COLOR,
            title=Text("HUNT REPORT", style=f"bold {ACCENT_COLOR}"),
            title_align="left",
            subtitle=Text(f"\"{CATCHPHRASE}\"", style=f"italic {ACCENT_COLOR}"),
            subtitle_align="right",
            padding=(1, 2),
        )
    )
