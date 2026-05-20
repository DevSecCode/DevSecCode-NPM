"""Gamification surface for the public devseccode CLI.

Banner art, Deva personality, encounter rendering, hunt summary card,
persistent hunter profile (XP/level/achievements), interactive play menu,
and exploratory code map. Imported lazily by `dsc.public_cli` so
non-gamified surfaces (scan --format sarif, list-rules) pay no
startup cost.
"""

from dsc.gamification.categories import DefenseCategory, classify_finding
from dsc.gamification.deva import (
    ACCENT_COLOR,
    CATCHPHRASE,
    GLOW_COLOR,
    PORTRAIT,
    VOICE,
    deva_color,
    deva_line,
    deva_portrait,
)

__all__ = [
    "DefenseCategory",
    "classify_finding",
    "ACCENT_COLOR",
    "CATCHPHRASE",
    "GLOW_COLOR",
    "PORTRAIT",
    "VOICE",
    "deva_color",
    "deva_line",
    "deva_portrait",
]
