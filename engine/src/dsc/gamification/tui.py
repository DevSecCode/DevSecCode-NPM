"""Full-screen TUI for the hunt map.

Built on prompt_toolkit (already in the bundle via questionary's
dependency tree). The screen has two layers:

  * Main: the layout canvas — file cards + import edges + Deva-orb
    cursor on the focused file.
  * Floating inspect modal: opens on Enter; shows the focused file's
    findings one at a time with [L]og / [I]gnore / [N]ext / [P]rev /
    [J]ump-to-import / [B]ack actions.

The TUI does *not* take a Console or write through Rich. It produces
prompt_toolkit FormattedText directly, so the Application owns the
terminal and we don't fight Rich over the alt-screen.

run_map_session() is the entry point. It returns when the player
quits (q / Ctrl-C / "finish hunt"). The caller (`cmd_hunt`) then
renders the summary card via Rich on the regular console.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import FormattedText, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    Layout,
    ScrollOffsets,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.filters import Condition
from prompt_toolkit.widgets import Frame

from dsc.gamification.categories import classify_finding
from dsc.gamification.deva import ACCENT_COLOR, VOICE
from dsc.gamification.imports import ImportGraph
from dsc.gamification.layout import CARD_H, CARD_W, Canvas, NodeInfo, NodeMap, layout_graph
from dsc.gamification.triage import TriageStore, save_triage
from dsc.scanner.models import Finding, Severity


_SEV_PTK_STYLE = {
    Severity.CRITICAL: "bold ansired",
    Severity.HIGH: "ansired",
    Severity.MEDIUM: "ansiyellow",
    Severity.LOW: "ansiblue",
    Severity.INFO: "ansigray",
}

_DEVA_STYLE = "fg:ansimagenta bold"
_ACCENT_PTK = "fg:ansimagenta"
_DIM_PTK = "fg:ansibrightblack"


def _tkey(finding: Finding) -> str:
    return f"{finding.file_path}::{finding.rule_id}::{finding.line_start}"


# --- state ------------------------------------------------------------

@dataclass
class _MapState:
    findings: list[Finding]
    targets: list[Path]
    import_graph: ImportGraph
    triage: TriageStore
    extra_files: list[str] = field(default_factory=list)
    node_map: NodeMap = field(default=None)  # type: ignore[assignment]
    canvas: Canvas = field(default=None)     # type: ignore[assignment]
    selected_path: str | None = None
    # Inspect modal state.
    inspecting: bool = False
    inspect_index: int = 0  # index into the focused node's findings
    # Status flash — short message shown above the status bar.
    flash: str = ""
    flash_style: str = ""

    @property
    def selected_node(self) -> NodeInfo | None:
        if not self.selected_path:
            return None
        return self.node_map.get(self.selected_path)

    @property
    def current_finding(self) -> Finding | None:
        node = self.selected_node
        if not node:
            return None
        # Cycle through *all* findings, not just visible — players can
        # un-ignore by toggling. The renderer marks the current state.
        if not node.findings:
            return None
        idx = self.inspect_index % len(node.findings)
        return node.findings[idx]

    def relayout(self, canvas_width: int) -> None:
        triage_status = {key: status for key, status in self.triage.entries.items()}
        self.canvas, self.node_map = layout_graph(
            self.findings,
            edges=((src, dst) for src, dsts in self.import_graph.edges.items() for dst in dsts),
            triage_status=triage_status,
            canvas_width=canvas_width,
            extra_files=self.extra_files,
        )
        # Preserve selection if still present, else pick first node.
        if self.selected_path and self.node_map.get(self.selected_path):
            return
        if self.node_map.nodes:
            self.selected_path = self.node_map.nodes[0].file_path
        else:
            self.selected_path = None


# --- rendering --------------------------------------------------------

def _render_canvas_with_cursor(state: _MapState) -> FormattedText:
    """Convert the canvas to prompt_toolkit FormattedText, overlaying
    the cursor highlight on the selected card."""
    canvas = state.canvas
    selected = state.selected_node

    # Determine cells inside the selected card so we can restyle them
    # without rebuilding the canvas.
    sel_rect = None
    if selected:
        sel_rect = (selected.x, selected.y, selected.right, selected.bottom)

    fragments: list[tuple[str, str]] = []
    for y in range(canvas.height):
        for x in range(canvas.width):
            ch = canvas._chars[y][x]
            style = canvas._styles[y][x]
            if sel_rect and sel_rect[0] <= x <= sel_rect[2] and sel_rect[1] <= y <= sel_rect[3]:
                # Selected card: reverse-video accent.
                style = f"reverse {ACCENT_COLOR}"
                # Cursor glyph: replace the leftmost padding cell of the
                # middle row with the Deva orb so it reads as "you are here".
                if y == selected.y + 2 and x == selected.x + 1:
                    ch = "◉"
            fragments.append((_rich_to_ptk_style(style), ch))
        fragments.append(("", "\n"))
    return FormattedText(fragments)


def _rich_to_ptk_style(rich_style: str) -> str:
    """Translate the small set of Rich style names we use into
    prompt_toolkit equivalents.

    prompt_toolkit's style language is different — it doesn't accept
    space-separated Rich tokens like 'bold red'. We map enough of the
    cases used by layout.py and this module."""
    if not rich_style:
        return ""
    s = rich_style.strip()
    # Direct passthroughs that prompt_toolkit understands.
    if s in ("", "bold", "italic", "reverse", "dim", "underline"):
        return s
    # Compound 'reverse <color>' — preserve reverse and translate color.
    if s.startswith("reverse "):
        return "reverse " + _color_to_ptk(s[len("reverse "):])
    # Compound 'bold <color>'.
    if s.startswith("bold "):
        return "bold " + _color_to_ptk(s[len("bold "):])
    if s.startswith("italic "):
        return "italic " + _color_to_ptk(s[len("italic "):])
    if s.startswith("dim "):
        return "fg:ansibrightblack"
    return _color_to_ptk(s)


_COLOR_MAP = {
    "red": "fg:ansired",
    "green": "fg:ansigreen",
    "yellow": "fg:ansiyellow",
    "blue": "fg:ansiblue",
    "magenta": "fg:ansimagenta",
    "cyan": "fg:ansicyan",
    "white": "fg:ansiwhite",
    "bright_red": "fg:ansibrightred",
    "bright_green": "fg:ansibrightgreen",
    "bright_yellow": "fg:ansibrightyellow",
    "bright_blue": "fg:ansibrightblue",
    "bright_magenta": "fg:ansimagenta",
    "bright_cyan": "fg:ansibrightcyan",
    "dim cyan": "fg:ansicyan",
    "dim white": "fg:ansibrightblack",
}


def _color_to_ptk(rich_color: str) -> str:
    s = rich_color.strip()
    if s in _COLOR_MAP:
        return _COLOR_MAP[s]
    return ""


# --- status bar -------------------------------------------------------

def _status_bar_text(state: _MapState) -> FormattedText:
    parts: list[tuple[str, str]] = []
    parts.append((_ACCENT_PTK + " bold", " Deva "))
    parts.append(("", " "))
    node = state.selected_node
    if node:
        rel = _relative_path(node.file_path, state.targets)
        parts.append(("bold", rel))
        parts.append((_DIM_PTK, f"  ({len(node.findings)} findings)"))
    else:
        parts.append((_DIM_PTK, "(no selection)"))
    parts.append(("", "\n"))
    if state.flash:
        parts.append((state.flash_style or _ACCENT_PTK, " " + state.flash + " "))
        parts.append(("", "\n"))
    parts.append((_DIM_PTK, " ←↑→↓ move   enter inspect   q finish   ? help "))
    return FormattedText(parts)


def _help_text() -> FormattedText:
    return FormattedText([
        (_ACCENT_PTK + " bold", " Hunt Map controls "),
        ("", "\n"),
        ("", "  ←↑→↓ "),
        (_DIM_PTK, "move cursor between files"),
        ("", "\n"),
        ("", "  Enter "),
        (_DIM_PTK, "inspect findings for the focused file"),
        ("", "\n"),
        ("", "  q     "),
        (_DIM_PTK, "finish the hunt → summary card"),
        ("", "\n"),
        ("", "  ?     "),
        (_DIM_PTK, "show/hide this help"),
        ("", "\n\n"),
        (_ACCENT_PTK + " bold", " Inspect modal "),
        ("", "\n"),
        ("", "  L  "),
        (_DIM_PTK, "log the current finding (confirm real)"),
        ("", "\n"),
        ("", "  I  "),
        (_DIM_PTK, "ignore the current finding"),
        ("", "\n"),
        ("", "  N / P "),
        (_DIM_PTK, "next / previous finding in this file"),
        ("", "\n"),
        ("", "  J  "),
        (_DIM_PTK, "jump to one of this file's imports"),
        ("", "\n"),
        ("", "  B / Esc "),
        (_DIM_PTK, "back to the map"),
        ("", "\n"),
    ])


def _relative_path(p: str, targets: list[Path]) -> str:
    pp = Path(p)
    for t in targets:
        try:
            return str(pp.relative_to(t))
        except ValueError:
            continue
    return p


# --- inspect modal ----------------------------------------------------

def _inspect_modal_text(state: _MapState) -> FormattedText:
    node = state.selected_node
    if not node:
        return FormattedText([("", "(no selection)")])
    finding = state.current_finding
    if finding is None:
        return FormattedText([
            (_DIM_PTK, "No findings in this file."),
            ("", "\n\n"),
            (_DIM_PTK, "[B/Esc] back to map"),
        ])

    status = state.triage.status_of(finding)
    cat = classify_finding(finding)
    sev_style = _SEV_PTK_STYLE.get(finding.severity, "")

    parts: list[tuple[str, str]] = []
    rel = _relative_path(finding.file_path, state.targets)
    parts.append((_ACCENT_PTK + " bold", f"  {rel}  "))
    parts.append((_DIM_PTK, f"  finding {(state.inspect_index % len(node.findings)) + 1} of {len(node.findings)}"))
    parts.append(("", "\n\n"))
    parts.append((sev_style + " bold", f"  {finding.severity.name}  "))
    parts.append((_DIM_PTK, " · "))
    parts.append(("bold", f"{cat.label}"))
    parts.append((_DIM_PTK, " · "))
    parts.append(("", f"{finding.rule_id}  ({finding.cwe})"))
    parts.append(("", "\n"))
    parts.append((_DIM_PTK, f"  line {finding.line_start}"))
    if status == "logged":
        parts.append(("fg:ansibrightgreen bold", "    ✓ LOGGED"))
    elif status == "ignored":
        parts.append((_DIM_PTK + " italic", "    (ignored)"))
    parts.append(("", "\n\n"))

    if finding.snippet:
        for line in finding.snippet.splitlines():
            parts.append(("fg:ansibrightcyan", "    " + line))
            parts.append(("", "\n"))
        parts.append(("", "\n"))

    msg = (finding.message or "").strip()
    if msg:
        for line in _wrap(msg, width=72):
            parts.append(("", "  " + line))
            parts.append(("", "\n"))
        parts.append(("", "\n"))
    fix = (finding.fix_suggestion or "").strip()
    if fix:
        parts.append(("fg:ansigreen bold", "  Fix: "))
        for i, line in enumerate(_wrap(fix, width=68)):
            if i == 0:
                parts.append(("fg:ansigreen", line))
            else:
                parts.append(("fg:ansigreen", "       " + line))
            parts.append(("", "\n"))
        parts.append(("", "\n"))

    # Import context.
    imports = state.import_graph.imports_of(finding.file_path)
    importers = state.import_graph.importers_of(finding.file_path)
    externals = state.import_graph.externals_of(finding.file_path)
    if imports or importers or externals:
        if imports:
            parts.append((_DIM_PTK, "  Imports:     "))
            parts.append(("", ", ".join(_relative_path(p, state.targets) for p in imports[:5])))
            if len(imports) > 5:
                parts.append((_DIM_PTK, f"  (+{len(imports)-5})"))
            parts.append(("", "\n"))
        if importers:
            parts.append((_DIM_PTK, "  Imported by: "))
            parts.append(("", ", ".join(_relative_path(p, state.targets) for p in importers[:5])))
            if len(importers) > 5:
                parts.append((_DIM_PTK, f"  (+{len(importers)-5})"))
            parts.append(("", "\n"))
        if externals:
            parts.append((_DIM_PTK, "  External:    "))
            parts.append((_DIM_PTK, ", ".join(externals[:6])))
            if len(externals) > 6:
                parts.append((_DIM_PTK, f"  (+{len(externals)-6})"))
            parts.append(("", "\n"))
        parts.append(("", "\n"))

    # Action hints.
    parts.append((_DIM_PTK, "  [L] log    [I] ignore    [N] next    [P] prev    "))
    if imports:
        parts.append((_DIM_PTK, "[J] jump    "))
    parts.append((_DIM_PTK, "[B] back"))
    return FormattedText(parts)


def _wrap(text: str, *, width: int) -> list[str]:
    out: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            out.append("")
            continue
        words = paragraph.split()
        line = ""
        for w in words:
            if not line:
                line = w
                continue
            if len(line) + 1 + len(w) > width:
                out.append(line)
                line = w
            else:
                line = f"{line} {w}"
        if line:
            out.append(line)
    return out


# --- jump-to-import picker --------------------------------------------

@dataclass
class _JumpState:
    options: list[str]
    cursor: int = 0


def _jump_text(jump_state: _JumpState, state: _MapState) -> FormattedText:
    parts: list[tuple[str, str]] = []
    parts.append((_ACCENT_PTK + " bold", " Jump to import "))
    parts.append(("", "\n\n"))
    for i, p in enumerate(jump_state.options):
        rel = _relative_path(p, state.targets)
        if i == jump_state.cursor:
            parts.append(("reverse fg:ansimagenta", f"  > {rel}"))
        else:
            parts.append(("", f"    {rel}"))
        parts.append(("", "\n"))
    parts.append(("", "\n"))
    parts.append((_DIM_PTK, "  ↑↓ move    enter jump    esc cancel"))
    return FormattedText(parts)


# --- main entry -------------------------------------------------------

def run_map_session(
    findings: Iterable[Finding],
    targets: Iterable[Path],
    *,
    import_graph: ImportGraph,
    triage: TriageStore,
    extra_files: Iterable[str] | None = None,
) -> None:
    """Run the full-screen hunt-map TUI until the player quits.

    On exit, the (in-memory mutated) `triage` is persisted via
    save_triage(). The caller then renders the post-hunt summary card.

    `extra_files` are non-findings source files to render as cards too,
    so the player can navigate the rest of the codebase (and see the
    import edges between findings and clean files).
    """
    findings = list(findings)
    targets = list(targets)
    state = _MapState(
        findings=findings,
        targets=targets,
        import_graph=import_graph,
        triage=triage,
        extra_files=list(extra_files or []),
    )

    # Initial layout — we'll re-layout on terminal resize.
    state.relayout(canvas_width=120)

    # Jump-to-import state, created on demand.
    jump_state: _JumpState | None = None

    # --- key bindings ------------------------------------------------
    kb = KeyBindings()
    help_visible = {"on": False}

    @Condition
    def _map_focused() -> bool:
        return not state.inspecting and jump_state is None and not help_visible["on"]

    @Condition
    def _modal_focused() -> bool:
        return state.inspecting and jump_state is None

    @Condition
    def _jump_focused() -> bool:
        return jump_state is not None

    @Condition
    def _help_focused() -> bool:
        return help_visible["on"]

    def _move(direction: str) -> None:
        node = state.selected_node
        if not node:
            return
        nxt = state.node_map.neighbor(node, direction)
        if nxt is not None:
            state.selected_path = nxt.file_path

    @kb.add("left", filter=_map_focused)
    def _(_e): _move("left")

    @kb.add("right", filter=_map_focused)
    def _(_e): _move("right")

    @kb.add("up", filter=_map_focused)
    def _(_e): _move("up")

    @kb.add("down", filter=_map_focused)
    def _(_e): _move("down")

    @kb.add("enter", filter=_map_focused)
    def _(_e):
        node = state.selected_node
        if node and node.findings:
            state.inspecting = True
            state.inspect_index = 0
            state.flash = ""

    @kb.add("q", filter=_map_focused)
    @kb.add("c-c")
    def _(event):
        event.app.exit()

    @kb.add("?", filter=_map_focused)
    @kb.add("h", filter=_map_focused)
    def _(_e):
        help_visible["on"] = True

    @kb.add("escape", filter=_help_focused)
    @kb.add("q", filter=_help_focused)
    @kb.add("?", filter=_help_focused)
    def _(_e):
        help_visible["on"] = False

    # --- modal bindings ----------------------------------------------
    @kb.add("escape", filter=_modal_focused)
    @kb.add("b", filter=_modal_focused)
    def _(_e):
        state.inspecting = False
        state.flash = ""
        # Re-layout to reflect any triage changes (card may dim out).
        state.relayout(canvas_width=120)

    @kb.add("n", filter=_modal_focused)
    @kb.add("right", filter=_modal_focused)
    def _(_e):
        node = state.selected_node
        if node and node.findings:
            state.inspect_index = (state.inspect_index + 1) % len(node.findings)

    @kb.add("p", filter=_modal_focused)
    @kb.add("left", filter=_modal_focused)
    def _(_e):
        node = state.selected_node
        if node and node.findings:
            state.inspect_index = (state.inspect_index - 1) % len(node.findings)

    @kb.add("l", filter=_modal_focused)
    def _(_e):
        f = state.current_finding
        if f is None:
            return
        state.triage.set_status(f, "logged")
        try:
            save_triage(state.triage)
        except OSError:
            pass
        state.flash = f"Logged: {Path(f.file_path).name}:{f.line_start}"
        state.flash_style = "fg:ansibrightgreen bold"

    @kb.add("i", filter=_modal_focused)
    def _(_e):
        f = state.current_finding
        if f is None:
            return
        state.triage.set_status(f, "ignored")
        try:
            save_triage(state.triage)
        except OSError:
            pass
        state.flash = f"Ignored: {Path(f.file_path).name}:{f.line_start}"
        state.flash_style = _DIM_PTK

    @kb.add("u", filter=_modal_focused)
    def _(_e):
        # Undo: revert to unseen.
        f = state.current_finding
        if f is None:
            return
        state.triage.set_status(f, "unseen")
        try:
            save_triage(state.triage)
        except OSError:
            pass
        state.flash = f"Reset: {Path(f.file_path).name}:{f.line_start}"
        state.flash_style = _ACCENT_PTK

    @kb.add("j", filter=_modal_focused)
    def _(_e):
        nonlocal jump_state
        f = state.current_finding
        if f is None:
            return
        imports = state.import_graph.imports_of(f.file_path)
        if not imports:
            state.flash = "No imports to jump to."
            state.flash_style = _DIM_PTK
            return
        # Filter to imports that exist as nodes in the map.
        navigable = [p for p in imports if state.node_map.get(p)]
        if not navigable:
            state.flash = "Imports go outside the scanned set."
            state.flash_style = _DIM_PTK
            return
        jump_state = _JumpState(options=navigable, cursor=0)

    # --- jump picker bindings ----------------------------------------
    @kb.add("up", filter=_jump_focused)
    def _(_e):
        nonlocal jump_state
        if jump_state is None:
            return
        jump_state.cursor = (jump_state.cursor - 1) % len(jump_state.options)

    @kb.add("down", filter=_jump_focused)
    def _(_e):
        nonlocal jump_state
        if jump_state is None:
            return
        jump_state.cursor = (jump_state.cursor + 1) % len(jump_state.options)

    @kb.add("enter", filter=_jump_focused)
    def _(_e):
        nonlocal jump_state
        if jump_state is None:
            return
        target = jump_state.options[jump_state.cursor]
        jump_state = None
        state.inspecting = False
        state.selected_path = target
        state.inspect_index = 0
        # Auto-open the inspect modal at the destination if it has findings.
        node = state.node_map.get(target)
        if node and node.findings:
            state.inspecting = True
        state.flash = f"Jumped to {Path(target).name}"
        state.flash_style = _ACCENT_PTK

    @kb.add("escape", filter=_jump_focused)
    @kb.add("q", filter=_jump_focused)
    def _(_e):
        nonlocal jump_state
        jump_state = None

    # --- layout ------------------------------------------------------
    def _cursor_pos() -> Point:
        """Tell prompt_toolkit where the focused card sits so the Window
        scrolls to keep it on screen as the player navigates."""
        node = state.selected_node
        if not node:
            return Point(x=0, y=0)
        return Point(x=node.cx, y=node.cy)

    map_window = Window(
        FormattedTextControl(
            text=lambda: _render_canvas_with_cursor(state),
            get_cursor_position=_cursor_pos,
            focusable=True,
        ),
        wrap_lines=False,
        always_hide_cursor=True,
        # Keep at least a card's worth of breathing room around the cursor
        # so the next-row neighbor is already visible before you move to it.
        scroll_offsets=ScrollOffsets(
            top=CARD_H + 1,
            bottom=CARD_H + 1,
            left=CARD_W // 2,
            right=CARD_W // 2,
        ),
    )

    status_window = Window(
        FormattedTextControl(text=lambda: _status_bar_text(state)),
        height=Dimension.exact(3),
        always_hide_cursor=True,
    )

    inspect_window = ConditionalContainer(
        Frame(
            Window(
                FormattedTextControl(text=lambda: _inspect_modal_text(state)),
                wrap_lines=False,
                always_hide_cursor=True,
            ),
            title="Inspect",
            style=_ACCENT_PTK,
        ),
        filter=_modal_focused,
    )

    jump_window = ConditionalContainer(
        Frame(
            Window(
                FormattedTextControl(text=lambda: _jump_text(jump_state, state) if jump_state else FormattedText([])),
                wrap_lines=False,
                always_hide_cursor=True,
            ),
            title="Jump",
            style=_ACCENT_PTK,
        ),
        filter=_jump_focused,
    )

    help_window = ConditionalContainer(
        Frame(
            Window(
                FormattedTextControl(text=lambda: _help_text()),
                wrap_lines=False,
                always_hide_cursor=True,
            ),
            title="Help",
            style=_ACCENT_PTK,
        ),
        filter=_help_focused,
    )

    body = HSplit([
        map_window,
        status_window,
    ])

    root = FloatContainer(
        content=body,
        floats=[
            Float(content=inspect_window, top=2, left=4, right=4),
            Float(content=jump_window, top=4, left=10, right=10),
            Float(content=help_window, top=2, left=10, right=10),
        ],
    )

    app = Application(
        layout=Layout(root),
        key_bindings=kb,
        full_screen=True,
        mouse_support=False,
    )

    # prompt_toolkit handles its own terminal IO. Run synchronously —
    # the call returns when the user hits 'q' (which triggers app.exit()).
    try:
        app.run()
    except (KeyboardInterrupt, EOFError):
        pass

    # Final persist in case anything didn't flush yet.
    try:
        save_triage(triage)
    except OSError:
        pass
