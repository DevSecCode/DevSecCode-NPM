"""ASCII banner art for the play menu and hunt start.

Flamebird-style box banner with stylized DEVSECCODE wordmark, plus a
status line pulled from the profile. Deva appears as a single fixed
personality, so the status line includes Deva's mark rather than a
class identity.

Banners go to stderr because they're presentation chrome — keeping them
off stdout means `devseccode scan . | jq ...` (or any pipe consumer)
still sees clean structured output.
"""

from __future__ import annotations

import sys
import time
from typing import Iterable

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from dsc.gamification.characters import get_character
from dsc.gamification.deva import (
    ACCENT_COLOR,
    CATCHPHRASE,
    GLOW_COLOR,
    VOICE,
    active_name,
    active_portrait,
    deva_portrait,
)
from dsc.gamification.profile import Profile
from dsc.version import __version__


_WORDMARK = r"""
 ____  _____ _   _ ____  _____ ____  ____ ___  ____  _____
|  _ \| ____| | | / ___|| ____/ ___|/ ___/ _ \|  _ \| ____|
| | | |  _| | | | \___ \|  _|| |   | |  | | | | | | |  _|
| |_| | |___| |_| |___) | |__| |___| |__| |_| | |_| | |___
|____/|_____|\___/|____/|_____\____|\____\___/|____/|_____|
"""

def _err_console() -> Console:
    """Stderr console, color-on whenever stderr is a TTY."""
    return Console(file=sys.stderr, highlight=False)


def _status_line(profile: Profile) -> Text:
    level = profile.level
    xp_into = profile.xp_into_level
    char = get_character(profile.hunter_class)
    line = Text()
    line.append(f"{char.glyph} {char.name}", style=f"bold {char.accent_color}")
    line.append(" · ", style="dim")
    line.append(f"Lvl {level}", style="bold")
    line.append(f" ({xp_into}/100 XP)", style="dim")
    line.append("  ·  ", style="dim")
    line.append(f"Hunts: {profile.hunts_completed}", style="dim")
    if profile.achievements:
        line.append("  ·  ", style="dim")
        line.append(f"Achievements: {len(profile.achievements)}", style="dim")
    return line


def _animate_play_banner(profile: Profile, console: Console) -> None:
    """Animated banner: Deva orb grows → glow → DEVSECCODE sweeps in."""
    wordmark_lines = _WORDMARK.strip("\n").split("\n")
    char = get_character(profile.hunter_class)
    subtitle = f"Local security CLI, DevSecCode LITE  ·  Public Campaign  ·  v{__version__}"
    orb_lines = deva_portrait().split("\n")

    try:
        with Live(console=console, refresh_per_second=30, transient=True) as live:
            # Phase 1: Orb grows from center outward — materializing.
            mid = len(orb_lines) // 2
            for radius in range(1, mid + 2):
                start = max(0, mid - radius)
                end = min(len(orb_lines), mid + radius)
                visible = orb_lines[start:end]
                pad_top = [""] * start
                pad_bot = [""] * (len(orb_lines) - end)
                body = Text("\n".join(pad_top + visible + pad_bot),
                            style=f"bold {ACCENT_COLOR}")
                live.update(Panel(
                    Align.center(body),
                    border_style=ACCENT_COLOR,
                    padding=(1, 2),
                ))
                time.sleep(0.08)

            time.sleep(0.15)

            # Phase 1b: Orb rotates — highlight sweeps left to right.
            # Each orb line's dots get replaced by brightness tiers
            # based on distance from a moving "light column".
            _TIERS = (" ", "·", "•", "●", "•", "·")  # falloff curve

            def _rotated_orb(orb_src: list[str], light_col: int) -> str:
                out = []
                for row in orb_src:
                    chars = list(row)
                    dot_positions = [i for i, c in enumerate(chars) if c in ("·", "•")]
                    if not dot_positions:
                        out.append(row)
                        continue
                    for pos in dot_positions:
                        dist = abs(pos - light_col)
                        tier_idx = min(dist // 2, len(_TIERS) - 1)
                        chars[pos] = _TIERS[tier_idx]
                    out.append("".join(chars))
                return "\n".join(out)

            # Find the dot range to sweep across.
            all_dot_cols = []
            for row in orb_lines:
                all_dot_cols.extend(i for i, c in enumerate(row) if c in ("·", "•"))
            col_min = min(all_dot_cols) if all_dot_cols else 0
            col_max = max(all_dot_cols) if all_dot_cols else 30
            sweep_step = 2
            # Sweep right then left.
            sweep_cols = list(range(col_min, col_max + 1, sweep_step))
            sweep_cols += list(range(col_max, col_min - 1, -sweep_step))
            for lc in sweep_cols:
                rotated = _rotated_orb(orb_lines, lc)
                body = Text(rotated, style=f"bold {ACCENT_COLOR}")
                live.update(Panel(
                    Align.center(body),
                    border_style=ACCENT_COLOR,
                    padding=(1, 2),
                ))
                time.sleep(0.03)

            time.sleep(0.15)

            # Orb glow pulse — rapid color cycle.
            full_orb = "\n".join(orb_lines)
            for color in [GLOW_COLOR, "bright_white", ACCENT_COLOR]:
                body = Text(full_orb, style=f"bold {color}")
                live.update(Panel(
                    Align.center(body),
                    border_style=color,
                    padding=(1, 2),
                ))
                time.sleep(0.1)

            # Phase 2: DEVSECCODE sweeps in column by column.
            max_width = max(len(line) for line in wordmark_lines)
            step = 3
            for col in range(0, max_width + step, step):
                body = Text()
                body.append(
                    "\n".join(line[:col] for line in wordmark_lines),
                    style=f"bold {ACCENT_COLOR}",
                )
                live.update(Panel(
                    Align.left(body),
                    border_style=ACCENT_COLOR,
                    padding=(1, 2),
                    title=Text("DEVSECCODE", style=f"bold {ACCENT_COLOR}"),
                    title_align="left",
                ))
                time.sleep(0.025)

            time.sleep(0.2)

            # Phase 3: Subtitle types in with cursor.
            for i in range(0, len(subtitle) + 1, 3):
                body = Text()
                body.append("\n".join(wordmark_lines), style=f"bold {ACCENT_COLOR}")
                body.append("\n")
                body.append(subtitle[:i], style="dim")
                body.append("█", style=f"bold {ACCENT_COLOR}")
                live.update(Panel(
                    Align.left(body),
                    border_style=ACCENT_COLOR,
                    padding=(1, 2),
                    title=Text("DEVSECCODE", style=f"bold {ACCENT_COLOR}"),
                    title_align="left",
                ))
                time.sleep(0.02)

            # Phase 4: Stats count up from zero.
            target_level = profile.level
            target_hunts = profile.hunts_completed
            target_ach = len(profile.achievements)
            steps = 8
            for s in range(steps + 1):
                frac = s / steps
                body = Text()
                body.append("\n".join(wordmark_lines), style=f"bold {ACCENT_COLOR}")
                body.append("\n")
                body.append(subtitle, style="dim")
                body.append("\n\n")
                body.append(f"{char.glyph} {char.name}", style=f"bold {char.accent_color}")
                body.append(" · ", style="dim")
                body.append(f"Lvl {int(target_level * frac)}", style="bold")
                body.append("  ·  ", style="dim")
                body.append(f"Hunts: {int(target_hunts * frac)}", style="dim")
                if target_ach > 0:
                    body.append("  ·  ", style="dim")
                    body.append(f"Achievements: {int(target_ach * frac)}", style="dim")
                live.update(Panel(
                    Align.left(body),
                    border_style=ACCENT_COLOR,
                    padding=(1, 2),
                    title=Text("DEVSECCODE", style=f"bold {ACCENT_COLOR}"),
                    title_align="left",
                ))
                time.sleep(0.04)

            # Phase 5: Catchphrase types in.
            catchphrase = f"\"{CATCHPHRASE}\""
            for i in range(0, len(catchphrase) + 1, 2):
                body = Text()
                body.append("\n".join(wordmark_lines), style=f"bold {ACCENT_COLOR}")
                body.append("\n")
                body.append(subtitle, style="dim")
                body.append("\n\n")
                body.append(_status_line(profile))
                body.append("\n\n")
                body.append(catchphrase[:i], style=f"italic {ACCENT_COLOR}")
                live.update(Panel(
                    Align.left(body),
                    border_style=ACCENT_COLOR,
                    padding=(1, 2),
                    title=Text("DEVSECCODE", style=f"bold {ACCENT_COLOR}"),
                    title_align="left",
                ))
                time.sleep(0.02)

            time.sleep(0.2)
    except Exception:
        pass


def render_play_banner(profile: Profile, *, animate: bool = True) -> None:
    """Big banner for the interactive `devseccode` play menu entry."""
    console = _err_console()

    if animate and sys.stderr.isatty():
        _animate_play_banner(profile, console)

    # Always print the final static version.
    body = Text()
    body.append(_WORDMARK.strip("\n"), style=f"bold {ACCENT_COLOR}")
    body.append("\n")
    body.append("Local security CLI, DevSecCode LITE  ·  Public Campaign  ·  ", style="dim")
    body.append(f"v{__version__}", style="bold")
    body.append("\n\n")
    body.append(_status_line(profile))
    body.append("\n\n")
    body.append(f"\"{CATCHPHRASE}\"", style=f"italic {ACCENT_COLOR}")

    console.print(
        Panel(
            Align.left(body),
            border_style=ACCENT_COLOR,
            padding=(1, 2),
            title=Text("DEVSECCODE", style=f"bold {ACCENT_COLOR}"),
            title_align="left",
        )
    )


def render_hunt_banner(targets: Iterable, profile: Profile) -> None:
    """Compact banner shown when a hunt kicks off.

    Smaller than the play banner — kept to a few lines because hunts
    can be invoked from CI and we don't want huge fixed prelude noise.
    """
    console = _err_console()
    target_text = ", ".join(str(t) for t in targets) or "(empty)"

    char = get_character(profile.hunter_class)
    header = Text()
    header.append("HUNT STARTED ", style=f"bold white on {char.accent_color}")
    header.append("  ", style="dim")
    header.append(f"{char.glyph} {char.name}", style=f"bold {char.accent_color}")
    header.append("  ·  ", style="dim")
    header.append(f"Lvl {profile.level}", style="bold")
    if profile.hunts_completed == 0:
        header.append("  ·  ", style="dim")
        header.append("first hunt — earn the First Blood achievement", style="italic yellow")

    sub = Text()
    sub.append(f"Deva: ", style="dim")
    sub.append(VOICE.hunt_start, style=f"italic {ACCENT_COLOR}")
    sub.append("\n")
    sub.append("Targets: ", style="dim")
    sub.append(target_text, style="bold")

    console.print()
    console.print(header)
    console.print(sub)
    console.print()


def render_deva_card(*, console: Console | None = None) -> None:
    """Standalone Deva portrait card. Used by the stats view."""
    console = console or _err_console()
    body = Text()
    body.append(deva_portrait(), style=f"{ACCENT_COLOR}")
    body.append("\n\n")
    body.append("Deva", style=f"bold {ACCENT_COLOR}")
    body.append("\n")
    body.append(f"\"{CATCHPHRASE}\"", style=f"italic {GLOW_COLOR}")
    body.append("\n")
    body.append(
        "Your watcher. Always on the perimeter, always counting threats.",
        style="dim",
    )
    console.print(
        Panel(
            body,
            border_style=ACCENT_COLOR,
            padding=(1, 2),
        )
    )
