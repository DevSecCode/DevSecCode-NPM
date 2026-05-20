"""Interactive play menu shown when `devseccode` runs with no args.

Flamebird-style "play" experience: arrow-key menu with the Deva banner
above it, leading to all the major surfaces (hunt, map, stats, init,
CI tip, IDE upsell).

questionary is bundled into the PyInstaller binary. If it fails to
import or stdin/stderr isn't a TTY, we fall back to the banner plus a
hint and exit 0 — never silently swallow the user's attempt.
"""

from __future__ import annotations

import sys
from typing import Callable

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from dsc.gamification import banner
from dsc.gamification.deva import ACCENT_COLOR, CATCHPHRASE, VOICE, deva_portrait
from dsc.gamification.profile import Profile, load_profile


def _err_console() -> Console:
    return Console(file=sys.stderr, highlight=False)


def _is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stderr.isatty()


def _clear_screen() -> None:
    """Reset the visible terminal so each menu cycle starts clean.

    questionary commits each prompt + selection to scrollback ("What
    would you like to do? Hunter Stats"), so without this the menu
    accumulates stale prompt lines as the user picks things. The
    scrollback isn't wiped — only the visible screen — so the player
    can still scroll up to see past hunts.
    """
    if not _is_interactive():
        return
    sys.stderr.write("\033[2J\033[H")  # ED2 + CUP(1,1): clear screen, cursor home
    sys.stderr.flush()


def _try_import_questionary():
    try:
        import questionary  # type: ignore
        return questionary
    except Exception:
        return None


def _print_non_interactive_help() -> None:
    console = _err_console()
    text = Text()
    text.append("Interactive mode unavailable", style="bold yellow")
    text.append(" (no TTY or questionary missing).\n", style="dim")
    text.append("Run a command directly:\n\n", style="dim")
    text.append("  devseccode hunt .\n", style="bold")
    text.append("  devseccode map .\n", style="bold")
    text.append("  devseccode quests\n", style="bold")
    text.append("  devseccode stats\n", style="bold")
    text.append("  devseccode scan . --format sarif --output devseccode.sarif\n", style="bold")
    text.append("\nSee `devseccode --help` for the full list.", style="dim")
    console.print(text)


# --- menu actions -----------------------------------------------------

def _action_start_hunt(questionary, run_hunt: Callable[[str], int]) -> int:
    target = questionary.text(
        "Target path to hunt:",
        default=".",
        qmark=">",
    ).ask()
    if target is None:
        return 0
    return run_hunt(target)


def _action_show_quests(show_quests: Callable[[], int]) -> int:
    show_quests()
    return 0


def _action_show_stats(profile: Profile) -> int:
    """Render the hunter stats panel — Deva portrait + profile + achievements."""
    from dsc.gamification import screens
    screens.show_stats(profile)
    return 0


def _action_init(run_init: Callable[[], int]) -> int:
    return run_init()


def _action_ci_mode() -> int:
    from dsc.gamification import screens
    screens.show_ci_mode()
    return 0


def _action_ide_upsell(run_ide: Callable[[], int]) -> int:
    return run_ide()


# --- top-level entrypoint --------------------------------------------

def run_play_menu(
    *,
    run_hunt: Callable[[str], int],
    run_init: Callable[[], int],
    show_quests: Callable[[], int],
    run_ide: Callable[[], int],
) -> int:
    """Render the play banner + interactive menu loop.

    Callbacks are injected so the menu has no import cycle with
    public_cli (it only needs the action verbs, not the argument
    parsing machinery).
    """
    profile = load_profile()
    if not _is_interactive():
        banner.render_play_banner(profile)
        _print_non_interactive_help()
        return 0

    questionary = _try_import_questionary()
    if questionary is None:
        banner.render_play_banner(profile)
        _print_non_interactive_help()
        return 0

    while True:
        # Each cycle starts clean: clear, redraw banner with fresh stats,
        # then prompt. This stops questionary's "What would you like to
        # do? <choice>" echo from stacking up across selections.
        _clear_screen()
        banner.render_play_banner(profile)

        if profile.hunts_completed == 0:
            intro = Text()
            intro.append("Deva: ", style="dim")
            intro.append(
                "I'll watch the perimeter. Pick a path to begin.",
                style=f"italic {ACCENT_COLOR}",
            )
            _err_console().print(intro)

        choice = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Choice(title="Start Hunt — scan and explore a target", value="hunt"),
                questionary.Choice(title="Quest Map — what the public ruleset catches", value="quests"),
                questionary.Choice(title="Hunter Stats — your profile, level, achievements", value="stats"),
                questionary.Separator(),
                questionary.Choice(title="Init Config — drop .dsc.yml in the current directory", value="init"),
                questionary.Choice(title="CI Mode — copy a CI-friendly command", value="ci"),
                questionary.Choice(title="DevSecCode IDE — what the full product adds", value="ide"),
                questionary.Separator(),
                questionary.Choice(title="Exit", value="exit"),
            ],
            qmark=">",
            use_arrow_keys=True,
            use_shortcuts=False,
        ).ask()

        if choice is None or choice == "exit":
            text = Text()
            text.append("Deva: ", style="dim")
            text.append(VOICE.exit_hunt, style=f"italic {ACCENT_COLOR}")
            _err_console().print(text)
            return 0

        try:
            if choice == "hunt":
                _action_start_hunt(questionary, run_hunt)
                profile = load_profile()  # XP may have changed
            elif choice == "quests":
                _action_show_quests(show_quests)
            elif choice == "stats":
                _action_show_stats(profile)
            elif choice == "init":
                _action_init(run_init)
            elif choice == "ci":
                _action_ci_mode()
            elif choice == "ide":
                _action_ide_upsell(run_ide)
        except KeyboardInterrupt:
            _err_console().print(Text("Interrupted.", style="italic dim"))
            return 130
        # No trailing blank — next loop clears the screen anyway.
