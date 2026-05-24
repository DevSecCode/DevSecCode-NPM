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
from dsc.gamification.characters import all_characters, get_character
from dsc.gamification.deva import ACCENT_COLOR, CATCHPHRASE, VOICE, active_name, deva_portrait
from dsc.gamification.profile import (
    DIFFICULTY_MODES,
    Profile,
    get_loot_info,
    load_profile,
    save_profile,
    set_active_title,
    set_difficulty,
    set_hunter_class,
)


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
    """Render the hunter stats panel."""
    from dsc.gamification import screens
    screens.show_stats(profile)
    return 0




def _action_profile_menu(questionary, profile: Profile) -> Profile:
    """Profile sub-menu: stats, change hunter, difficulty, loot, leaderboard."""
    char = get_character(profile.hunter_class)
    loot_count = len(profile.loot)

    menu_style = questionary.Style([
        ("qmark", "fg:#9b8cff bold"),
        ("question", "bold"),
        ("pointer", "fg:#9b8cff bold"),
        ("highlighted", "fg:#9b8cff bold underline"),
        ("selected", "fg:#9b8cff bold"),
        ("separator", "fg:#555555"),
        ("answer", "fg:#9b8cff bold"),
    ])

    pick = questionary.select(
        f"{char.glyph}  {char.name} · Lvl {profile.level}",
        choices=[
            questionary.Choice(title=f"  ★  Hunter Stats", value="stats"),
            questionary.Choice(title=f"  {char.glyph}  Change Hunter", value="character"),
            questionary.Choice(title=f"  ⚙  Difficulty · {profile.difficulty.upper()}", value="difficulty"),
            questionary.Choice(title=f"  ◆  Loot · {loot_count} title{'s' if loot_count != 1 else ''}", value="loot"),
            questionary.Choice(title=f"  ▲  Leaderboard", value="leaderboard"),
            questionary.Separator("  ────────────────────────────────"),
            questionary.Choice(title=f"  ←  Back", value="back"),
        ],
        qmark="◆",
        use_arrow_keys=True,
        style=menu_style,
    ).ask()

    if pick is None or pick == "back":
        return profile
    if pick == "stats":
        _action_show_stats(profile)
    elif pick == "character":
        _action_change_character(questionary, profile)
        profile = load_profile()
    elif pick == "difficulty":
        _action_set_difficulty(questionary, profile)
        profile = load_profile()
    elif pick == "loot":
        _action_loot(questionary, profile)
        profile = load_profile()
    elif pick == "leaderboard":
        _action_leaderboard(profile)
    return profile


def _action_change_character(questionary, profile: Profile) -> int:
    """Let the player pick a new pixel-art character."""
    characters = all_characters()
    current = get_character(profile.hunter_class)

    choices = []
    for ch in characters:
        marker = " (current)" if ch.key == current.key else ""
        choices.append(questionary.Choice(
            title=f"  {ch.glyph}  {ch.name} — {ch.title}{marker}",
            value=ch.key,
        ))

    pick = questionary.select(
        "Choose your hunter:",
        choices=choices,
        qmark=">",
        use_arrow_keys=True,
    ).ask()
    if pick is None:
        return 0

    set_hunter_class(profile, pick)
    chosen = get_character(pick)
    console = _err_console()
    console.print(Text(f"\n  {chosen.glyph}  Now playing as {chosen.name}\n", style=f"bold {chosen.accent_color}"))
    return 0


def _action_view_report(questionary) -> int:
    """View the last hunt report."""
    from dsc.gamification import screens
    screens.show_last_report()
    return 0


def _action_save_report(questionary) -> int:
    """Export the last hunt report to a file."""
    from dsc.gamification.report_store import export_report, load_report

    report = load_report()
    if report is None:
        console = _err_console()
        console.print(Text("No report saved yet. Run a hunt first!", style="yellow"))
        return 0

    default_name = f"devseccode-report-{report.timestamp[:10]}.json"
    path = questionary.text(
        "Save report to:",
        default=default_name,
        qmark=">",
    ).ask()
    if path is None:
        return 0
    try:
        saved = export_report(report, path)
        console = _err_console()
        console.print(Text(f"Report saved to {saved}", style="bold bright_green"))
    except OSError as exc:
        console = _err_console()
        console.print(Text(f"Failed to save: {exc}", style="bold red"))
    return 0


def _action_set_difficulty(questionary, profile: Profile) -> int:
    """Let the player pick a difficulty mode."""
    xp_mults = {"easy": "0.75x XP", "normal": "1.0x XP", "hard": "1.5x XP"}
    gate_hints = {"easy": "only CRITICAL fails", "normal": "HIGH+ fails", "hard": "MEDIUM+ fails"}

    choices = []
    for diff in DIFFICULTY_MODES:
        marker = " (current)" if diff == profile.difficulty else ""
        label = f"{diff.upper()} — {gate_hints[diff]}, {xp_mults[diff]}{marker}"
        choices.append(questionary.Choice(title=label, value=diff))

    pick = questionary.select(
        "Select difficulty:",
        choices=choices,
        qmark=">",
        use_arrow_keys=True,
    ).ask()
    if pick is None:
        return 0

    set_difficulty(profile, pick)
    console = _err_console()
    console.print(Text(f"  Difficulty set to {pick.upper()}", style="bold"))
    return 0


def _action_leaderboard(profile: Profile) -> int:
    """Show the personal best scores."""
    from dsc.gamification import screens
    screens.show_leaderboard(profile)
    return 0


def _action_loot(questionary, profile: Profile) -> int:
    """Show loot chest and let the player equip a title."""
    console = _err_console()

    if not profile.loot:
        chest = Text()
        chest.append("  ┌─────────┐\n", style="dim")
        chest.append("  │  EMPTY  │\n", style="dim")
        chest.append("  └─────────┘\n", style="dim")
        chest.append("  No loot earned yet. Keep hunting!", style="yellow")
        console.print(chest)
        return 0

    # Render the loot chest display before the picker.
    chest_art = Text()
    chest_art.append("\n")
    chest_art.append("       ┌──────────────────────────────────┐\n", style="bright_cyan")
    chest_art.append("       │ ◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆ │\n", style="bright_cyan")
    chest_art.append("       │          LOOT  CHEST             │\n", style="bold bright_cyan")
    chest_art.append("       │ ◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇◆◇ │\n", style="bright_cyan")
    chest_art.append("       └──────────────────────────────────┘\n", style="bright_cyan")
    chest_art.append(f"         {len(profile.loot)} title{'s' if len(profile.loot) != 1 else ''} collected\n", style="dim")
    console.print(chest_art)

    # Show each title as a loot card.
    for loot_key in profile.loot:
        info = get_loot_info(loot_key)
        if not info:
            continue
        name, desc = info
        equipped = loot_key == profile.active_title
        card = Text()
        if equipped:
            card.append("  ★ ", style="bold bright_yellow")
            card.append(name, style="bold bright_cyan")
            card.append("  [EQUIPPED]", style="bold bright_yellow")
        else:
            card.append("  ◆ ", style="bright_cyan")
            card.append(name, style="bold bright_cyan")
        card.append(f"\n    {desc}", style="dim")
        console.print(card)
    console.print()

    # Equip picker.
    loot_style = questionary.Style([
        ("qmark", "fg:ansicyan bold"),
        ("question", "bold"),
        ("pointer", "fg:ansicyan bold"),
        ("highlighted", "fg:ansicyan bold underline"),
        ("selected", "fg:ansicyan bold"),
        ("separator", "fg:#555555"),
        ("answer", "fg:ansicyan bold"),
    ])

    choices = [questionary.Choice(title="  ✕  Remove title", value="__none__")]
    for loot_key in profile.loot:
        info = get_loot_info(loot_key)
        if info:
            name, desc = info
            glyph = "★" if loot_key == profile.active_title else "◆"
            choices.append(questionary.Choice(title=f"  {glyph}  {name}", value=loot_key))

    pick = questionary.select(
        "Equip a title:",
        choices=choices,
        qmark="◆",
        use_arrow_keys=True,
        style=loot_style,
    ).ask()
    if pick is None:
        return 0
    if pick == "__none__":
        pick = None

    set_active_title(profile, pick)
    if pick:
        info = get_loot_info(pick)
        name = info[0] if info else pick
        equipped_text = Text()
        equipped_text.append("\n  ★ ", style="bold bright_yellow")
        equipped_text.append(f"Title equipped: {name}", style="bold bright_cyan")
        equipped_text.append("\n", style="")
        console.print(equipped_text)
    else:
        console.print(Text("\n  Title removed.\n", style="dim"))
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
    run_watch: Callable[[str], int] = lambda _: 0,
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

    _first_cycle = True
    while True:
        # Each cycle starts clean: clear, redraw banner with fresh stats,
        # then prompt. This stops questionary's "What would you like to
        # do? <choice>" echo from stacking up across selections.
        _clear_screen()
        banner.render_play_banner(profile, animate=_first_cycle)
        _first_cycle = False

        if profile.hunts_completed == 0:
            intro = Text()
            intro.append("Deva: ", style="dim")
            intro.append(
                "I'll watch the perimeter. Pick a path to begin.",
                style=f"italic {ACCENT_COLOR}",
            )
            _err_console().print(intro)

        char = get_character(profile.hunter_class)
        streak_label = f"  streak: {profile.current_streak}d" if profile.current_streak > 1 else ""
        loot_count = len(profile.loot)

        menu_style = questionary.Style([
            ("qmark", "fg:#9b8cff bold"),
            ("question", "bold"),
            ("pointer", "fg:#9b8cff bold"),
            ("highlighted", "fg:#9b8cff bold underline"),
            ("selected", "fg:#9b8cff bold"),
            ("separator", "fg:#555555"),
            ("answer", "fg:#9b8cff bold"),
        ])

        choice = questionary.select(
            "What would you like to do?",
            choices=[
                questionary.Separator("  ─── HUNT ───────────────────────"),
                questionary.Choice(title=f"  ⚔  Start Hunt", value="hunt"),
                questionary.Choice(title=f"  ◉  Watch Mode", value="watch"),
                questionary.Choice(title=f"  ◈  Quest Map", value="quests"),
                questionary.Separator("  ────────────────────────────────"),
                questionary.Choice(title=f"  {char.glyph}  My Profile", value="profile"),
                questionary.Separator("  ────────────────────────────────"),
                questionary.Choice(title=f"  ◇  Last Report", value="report"),
                questionary.Choice(title=f"  ▸  DevSecCode IDE", value="ide"),
                questionary.Choice(title=f"  ✕  Exit", value="exit"),
            ],
            qmark="◆",
            use_arrow_keys=True,
            use_shortcuts=False,
            style=menu_style,
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
            elif choice == "profile":
                profile = _action_profile_menu(questionary, profile)
            elif choice == "report":
                _action_view_report(questionary)
            elif choice == "watch":
                run_watch(".")
            elif choice == "ide":
                _action_ide_upsell(run_ide)
        except KeyboardInterrupt:
            _err_console().print(Text("Interrupted.", style="italic dim"))
            return 130
        # No trailing blank — next loop clears the screen anyway.
