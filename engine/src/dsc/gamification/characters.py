"""Selectable pixel-art hunter characters.

Each character has a portrait (Unicode block-element sprite), a name,
a catchphrase, an accent color, and voice overrides. The player picks
a character from the play menu; the choice is stored in profile.json
as `hunter_class`.

Deva remains the default (and the "watcher" NPC that narrates), but
the player's *avatar* can now be one of several pixel-art sprites.

Sprites are built from Unicode block elements:
    Full block: █   Upper half: ▀   Lower half: ▄
    Light shade: ░   Medium shade: ▓   Dark shade: █
    These render well in virtually every modern terminal.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Character:
    key: str
    name: str
    title: str
    catchphrase: str
    portrait: str
    accent_color: str
    glyph: str       # single char for the map cursor


# ── Pixel-art sprites ────────────────────────────────────────────────

_KNIGHT_PORTRAIT = r"""
       ▄███▄
      █▓▓▓▓▓█
     █▓▓▀▀▓▓█
     █▓▓▄▄▓▓█
      █████▀
     ▄█▓▓▓█▄
    █▓█████▓█
    █▓▓███▓▓█
    ▀▓▓▓▓▓▓▓▀
      █▓▓▓█
     ██▓▓▓██
     █▀   ▀█
"""

_ROGUE_PORTRAIT = r"""
      ▄▄███▄▄
     ████████▀
    ▐▓▓▓▓▓▓▌
     ▐▓▀▀▓▌
      ▓▄▄▓
      ▄▓▓▄
    ▄▓░░░░▓▄
   ▓░░▓▓▓░░▓
    ▓░░░░░▓
     ▓░░░▓
    ▐▓   ▓▌
    ▀▀   ▀▀
"""

_MAGE_PORTRAIT = r"""
       ▄█▄
      ▄███▄
     ▀▀███▀▀
      █▓▓▓█
      █▀▀▀█
       ▓▓▓
      ▄▓▓▓▄
    ▄▓▓███▓▓▄
   █▓▓▓▓▓▓▓▓▓█
    ▀▓▓▓▓▓▓▓▀
      █▓▓▓█
     ▐█   █▌
"""

_SCOUT_PORTRAIT = r"""
      ▄████▄
     ██░░░░██
     █░▀░░▀░█
      █░▄▄░█
       ████
      ▄▓▓▓▓▄
    ░▓▓▓▓▓▓▓▓░
     ▓▓░░░░▓▓
      ▓▓▓▓▓▓
       ▓▓▓▓
      ▓▓  ▓▓
      ▀▀  ▀▀
"""

_SENTINEL_PORTRAIT = r"""
     ▄▄█████▄▄
    █▓▓▓▓▓▓▓▓▓█
    █▓▓█▀▀█▓▓█
    █▓▓█▄▄█▓▓█
     ▀▓▓▓▓▓▓▀
      ▄████▄
    ██▓▓██▓▓██
   █▓▓▓▓██▓▓▓▓█
    ██▓▓▓▓▓▓██
     ▀██████▀
      █▓  ▓█
      ▀▀  ▀▀
"""


# ── Character registry ──────────────────────────────────────────────

CHARACTERS: tuple[Character, ...] = (
    Character(
        key="knight",
        name="Knight",
        title="The Shield",
        catchphrase="No vulnerability passes my guard.",
        portrait=_KNIGHT_PORTRAIT.strip("\n"),
        accent_color="bright_cyan",
        glyph="♞",
    ),
    Character(
        key="rogue",
        name="Rogue",
        title="The Shadow",
        catchphrase="I find what others overlook.",
        portrait=_ROGUE_PORTRAIT.strip("\n"),
        accent_color="bright_green",
        glyph="♦",
    ),
    Character(
        key="mage",
        name="Mage",
        title="The Cipher",
        catchphrase="Every secret has a pattern.",
        portrait=_MAGE_PORTRAIT.strip("\n"),
        accent_color="bright_yellow",
        glyph="★",
    ),
    Character(
        key="scout",
        name="Scout",
        title="The Pathfinder",
        catchphrase="First to the breach, first to report.",
        portrait=_SCOUT_PORTRAIT.strip("\n"),
        accent_color="bright_red",
        glyph="▸",
    ),
    Character(
        key="sentinel",
        name="Sentinel",
        title="The Warden",
        catchphrase="I watch so others don't have to.",
        portrait=_SENTINEL_PORTRAIT.strip("\n"),
        accent_color="bright_blue",
        glyph="◆",
    ),
)

_BY_KEY: dict[str, Character] = {c.key: c for c in CHARACTERS}
DEFAULT_CHARACTER = CHARACTERS[0]


def get_character(key: str | None) -> Character:
    """Look up a character by key, falling back to the default."""
    if key is None:
        return DEFAULT_CHARACTER
    return _BY_KEY.get(key, DEFAULT_CHARACTER)


def all_characters() -> tuple[Character, ...]:
    return CHARACTERS
