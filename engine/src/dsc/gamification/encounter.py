"""Render each scan finding as an RPG-style enemy encounter.

The encounter card swaps the usual "rule_id / message / snippet" layout
for a stat-block presentation: the finding is an ENEMY with a name
(derived from category + rule), an HP bar (severity), and a WEAKNESS
(fix suggestion). Visually it sits inside a Rich Panel whose border
color matches the severity.

This module deliberately only renders one finding at a time. The
caller (`public_cli.cmd_hunt`) drives the loop so a future iteration
can stream encounters with `rich.live` or add brief pauses for
dramatic effect without restructuring this module.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from dsc.gamification.categories import (
    CONTAINER,
    CRYPTO,
    DefenseCategory,
    INJECTION,
    MISC,
    SECRETS,
    classify_finding,
)
from dsc.scanner.models import Finding, Severity


# Per-CWE enemy names. Mapping the CWE to a single themed name keeps the
# narration consistent ("the XSS Wraith strikes again") instead of randomly
# rotating an XSS finding into a "SSRF Banshee" just because the hash hit.
_CWE_TO_ENEMY: dict[str, str] = {
    # Secrets / credential exposure.
    "CWE-798": "Credential Goblin",
    "CWE-259": "Credential Goblin",
    "CWE-321": "Key Specter",
    "CWE-200": "Secret Phantom",
    "CWE-532": "Log Leak Wraith",
    # Injection family.
    "CWE-79":  "XSS Wraith",
    "CWE-89":  "SQL Hydra",
    "CWE-78":  "Cmd Demon",
    "CWE-77":  "Cmd Demon",
    "CWE-90":  "LDAP Lich",
    "CWE-91":  "XML Imp",
    "CWE-94":  "Code Demon",
    "CWE-95":  "Eval Wraith",
    "CWE-22":  "Path Witch",
    "CWE-23":  "Path Witch",
    "CWE-36":  "Path Witch",
    "CWE-117": "Log Imp",
    "CWE-611": "XXE Banshee",
    "CWE-918": "SSRF Banshee",
    "CWE-643": "XPath Specter",
    "CWE-1336": "Template Imp",
    # Crypto / TLS / hashing.
    "CWE-327": "Hash Ghoul",
    "CWE-328": "Hash Ghoul",
    "CWE-326": "Weak-Key Reaper",
    "CWE-330": "Entropy Ghoul",
    "CWE-338": "Entropy Ghoul",
    "CWE-310": "Cipher Zombie",
    "CWE-319": "Cleartext Banshee",
    "CWE-295": "Cert-Trust Reaper",
    "CWE-296": "Cert-Trust Reaper",
    "CWE-297": "Cert-Trust Reaper",
    "CWE-916": "Bare-Hash Ghoul",
    # Container / privilege / config.
    "CWE-250": "Privilege Wyvern",
    "CWE-732": "Permission Hellhound",
    "CWE-276": "Permission Hellhound",
    "CWE-668": "Mount Hellhound",
    "CWE-269": "Privilege Wyvern",
    "CWE-1004": "Cookie Imp",
}

# Per-category fallback when a CWE isn't mapped. Each category gets a
# single canonical name so unknown CWEs in that family still feel coherent.
_CATEGORY_FALLBACK: dict[str, str] = {
    SECRETS.key: "Secret Phantom",
    INJECTION.key: "Inject-O-Tron",
    CRYPTO.key: "Cipher Zombie",
    CONTAINER.key: "Container Drake",
    MISC.key: "Rogue Bit",
}

_SEVERITY_BORDER_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "blue",
    Severity.INFO: "dim white",
}

_SEVERITY_HP_BARS = {
    # 10-slot bars; "filled" represents how dangerous this enemy is.
    Severity.CRITICAL: ("██████████", 10, "FATAL"),
    Severity.HIGH:     ("████████░░", 8, "GRAVE"),
    Severity.MEDIUM:   ("██████░░░░", 6, "WOUNDING"),
    Severity.LOW:      ("████░░░░░░", 4, "NICK"),
    Severity.INFO:     ("██░░░░░░░░", 2, "GRAZE"),
}

_LEXER_BY_SUFFIX = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
    ".php": "php",
    ".cs": "csharp",
    ".sh": "bash",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".dockerfile": "docker",
}


def _enemy_name(finding: Finding, category: DefenseCategory) -> str:
    cwe = (finding.cwe or "").strip().upper()
    if cwe and not cwe.startswith("CWE-"):
        if cwe.startswith("CWE"):
            cwe = "CWE-" + cwe[3:].lstrip("-")
        elif cwe.isdigit():
            cwe = "CWE-" + cwe
    named = _CWE_TO_ENEMY.get(cwe)
    if named:
        return named
    return _CATEGORY_FALLBACK.get(category.key, "Rogue Bit")


def _lexer_for(file_path: str) -> str:
    name = Path(file_path).name.lower()
    if name == "dockerfile" or name.endswith(".dockerfile"):
        return "docker"
    return _LEXER_BY_SUFFIX.get(Path(file_path).suffix.lower(), "text")


def _err_console() -> Console:
    return Console(file=sys.stderr, highlight=False)


def _stat_line(label: str, value: str, *, value_style: str = "") -> Text:
    line = Text()
    line.append(f"{label:<9} ", style="dim")
    line.append(value, style=value_style)
    return line


def render_encounter(
    finding: Finding,
    *,
    index: int,
    total: int,
    console: Console | None = None,
) -> None:
    console = console or _err_console()
    category = classify_finding(finding)
    enemy = _enemy_name(finding, category)
    sev_style = _SEVERITY_BORDER_STYLE.get(finding.severity, "white")
    hp_glyph, hp_filled, hp_label = _SEVERITY_HP_BARS[finding.severity]

    # Title encodes the encounter number + severity tag + enemy name.
    title = Text()
    title.append(f"Encounter {index}/{total}", style="bold")
    title.append("  ·  ", style="dim")
    title.append(finding.severity.name, style=sev_style)
    title.append("  ·  ", style="dim")
    title.append(enemy, style=f"bold {sev_style}")

    body_parts: list = []

    # Stat block: HP bar, CWE tag, family.
    stats = Text()
    stats.append("HP        ", style="dim")
    stats.append(hp_glyph, style=sev_style)
    stats.append(f"  {hp_label}  ({hp_filled}/10)\n", style="dim")
    stats.append("FAMILY    ", style="dim")
    stats.append(category.label, style="bold")
    stats.append(f"   {category.emoji}\n", style="dim")
    stats.append("ID        ", style="dim")
    stats.append(f"{finding.rule_id}  ({finding.cwe})", style="dim")
    body_parts.append(stats)

    # Location.
    loc = Text()
    loc.append("\nFOUND AT  ", style="dim")
    loc.append(
        f"{finding.file_path}:{finding.line_start}:{finding.column}",
        style="bold magenta",
    )
    body_parts.append(loc)

    # Attack pattern (code snippet). Falls back to lore if no snippet.
    if finding.snippet:
        body_parts.append(Text("\nATTACK PATTERN", style="bold dim"))
        lexer = _lexer_for(finding.file_path)
        body_parts.append(
            Syntax(
                finding.snippet.rstrip("\n"),
                lexer,
                line_numbers=False,
                word_wrap=True,
                theme="ansi_dark",
                background_color="default",
            )
        )

    # Lore = the rule's message. Trim aggressively — multi-paragraph
    # messages turn the encounter into a wall of text.
    lore = (finding.message or "").strip()
    if lore:
        body_parts.append(Text("\nLORE", style="bold dim"))
        body_parts.append(Text(lore, style=""))

    # Weakness = fix suggestion.
    fix = (finding.fix_suggestion or "").strip()
    if fix:
        body_parts.append(Text("\nWEAKNESS", style="bold dim"))
        body_parts.append(Text(fix, style="green"))

    console.print(
        Panel(
            Group(*body_parts),
            border_style=sev_style,
            title=title,
            title_align="left",
            padding=(0, 1),
        )
    )


def render_no_encounters(console: Console | None = None) -> None:
    console = console or _err_console()
    text = Text()
    text.append("No enemies in sight. ", style="bold green")
    text.append(
        "Your repo is clean for the public ruleset — try a fresh target or "
        "level up with the full DevSecCode IDE rule library.",
        style="dim",
    )
    console.print(Panel(text, border_style="green", title="Clear field", title_align="left"))


def render_all_encounters(
    findings: Iterable[Finding],
    *,
    console: Console | None = None,
) -> None:
    findings_list = list(findings)
    console = console or _err_console()
    if not findings_list:
        render_no_encounters(console)
        return
    total = len(findings_list)
    for i, f in enumerate(findings_list, start=1):
        render_encounter(f, index=i, total=total, console=console)
