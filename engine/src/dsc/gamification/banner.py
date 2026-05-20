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
from typing import Iterable

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dsc.gamification.deva import (
    ACCENT_COLOR,
    CATCHPHRASE,
    GLOW_COLOR,
    VOICE,
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
    line = Text()
    line.append("Deva", style=f"bold {ACCENT_COLOR}")
    line.append(" · ", style="dim")
    line.append(f"Lvl {level}", style="bold")
    line.append(f" ({xp_into}/100 XP)", style="dim")
    line.append("  ·  ", style="dim")
    line.append(f"Hunts: {profile.hunts_completed}", style="dim")
    if profile.achievements:
        line.append("  ·  ", style="dim")
        line.append(f"Achievements: {len(profile.achievements)}", style="dim")
    return line


def render_play_banner(profile: Profile) -> None:
    """Big banner for the interactive `devseccode` play menu entry."""
    console = _err_console()
    body = Text()
    body.append(_WORDMARK.strip("\n"), style=f"bold {ACCENT_COLOR}")
    body.append("\n")
    body.append("Gamified local security CLI  ·  Public Campaign  ·  ", style="dim")
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

    header = Text()
    header.append("HUNT STARTED ", style=f"bold white on {ACCENT_COLOR}")
    header.append("  ", style="dim")
    header.append("Deva", style=f"bold {ACCENT_COLOR}")
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
