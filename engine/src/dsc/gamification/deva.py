"""Deva — the personality of the DevSecCode CLI.

A single fixed identity (no class picker). Deva is the watcher: a
luminous blue-purple particle-sphere that accompanies the player on
every hunt. Voice is oracular but warm — short, observational lines
rather than the chatty narration of an RPG class.

The portrait is rendered as a dotted orb in ASCII. Rich colors the
glyphs in bright_magenta as the primary accent (closest 256-color
match to the blue-purple of Deva's reference image).

If we ever need to localize or theme Deva (different colors per build,
different voice lines per surface), this is the single place to do it.
"""

from __future__ import annotations

from dataclasses import dataclass


# Primary accent. Used by banner, summary, encounter, and menu surfaces.
# bright_magenta on a 256-color terminal renders blue-purple; on truecolor
# terminals Rich falls through to the closer hex below if available.
ACCENT_COLOR = "bright_magenta"
ACCENT_RGB = "#9b8cff"   # truecolor fallback — close to Deva's reference glow
GLOW_COLOR = "bright_blue"


# Stippled-orb portrait. Centered, ~13 lines tall x 25 wide. The • and ·
# combination evokes the dense particle-cloud look from the reference
# image: bullet dots for the body, mid-dots for the corona.
PORTRAIT = r"""
            · • • • ·
        · • • • • • • • ·
      • • • • • • • • • • •
    · • • • • • • • • • • • ·
    • • • • • • • • • • • • •
    • • • • • • • • • • • • •
    • • • • • • • • • • • • •
    • • • • • • • • • • • • •
    · • • • • • • • • • • • ·
      • • • • • • • • • • •
        · • • • • • • • ·
            · • • • ·
"""


CATCHPHRASE = "I see what was hidden."


# Voice lines — short, observational, oracular. Used by the rendering
# modules to sprinkle Deva commentary into the hunt without retemplating
# every string. Keep these short (single sentence) so they read as
# whispered guidance, not paragraphs of lore.
@dataclass(frozen=True, slots=True)
class _Voice:
    hunt_start: str
    scan_done_with_findings: str   # formatted with {n}
    scan_done_clean: str
    inspect_file: str              # formatted with {file}
    inspect_clean: str
    inspect_all: str
    achievement_unlocked: str
    level_up: str
    summary_gate_failed: str
    summary_gate_passed_dirty: str
    summary_clean: str
    map_prompt: str
    exit_hunt: str


VOICE = _Voice(
    hunt_start="I'm watching the perimeter. Let's begin.",
    scan_done_with_findings="Sweep complete. {n} anomalies — start anywhere.",
    scan_done_clean="Sweep complete. The code is quiet.",
    inspect_file="{file}. I'll show you what I see.",
    inspect_clean="This file is silent. For now.",
    inspect_all="All threats at once. Watch them carefully.",
    achievement_unlocked="A milestone — well done.",
    level_up="You grow stronger.",
    summary_gate_failed="The shadows are deep here.",
    summary_gate_passed_dirty="You held the line.",
    summary_clean="All quiet. I remain vigilant.",
    map_prompt="Where shall we look?",
    exit_hunt="Until next time.",
)


def deva_color() -> str:
    """Return the accent color name Rich should use for Deva surfaces."""
    return ACCENT_COLOR


def deva_portrait() -> str:
    """Return the dotted-orb ASCII portrait, stripped of leading/trailing blank lines."""
    return PORTRAIT.strip("\n")


def deva_line(template: str, **kwargs) -> str:
    """Format a Deva voice line with the standard prefix."""
    if kwargs:
        template = template.format(**kwargs)
    return f"Deva: {template}"


def active_portrait(hunter_class: str | None) -> tuple[str, str]:
    """Return (portrait_text, accent_color) for the active character.

    If hunter_class is set, returns the pixel-art character sprite.
    Otherwise falls back to Deva's orb.
    """
    if hunter_class:
        from dsc.gamification.characters import get_character
        char = get_character(hunter_class)
        return char.portrait, char.accent_color
    return deva_portrait(), ACCENT_COLOR


def active_name(hunter_class: str | None) -> str:
    """Return the display name for the active character."""
    if hunter_class:
        from dsc.gamification.characters import get_character
        return get_character(hunter_class).name
    return "Deva"
