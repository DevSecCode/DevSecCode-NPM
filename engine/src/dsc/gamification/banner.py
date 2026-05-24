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


# Smaller orb for the HUD layout — properly circular at terminal aspect ratio.
# Terminal chars are ~2:1 height:width, so 15 wide × 7 tall ≈ circle.
_SMALL_ORB = """\
      · • ·
    · • • • ·
  • • • • • • •
  • • • • • • •
  • • • • • • •
    · • • • ·
      · • ·"""


def _compact_portrait(text: str, max_width: int = 18) -> str:
    """Return a HUD-sized portrait. Wide portraits (like Deva's full orb)
    get swapped for a smaller, properly proportioned version."""
    lines = text.split("\n")
    widest = max((len(l) for l in lines), default=0)
    if widest <= max_width:
        return text
    return _SMALL_ORB


def _animate_play_banner(profile: Profile, console: Console) -> None:
    """Animated banner: Deva orb grows → pulse → DEVSECCODE sweeps in."""
    wordmark_lines = _WORDMARK.strip("\n").split("\n")
    char = get_character(profile.hunter_class)
    subtitle = f"Local security CLI, DevSecCode LITE  ·  Public Campaign  ·  v{__version__}"
    orb_lines = deva_portrait().split("\n")
    full_orb = "\n".join(orb_lines)

    def _orb_panel(style: str, border: str) -> Panel:
        return Panel(Align.center(Text(full_orb, style=style)),
                     border_style=border, padding=(1, 2))

    def _wm_panel(body: Text) -> Panel:
        return Panel(Align.left(body), border_style=ACCENT_COLOR, padding=(1, 2),
                     title=Text("DEVSECCODE", style=f"bold {ACCENT_COLOR}"),
                     title_align="left")

    # Measure orb panel height for cursor-based redraws.
    import io as _io
    _buf = _io.StringIO()
    Console(file=_buf, force_terminal=True, width=console.width,
            highlight=False).print(_orb_panel(ACCENT_COLOR, ACCENT_COLOR))
    _ph = _buf.getvalue().count("\n")

    try:
        # Phase 1: Orb grows from center outward.
        with Live(console=console, refresh_per_second=30, transient=True) as live:
            mid = len(orb_lines) // 2
            for radius in range(1, mid + 2):
                start = max(0, mid - radius)
                end = min(len(orb_lines), mid + radius)
                visible = orb_lines[start:end]
                pad_top = [""] * start
                pad_bot = [""] * (len(orb_lines) - end)
                body = Text("\n".join(pad_top + visible + pad_bot),
                            style=f"bold {ACCENT_COLOR}")
                live.update(Panel(Align.center(body),
                                  border_style=ACCENT_COLOR, padding=(1, 2)))
                time.sleep(0.08)
            time.sleep(0.1)

        # Phase 1b: Orb rotation — shift dot density pattern to simulate spin.
        # Replace dots based on a moving "phase" offset: dots near the phase
        # column become ● (big), others become · (small), creating visible motion.
        def _rotated_frame(lines: list[str], phase: int) -> Text:
            body = Text()
            for li, row in enumerate(lines):
                if li > 0:
                    body.append("\n")
                for ci, ch in enumerate(row):
                    if ch in ("·", "•"):
                        dist = abs(ci - phase)
                        if dist <= 4:
                            body.append("●", style="bold bright_white")
                        elif dist <= 8:
                            body.append("•", style=f"bold {ACCENT_COLOR}")
                        else:
                            body.append("·", style=f"{ACCENT_COLOR}")
                    else:
                        body.append(ch)
            return body

        # Find dot column range.
        dot_cols = []
        for row in orb_lines:
            dot_cols.extend(i for i, c in enumerate(row) if c in ("·", "•"))
        cmin = min(dot_cols) if dot_cols else 0
        cmax = max(dot_cols) if dot_cols else 26

        # Sweep right then left.
        sweep = list(range(cmin, cmax + 1, 2)) + list(range(cmax, cmin - 1, -2))
        for phase in sweep:
            sys.stderr.write(f"\033[{_ph}A")
            sys.stderr.flush()
            body = _rotated_frame(orb_lines, phase)
            console.print(Panel(Align.center(body),
                                border_style=ACCENT_COLOR, padding=(1, 2)))
            time.sleep(0.03)

        # Clear pulse frame.
        sys.stderr.write(f"\033[{_ph}A\033[J")
        sys.stderr.flush()

        # Phases 2-5: wordmark sweep, subtitle, stats, catchphrase.
        with Live(console=console, refresh_per_second=30, transient=True) as live:
            # Phase 2: DEVSECCODE sweeps in column by column.
            max_width = max(len(line) for line in wordmark_lines)
            for col in range(0, max_width + 3, 3):
                body = Text("\n".join(line[:col] for line in wordmark_lines),
                            style=f"bold {ACCENT_COLOR}")
                live.update(_wm_panel(body))
                time.sleep(0.025)
            time.sleep(0.2)

            # Phase 3: Subtitle types in.
            for i in range(0, len(subtitle) + 1, 3):
                body = Text()
                body.append("\n".join(wordmark_lines), style=f"bold {ACCENT_COLOR}")
                body.append("\n")
                body.append(subtitle[:i], style="dim")
                body.append("█", style=f"bold {ACCENT_COLOR}")
                live.update(_wm_panel(body))
                time.sleep(0.02)

            # Phase 4: Stats count up.
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
                body.append(f"Lvl {int(profile.level * frac)}", style="bold")
                body.append("  ·  ", style="dim")
                body.append(f"Hunts: {int(profile.hunts_completed * frac)}", style="dim")
                if profile.achievements:
                    body.append("  ·  ", style="dim")
                    body.append(f"Achievements: {int(len(profile.achievements) * frac)}", style="dim")
                live.update(_wm_panel(body))
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
                live.update(_wm_panel(body))
                time.sleep(0.02)
            time.sleep(0.2)
    except Exception:
        pass


def render_play_banner(profile: Profile, *, animate: bool = True) -> None:
    """Big banner for the interactive `devseccode` play menu entry."""
    console = _err_console()

    if animate and sys.stderr.isatty():
        _animate_play_banner(profile, console)

    # Always print the final static version — game HUD style.
    from rich.columns import Columns

    char = get_character(profile.hunter_class)
    portrait_text, portrait_color = active_portrait(profile.hunter_class)

    # Compact wide portraits (e.g. Deva orb) for side-by-side layout.
    portrait_text = _compact_portrait(portrait_text)

    # Left column: portrait in a bordered frame
    portrait = Text(portrait_text, style=f"bold {portrait_color}")

    # Right column: wordmark + stats
    right = Text()
    right.append(_WORDMARK.strip("\n"), style=f"bold {ACCENT_COLOR}")
    right.append("\n")
    right.append("Local security CLI, DevSecCode LITE  ·  Public Campaign  ·  ", style="dim")
    right.append(f"v{__version__}", style="bold")

    # XP progress bar
    xp = profile.xp_into_level
    filled = int(xp / 100 * 20)
    empty = 20 - filled
    right.append("\n\n")
    right.append(f"  {char.glyph} {char.name}", style=f"bold {char.accent_color}")
    right.append(f"  Lvl {profile.level}", style="bold")
    right.append("\n  ")
    right.append("█" * filled, style=f"bold {char.accent_color}")
    right.append("░" * empty, style="dim")
    right.append(f"  {xp}/100 XP", style="dim")

    # Status indicators
    right.append("\n  ")
    right.append(f"⚡ {profile.hunts_completed} hunts", style="bold")
    if profile.current_streak > 1:
        right.append(f"  🔥 {profile.current_streak}d streak", style="bold bright_yellow")
    if profile.achievements:
        right.append(f"  ★ {len(profile.achievements)} achievements", style="bold bright_yellow")
    if profile.loot:
        right.append(f"  ◆ {len(profile.loot)} loot", style="bold bright_cyan")

    right.append("\n\n")
    right.append(f"  \"{CATCHPHRASE}\"", style=f"italic {ACCENT_COLOR}")

    layout = Columns([portrait, right], equal=False, expand=False, padding=(0, 3))

    console.print(
        Panel(
            layout,
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
