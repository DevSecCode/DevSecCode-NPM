"""Terminal animations for game-like feedback.

Scan progress spinner, level-up fanfare, boss encounter intro, and
achievement unlock flash. All animations write to stderr and use
Rich's Live display for smooth rendering. Each one is short (1-3s)
so the UX stays snappy.

Sound effects use the terminal bell character (\\a). Most terminals
play a system beep or a visual flash; those that silence it simply
ignore it. No external audio dependencies.
"""

from __future__ import annotations

import sys
import time
from typing import Iterable

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from dsc.gamification.deva import ACCENT_COLOR


def _err_console() -> Console:
    return Console(file=sys.stderr, highlight=False)


def _bell() -> None:
    """Play the terminal bell — a system beep or visual flash."""
    sys.stderr.write("\a")
    sys.stderr.flush()


# ── Scan progress ────────────────────────────────────────────────────

_SCAN_PHASES = [
    "Initializing perimeter scan...",
    "Loading detection rules...",
    "Scanning source files...",
    "Matching patterns...",
    "Analyzing import graph...",
    "Correlating findings...",
    "Building encounter map...",
]

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def render_scan_progress(
    *,
    phase_count: int = 7,
    accent_color: str = ACCENT_COLOR,
) -> None:
    """Animated scan progress with rotating spinner and phase messages.

    Called before the actual scan starts. Each phase is ~0.25s so the
    whole animation takes ~1.75s — fast enough not to annoy, slow enough
    to feel like something is happening.
    """
    console = _err_console()
    phases = _SCAN_PHASES[:phase_count]

    try:
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            for i, phase in enumerate(phases):
                progress = int(((i + 1) / len(phases)) * 100)
                bar_filled = int(progress / 5)
                bar = "█" * bar_filled + "░" * (20 - bar_filled)

                for frame_idx in range(6):  # ~0.25s per phase at 24fps
                    spinner = _SPINNER_FRAMES[frame_idx % len(_SPINNER_FRAMES)]
                    text = Text()
                    text.append(f"  {spinner} ", style=f"bold {accent_color}")
                    text.append(phase, style=f"italic {accent_color}")
                    text.append(f"\n  [{bar}] {progress}%", style="dim")
                    live.update(text)
                    time.sleep(0.04)
    except Exception:
        # If Live display fails (non-TTY, etc.), just skip silently.
        pass


# ── Level-up animation ───────────────────────────────────────────────

_LEVEL_UP_FRAMES = [
    r"""
        ╔══════════════════╗
        ║                  ║
        ║    LEVEL  UP!    ║
        ║                  ║
        ╚══════════════════╝
    """,
    r"""
       ╔════════════════════╗
       ║  ·  ·  ·  ·  ·  · ║
       ║  ·  LEVEL  UP! ·  ║
       ║  ·  ·  ·  ·  ·  · ║
       ╚════════════════════╝
    """,
    r"""
      ╔══════════════════════╗
      ║ * · * · * · * · * · ║
      ║ ·  ★ LEVEL  UP! ★  ║
      ║ * · * · * · * · * · ║
      ╚══════════════════════╝
    """,
    r"""
     ╔════════════════════════╗
     ║ ★ * ★ * ★ * ★ * ★ * ★║
     ║ * ★  ★ LEVEL UP! ★  *║
     ║ ★ * ★ * ★ * ★ * ★ * ★║
     ╚════════════════════════╝
    """,
    r"""
      ╔══════════════════════╗
      ║ * · * · * · * · * · ║
      ║ ·  ★ LEVEL  UP! ★  ║
      ║ * · * · * · * · * · ║
      ╚══════════════════════╝
    """,
]


def render_level_up(
    *,
    old_level: int,
    new_level: int,
    accent_color: str = ACCENT_COLOR,
) -> None:
    """Animated level-up fanfare with expanding border and sparkles."""
    console = _err_console()
    _bell()

    try:
        with Live(console=console, refresh_per_second=8, transient=True) as live:
            for i, frame_str in enumerate(_LEVEL_UP_FRAMES):
                text = Text()
                text.append(frame_str.rstrip(), style=f"bold bright_yellow")
                text.append(f"\n        Lvl {old_level} → Lvl {new_level}", style=f"bold {accent_color}")
                live.update(text)
                time.sleep(0.3)
    except Exception:
        pass

    # Final static display
    final = Text()
    final.append("  ★ LEVEL UP! ★", style="bold bright_yellow")
    final.append(f"  Lvl {old_level} → Lvl {new_level}", style=f"bold {accent_color}")
    console.print(final)


# ── Boss encounter ───────────────────────────────────────────────────

_BOSS_INTRO_FRAMES = [
    "  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░",
    "  ░░░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░",
    "  ░░▓▓██████████████████▓▓░░░░",
    "  ░▓████████████████████████▓░",
    "  ▓██████████████████████████▓",
]

_BOSS_SKULL = r"""
        ▄▄▄████████▄▄▄
      ▄██████████████████▄
    ▄████▀▀▀████████▀▀▀████▄
   ████▀     ▀████▀     ▀████
  █████       ████       █████
  █████▄     ▄████▄     ▄█████
   ████████████▀▀████████████
    ▀████▀▀▄████████▄▀▀████▀
      ▀█▄  ▀▀▀▀▀▀▀▀  ▄█▀
        ▀████████████████▀
"""


def render_boss_encounter(
    enemy_name: str,
    *,
    accent_color: str = "bold red",
) -> None:
    """Dramatic intro for CRITICAL severity findings."""
    console = _err_console()
    _bell()
    _bell()

    try:
        with Live(console=console, refresh_per_second=10, transient=True) as live:
            # Fade-in effect
            for frame in _BOSS_INTRO_FRAMES:
                text = Text()
                text.append("\n" + frame, style="bold red")
                live.update(text)
                time.sleep(0.15)

            # Show skull
            text = Text()
            text.append(_BOSS_SKULL.rstrip(), style="bold red")
            text.append(f"\n\n    !! BOSS ENCOUNTER !!", style="bold bright_red")
            text.append(f"\n    {enemy_name}", style=f"bold bright_yellow")
            live.update(text)
            time.sleep(1.2)
    except Exception:
        pass

    # Static fallback
    boss_text = Text()
    boss_text.append("\n  !! BOSS ENCOUNTER !! ", style="bold white on red")
    boss_text.append(f"  {enemy_name}", style="bold bright_red")
    console.print(boss_text)


# ── Achievement unlock ───────────────────────────────────────────────

def render_achievement_unlock(
    title: str,
    description: str,
    glyph: str = "*",
    *,
    accent_color: str = "bright_yellow",
) -> None:
    """Brief flash animation when an achievement unlocks."""
    console = _err_console()
    _bell()

    frames = [
        f"  [ {glyph} ] {title}",
        f"  [*{glyph}*] {title}",
        f"  [**{glyph}**] {title}",
        f"  [*{glyph}*] {title}",
        f"  [ {glyph} ] {title}",
    ]

    try:
        with Live(console=console, refresh_per_second=8, transient=True) as live:
            for frame in frames:
                text = Text()
                text.append("  ACHIEVEMENT UNLOCKED\n", style=f"bold {accent_color}")
                text.append(frame, style=f"bold {accent_color}")
                live.update(text)
                time.sleep(0.2)
    except Exception:
        pass

    # Static result
    result = Text()
    result.append(f"  {glyph} ", style=f"bold {accent_color}")
    result.append(title, style="bold")
    result.append(f" — {description}", style="dim")
    console.print(result)


# ── Shield score count-up ───────────────────────────────────────────

def render_shield_countup(
    score: int,
    letter: str,
    stars: str,
    *,
    accent_color: str = ACCENT_COLOR,
) -> None:
    """Arcade-style score counting from 0 to final value.

    The number ticks up fast at first, then decelerates near the target
    like a slot machine settling. Takes ~1.2s total.
    """
    console = _err_console()

    try:
        with Live(console=console, refresh_per_second=20, transient=True) as live:
            # Generate tick sequence: fast start, slow finish.
            steps = []
            current = 0
            while current < score:
                remaining = score - current
                step = max(1, remaining // 4)
                current = min(current + step, score)
                steps.append(current)

            for val in steps:
                text = Text()
                text.append("  SHIELD    ", style="dim")
                partial_stars = "*" * int((val / max(score, 1)) * stars.count("*"))
                partial_stars = partial_stars.ljust(5)
                text.append(partial_stars, style="bold bright_yellow")
                text.append(f"  {val}/100", style="bold")
                live.update(text)
                time.sleep(0.06)

            # Final frame with rank reveal.
            _bell()
            text = Text()
            text.append("  SHIELD    ", style="dim")
            text.append(stars, style="bold bright_yellow")
            text.append(f"  {score}/100", style="bold")
            text.append(f"  ·  Rank {letter}", style=f"bold {accent_color}")
            live.update(text)
            time.sleep(0.4)
    except Exception:
        pass


# ── XP gain ticker ──────────────────────────────────────────────────

def render_xp_gain(
    *,
    xp_before: int,
    xp_after: int,
    xp_delta: int,
    level_before: int,
    level_after: int,
    xp_per_level: int = 100,
    accent_color: str = ACCENT_COLOR,
) -> None:
    """XP bar filling up with +XP floating beside it."""
    console = _err_console()

    try:
        with Live(console=console, refresh_per_second=15, transient=True) as live:
            steps = min(xp_delta, 20)  # Cap animation frames.
            for i in range(steps + 1):
                frac = i / max(steps, 1)
                current_xp = int(xp_before + xp_delta * frac)
                xp_into = current_xp % xp_per_level
                bar_pct = int(xp_into * 100 / xp_per_level)
                filled = int(round((bar_pct / 100.0) * 15))
                bar = "█" * filled + "░" * (15 - filled)

                text = Text()
                text.append("  XP  ", style="dim")
                text.append(bar, style="bright_yellow")
                text.append(f"  {xp_into}/{xp_per_level}", style="bold")
                text.append(f"   +{int(xp_delta * frac)}", style="bright_yellow")
                live.update(text)
                time.sleep(0.04)

            # Hold final state.
            time.sleep(0.3)
    except Exception:
        pass


# ── Defense bars animated fill ──────────────────────────────────────

def render_defense_bars_fill(
    categories_data: list[tuple[str, int, str]],
    *,
    accent_color: str = ACCENT_COLOR,
) -> None:
    """Each defense bar fills left-to-right one by one.

    categories_data is a list of (label, percent, color_style) tuples.
    """
    console = _err_console()

    def _make_frame(filled_cats: int, partial_pct: int = 100) -> Text:
        text = Text()
        text.append("  DEFENSE BREAKDOWN\n", style="bold dim")
        for idx, (label, percent, color) in enumerate(categories_data):
            if idx < filled_cats:
                show_pct = percent
            elif idx == filled_cats:
                show_pct = int(percent * partial_pct / 100)
            else:
                show_pct = 0
            filled = int(round((show_pct / 100.0) * 10))
            bar = "█" * filled + "░" * (10 - filled)
            text.append(f"  {label:<14} ", style="dim")
            text.append(bar, style=color if idx <= filled_cats else "dim")
            text.append(f" {show_pct}%\n", style="dim")
        return text

    try:
        with Live(console=console, refresh_per_second=15, transient=True) as live:
            for cat_idx in range(len(categories_data)):
                for step in range(0, 101, 20):
                    live.update(_make_frame(cat_idx, min(step, 100)))
                    time.sleep(0.03)
            # Hold final frame.
            live.update(_make_frame(len(categories_data)))
            time.sleep(0.3)
    except Exception:
        pass


# ── Encounter intro ─────────────────────────────────────────────────

_ENCOUNTER_APPEAR_FRAMES = [
    "░░░░░░░░░░░░░░░░░░░░",
    "░░▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░",
    "░▓██████████████▓░░░",
    "▓████████████████▓░░",
]

def render_encounter_intro(
    enemy_name: str,
    severity_name: str,
    *,
    index: int,
    total: int,
    severity_color: str = "red",
) -> None:
    """Brief dramatic reveal when an encounter appears.

    The enemy name types in character by character, then the HP bar fills.
    Takes ~0.8s.
    """
    console = _err_console()

    try:
        with Live(console=console, refresh_per_second=20, transient=True) as live:
            # Fade-in bars.
            for frame in _ENCOUNTER_APPEAR_FRAMES:
                text = Text()
                text.append(f"  {frame}", style=f"bold {severity_color}")
                live.update(text)
                time.sleep(0.06)

            # Type enemy name character by character.
            header = f"  Encounter {index}/{total}  ·  {severity_name}  ·  "
            for i in range(len(enemy_name) + 1):
                text = Text()
                text.append(header, style="bold")
                text.append(enemy_name[:i], style=f"bold {severity_color}")
                text.append("█", style=f"bold {severity_color}")  # Cursor.
                live.update(text)
                time.sleep(0.03)

            # Final frame without cursor.
            text = Text()
            text.append(header, style="bold")
            text.append(enemy_name, style=f"bold {severity_color}")
            live.update(text)
            time.sleep(0.2)
    except Exception:
        pass


# ── Victory / defeat splash ────────────────────────────────────────

_VICTORY_FRAMES = [
    r"""
         ╔═══════════╗
         ║  VICTORY  ║
         ╚═══════════╝
    """,
    r"""
       ╔═══════════════╗
       ║ · · VICTORY · ║
       ╚═══════════════╝
    """,
    r"""
     ╔═══════════════════╗
     ║ * ★  VICTORY  ★ * ║
     ╚═══════════════════╝
    """,
    r"""
    ╔═════════════════════╗
    ║ ★ * ★  VICTORY ★ * ★║
    ╚═════════════════════╝
    """,
    r"""
     ╔═══════════════════╗
     ║ * ★  VICTORY  ★ * ║
     ╚═══════════════════╝
    """,
]

_DEFEAT_FRAMES = [
    r"""
         ╔══════════╗
         ║  DEFEAT  ║
         ╚══════════╝
    """,
    r"""
        ╔════════════╗
        ║ ·  DEFEAT  ║
        ╚════════════╝
    """,
    r"""
       ╔══════════════╗
       ║ ×  DEFEAT  × ║
       ╚══════════════╝
    """,
    r"""
        ╔════════════╗
        ║ ·  DEFEAT  ║
        ╚════════════╝
    """,
    r"""
       ╔══════════════╗
       ║ ×  DEFEAT  × ║
       ╚══════════════╝
    """,
]


def render_victory(*, accent_color: str = "bright_green") -> None:
    """Expanding sparkle animation for quest success."""
    console = _err_console()
    _bell()

    try:
        with Live(console=console, refresh_per_second=8, transient=True) as live:
            for frame_str in _VICTORY_FRAMES:
                text = Text(frame_str.rstrip(), style=f"bold {accent_color}")
                live.update(text)
                time.sleep(0.25)
    except Exception:
        pass

    final = Text()
    final.append("  ★ QUEST COMPLETE ★", style=f"bold {accent_color}")
    console.print(final)


def render_defeat(*, accent_color: str = "red") -> None:
    """Shaking border animation for quest failure."""
    console = _err_console()
    _bell()
    _bell()

    try:
        with Live(console=console, refresh_per_second=8, transient=True) as live:
            for frame_str in _DEFEAT_FRAMES:
                text = Text(frame_str.rstrip(), style=f"bold {accent_color}")
                live.update(text)
                time.sleep(0.25)
    except Exception:
        pass

    final = Text()
    final.append("  × QUEST FAILED ×", style=f"bold {accent_color}")
    console.print(final)


# ── Loot chest opening ─────────────────────────────────────────────

_CHEST_CLOSED = r"""
        ┌──────────┐
        │ ╔══════╗ │
        │ ║ LOOT ║ │
        │ ╚══════╝ │
        └──────────┘
"""

_CHEST_OPENING = [
    r"""
        ┌──────────┐
        │ ╔══════╗ │
        │ ║ LOOT ║ │
        │ ╚══════╝ │
        └──────────┘
    """,
    r"""
       ╱──────────────╲
        ┌──────────┐
        │ ╔══════╗ │
        │ ║ LOOT ║ │
        │ ╚══════╝ │
        └──────────┘
    """,
    r"""
      ╱                ╲
     ╱  ·  ·  ·  ·  ·  ╲
        ┌──────────┐
        │ ╔══════╗ │
        │ ║ LOOT ║ │
        └──────────┘
    """,
    r"""
     ╱    *  ·  *  ·    ╲
    ╱  ·  ★  ·  ★  ·  ·  ╲
        ┌──────────┐
        │ ╔══════╗ │
        │ ║ ◆◆◆◆ ║ │
        └──────────┘
    """,
    r"""
         ★  *  ★  *
       *  ·  ★  ·  *
    ╱  ★  ·  ★  ·  ★  ·  ╲
        ┌──────────┐
        │ ╔══════╗ │
        │ ║ ◆◆◆◆ ║ │
        └──────────┘
    """,
]


def render_loot_drop(
    loot_name: str,
    loot_desc: str = "",
    *,
    accent_color: str = "bright_cyan",
) -> None:
    """Pixel-art chest opening animation for loot drops."""
    console = _err_console()
    _bell()

    try:
        with Live(console=console, refresh_per_second=6, transient=True) as live:
            for frame_str in _CHEST_OPENING:
                text = Text()
                text.append(frame_str.rstrip(), style=f"bold {accent_color}")
                text.append(f"\n\n  LOOT DROP!", style=f"bold bright_yellow")
                live.update(text)
                time.sleep(0.3)

            # Final reveal.
            text = Text()
            text.append(_CHEST_OPENING[-1].rstrip(), style=f"bold {accent_color}")
            text.append(f"\n\n  ◆ {loot_name}", style=f"bold {accent_color}")
            if loot_desc:
                text.append(f"\n  {loot_desc}", style="dim")
            live.update(text)
            time.sleep(0.8)
    except Exception:
        pass

    result = Text()
    result.append(f"  ◆ {loot_name}", style=f"bold {accent_color}")
    if loot_desc:
        result.append(f" — {loot_desc}", style="dim")
    console.print(result)


# ── Streak fire ─────────────────────────────────────────────────────

_FIRE_FRAMES = [
    r"""
       (  )
      (    )
       (  )
        )(
       |  |
    """,
    r"""
      (    )
     (  ()  )
      (    )
       )(
       |  |
    """,
    r"""
     (  ()  )
    (  (  )  )
     (  ()  )
       )(
       |  |
    """,
    r"""
    (  (  )  )
   ( (  ()  ) )
    (  (  )  )
       ()
       |  |
    """,
    r"""
     (  ()  )
    (  (  )  )
     (  ()  )
       )(
       |  |
    """,
]


def render_streak_fire(
    streak: int,
    *,
    accent_color: str = "bright_yellow",
) -> None:
    """Animated fire for 7+ day streaks."""
    console = _err_console()

    try:
        with Live(console=console, refresh_per_second=8, transient=True) as live:
            for frame_str in _FIRE_FRAMES:
                text = Text()
                text.append(frame_str.rstrip(), style="bold bright_red")
                text.append(f"\n      {streak}-DAY STREAK!", style=f"bold {accent_color}")
                live.update(text)
                time.sleep(0.2)
            time.sleep(0.3)
    except Exception:
        pass

    result = Text()
    result.append(f"  STREAK {streak} days", style=f"bold {accent_color}")
    console.print(result)


# ── Damage number pop ───────────────────────────────────────────────

def render_damage_number(
    penalty: int,
    severity_name: str,
    *,
    accent_color: str = "red",
) -> None:
    """Floating damage number that drifts upward — like an RPG hit.

    Shows something like:
        -25 HP
         CRITICAL
    The text starts low and "floats" up over ~0.6s.
    """
    if penalty <= 0:
        return

    console = _err_console()

    _FLOAT_POSITIONS = [
        (4, "dim"),
        (3, accent_color),
        (2, f"bold {accent_color}"),
        (1, f"bold {accent_color}"),
        (0, f"bold {accent_color}"),
        (0, accent_color),
        (0, "dim"),
    ]

    try:
        with Live(console=console, refresh_per_second=12, transient=True) as live:
            for pad, style in _FLOAT_POSITIONS:
                text = Text()
                text.append("\n" * pad)
                text.append(f"    -{penalty} HP", style=style)
                text.append(f"  {severity_name}", style="dim")
                live.update(text)
                time.sleep(0.08)
    except Exception:
        pass
