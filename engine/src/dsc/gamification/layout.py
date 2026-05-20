"""Graph layout + edge routing for the hunt-map TUI.

Takes the set of file nodes (with their finding counts) and the import
graph, and produces:

  1. A `Canvas` — a 2D character buffer ready to render with Rich.
  2. A `NodeMap` — per-node bounding-box info so the TUI knows where
     the cursor is and which spatial neighbor each arrow key should
     move to.

Layout strategy (intentionally simple):
  * Group nodes by parent directory.
  * Stack directories vertically; within each directory, place cards
    in a row (wrapping if the canvas is narrow).
  * Route import edges with L-shaped Manhattan paths around the cards.

We are not aiming for a force-directed graph here. The point is to
read fast and navigate fast in a terminal, not to look like d3.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from dsc.gamification.categories import classify_finding
from dsc.scanner.models import Finding, Severity


CARD_W = 22         # outer card width including border
CARD_H = 5          # outer card height including border
GAP_X = 4           # horizontal gap between cards in the same row
GAP_Y = 3           # vertical gap between rows
SECTION_GAP = 2     # extra rows between directory sections
MARGIN = 1          # canvas border margin


# Severity → 1-char dot. Used inside the card and on the cursor.
_SEV_DOT = {
    Severity.CRITICAL: "●",
    Severity.HIGH: "●",
    Severity.MEDIUM: "●",
    Severity.LOW: "●",
    Severity.INFO: "·",
}


@dataclass
class NodeInfo:
    file_path: str
    x: int               # top-left of card
    y: int
    findings: list[Finding] = field(default_factory=list)
    triaged_logged: int = 0
    triaged_ignored: int = 0

    @property
    def cx(self) -> int:
        return self.x + CARD_W // 2

    @property
    def cy(self) -> int:
        return self.y + CARD_H // 2

    @property
    def bottom(self) -> int:
        return self.y + CARD_H - 1

    @property
    def right(self) -> int:
        return self.x + CARD_W - 1

    @property
    def top_anchor(self) -> tuple[int, int]:
        return (self.cx, self.y)

    @property
    def bottom_anchor(self) -> tuple[int, int]:
        return (self.cx, self.bottom)

    @property
    def left_anchor(self) -> tuple[int, int]:
        return (self.x, self.cy)

    @property
    def right_anchor(self) -> tuple[int, int]:
        return (self.right, self.cy)

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.right and self.y <= py <= self.bottom


class Canvas:
    """Mutable 2D character buffer with style overlays.

    Each cell is (char, style). Rich `Text` consumes the result row by
    row in `render()`.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._chars: list[list[str]] = [[" "] * width for _ in range(height)]
        self._styles: list[list[str]] = [[""] * width for _ in range(height)]

    def put(self, x: int, y: int, ch: str, style: str = "") -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self._chars[y][x] = ch
            self._styles[y][x] = style

    def put_str(self, x: int, y: int, s: str, style: str = "") -> None:
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, style)

    def get(self, x: int, y: int) -> str:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._chars[y][x]
        return " "

    def render_to_text(self):
        """Return a Rich `Text` representation of the canvas."""
        from rich.text import Text
        out = Text()
        for y in range(self.height):
            for x in range(self.width):
                out.append(self._chars[y][x], style=self._styles[y][x] or "")
            out.append("\n")
        return out


@dataclass
class NodeMap:
    nodes: list[NodeInfo]
    by_path: dict[str, NodeInfo] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)

    def get(self, file_path: str) -> NodeInfo | None:
        return self.by_path.get(file_path)

    def neighbor(self, current: NodeInfo, direction: str) -> NodeInfo | None:
        """Find the nearest node in the given direction.

        Direction is one of 'left', 'right', 'up', 'down'. We pick the
        closest node whose center sits in the right half-plane, with
        cross-axis distance as a tiebreaker so the cursor moves "in
        line" rather than jumping to a far-off node.
        """
        if not self.nodes:
            return None
        candidates: list[tuple[float, NodeInfo]] = []
        for n in self.nodes:
            if n is current:
                continue
            dx = n.cx - current.cx
            dy = n.cy - current.cy
            if direction == "right" and dx > 0:
                # Prefer same-row (small |dy|) then nearest dx.
                score = abs(dy) * 4 + dx
            elif direction == "left" and dx < 0:
                score = abs(dy) * 4 + (-dx)
            elif direction == "down" and dy > 0:
                score = abs(dx) * 2 + dy
            elif direction == "up" and dy < 0:
                score = abs(dx) * 2 + (-dy)
            else:
                continue
            candidates.append((score, n))
        if not candidates:
            return None
        candidates.sort(key=lambda kv: kv[0])
        return candidates[0][1]


# --- layout -----------------------------------------------------------

def layout_graph(
    findings: list[Finding],
    *,
    edges: Iterable[tuple[str, str]],
    triage_status: dict[str, str] | None = None,
    canvas_width: int = 120,
    extra_files: Iterable[str] | None = None,
) -> tuple[Canvas, NodeMap]:
    """Lay out files + edges into a Canvas and return the navigation map.

    `edges` is an iterable of (src_path, dst_path) for one-way imports.
    Self-edges are silently dropped.
    `triage_status` keys findings to one of "logged" / "ignored" so
    the card can show ✓ / dimmed.
    `extra_files` are paths to include as nodes even if they have no
    findings (1-hop import neighbors of findings files, typically).
    """
    triage_status = triage_status or {}

    # 1. Decide node set: every file with at least one finding, plus any
    # extra files (typically 1-hop import neighbors).
    findings_by_file: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        findings_by_file[f.file_path].append(f)

    node_paths: list[str] = sorted(findings_by_file.keys())
    if extra_files:
        for ef in extra_files:
            if ef not in findings_by_file:
                node_paths.append(ef)

    # 2. Group by parent directory (stable order: by string).
    by_dir: dict[str, list[str]] = defaultdict(list)
    for p in node_paths:
        by_dir[str(Path(p).parent)].append(p)
    dir_order = sorted(by_dir.keys())

    # 3. Place cards row by row.
    nodes: list[NodeInfo] = []
    by_path: dict[str, NodeInfo] = {}
    cur_y = MARGIN
    canvas_inner = max(CARD_W + GAP_X * 2, canvas_width - MARGIN * 2)
    cards_per_row = max(1, (canvas_inner + GAP_X) // (CARD_W + GAP_X))

    for d in dir_order:
        files = by_dir[d]
        # Sort: most findings first, then path
        files.sort(key=lambda p: (-len(findings_by_file.get(p, [])), p))

        for i, fp in enumerate(files):
            col = i % cards_per_row
            row = i // cards_per_row
            x = MARGIN + col * (CARD_W + GAP_X)
            y = cur_y + row * (CARD_H + GAP_Y)
            file_findings = findings_by_file.get(fp, [])
            logged = sum(1 for f in file_findings if triage_status.get(_tkey(f)) == "logged")
            ignored = sum(1 for f in file_findings if triage_status.get(_tkey(f)) == "ignored")
            node = NodeInfo(
                file_path=fp,
                x=x,
                y=y,
                findings=file_findings,
                triaged_logged=logged,
                triaged_ignored=ignored,
            )
            nodes.append(node)
            by_path[fp] = node

        rows_used = (len(files) + cards_per_row - 1) // cards_per_row
        cur_y += rows_used * (CARD_H + GAP_Y) + SECTION_GAP

    canvas_height = max(CARD_H + MARGIN * 2, cur_y + MARGIN)

    canvas = Canvas(width=canvas_inner + MARGIN * 2, height=canvas_height)

    # 4. Draw edges first so cards overpaint endpoints (cleaner).
    valid_edges: list[tuple[str, str]] = []
    for src, dst in edges:
        if src == dst:
            continue
        if src in by_path and dst in by_path:
            valid_edges.append((src, dst))
            _draw_edge(canvas, by_path[src], by_path[dst])

    # 5. Draw cards.
    for d in dir_order:
        label = _section_label(d, node_paths)
        # Section label printed once above the first card row in this dir.
        first_card = by_path[by_dir[d][0]]
        canvas.put_str(first_card.x, first_card.y - 1, label, style="dim")

    for node in nodes:
        _draw_card(canvas, node, triage_status)

    return canvas, NodeMap(nodes=nodes, by_path=by_path, edges=valid_edges)


def _tkey(finding: Finding) -> str:
    return f"{finding.file_path}::{finding.rule_id}::{finding.line_start}"


def _section_label(dir_path: str, all_paths: list[str]) -> str:
    """A compact label like 'sample-vulns/' for a directory section."""
    if not all_paths:
        return Path(dir_path).name + "/"
    # Show the directory relative to the longest common parent of the
    # full node set — so a single-target scan reads "sample-vulns/" not
    # the full absolute path.
    try:
        common = _longest_common_parent(all_paths)
        rel = Path(dir_path).relative_to(common)
        return (str(rel) or ".") + "/"
    except (ValueError, IndexError):
        return Path(dir_path).name + "/"


def _longest_common_parent(paths: list[str]) -> Path:
    abs_paths = [Path(p).resolve() for p in paths]
    parts_list = [list(p.parts) for p in abs_paths]
    common: list[str] = []
    for parts_at_i in zip(*parts_list):
        first = parts_at_i[0]
        if all(p == first for p in parts_at_i):
            common.append(first)
        else:
            break
    return Path(*common) if common else Path("/")


# --- card rendering ---------------------------------------------------

def _peak_severity(findings: list[Finding]) -> Severity | None:
    if not findings:
        return None
    return max(f.severity for f in findings)


_SEV_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "blue",
    Severity.INFO: "dim white",
}


def _card_border_style(node: NodeInfo, triage_status: dict[str, str]) -> str:
    if not node.findings:
        return "dim"
    visible = [f for f in node.findings if triage_status.get(_tkey(f)) != "ignored"]
    if not visible:
        return "dim"
    sev = _peak_severity(visible)
    return _SEV_STYLE.get(sev, "white") if sev else "dim"


def _draw_card(canvas: Canvas, node: NodeInfo, triage_status: dict[str, str]) -> None:
    """Render a node's card into the canvas.

    Layout:
        ┌──────────────────┐
        │ ●●● HIGH         │
        │ filename.py      │
        │ Secrets Defense  │
        └──────────────────┘
    """
    style = _card_border_style(node, triage_status)
    x, y = node.x, node.y
    w, h = CARD_W, CARD_H

    # Box corners and edges.
    canvas.put(x, y, "┌", style)
    canvas.put(x + w - 1, y, "┐", style)
    canvas.put(x, y + h - 1, "└", style)
    canvas.put(x + w - 1, y + h - 1, "┘", style)
    for i in range(1, w - 1):
        canvas.put(x + i, y, "─", style)
        canvas.put(x + i, y + h - 1, "─", style)
    for i in range(1, h - 1):
        canvas.put(x, y + i, "│", style)
        canvas.put(x + w - 1, y + i, "│", style)

    # Row 1: dots + severity label
    visible = [f for f in node.findings if triage_status.get(_tkey(f)) != "ignored"]
    logged = sum(1 for f in node.findings if triage_status.get(_tkey(f)) == "logged")
    inner_w = w - 4  # account for "│ " ... " │"
    if visible:
        dots = ""
        dot_styles: list[str] = []
        sev_order = sorted(visible, key=lambda f: -int(f.severity))
        for f in sev_order[:5]:
            dots += _SEV_DOT[f.severity]
            dot_styles.append(_SEV_STYLE[f.severity])
        if len(sev_order) > 5:
            dots += f"+{len(sev_order)-5}"
        # Write dots with per-cell styling
        cx = x + 2
        for i, ch in enumerate(dots):
            s = dot_styles[i] if i < len(dot_styles) else "dim"
            canvas.put(cx + i, y + 1, ch, s)
        peak = _peak_severity(visible)
        sev_label = peak.name if peak else ""
        canvas.put_str(
            cx + len(dots) + 1,
            y + 1,
            sev_label[: inner_w - len(dots) - 1],
            style=_SEV_STYLE.get(peak, "") if peak else "",
        )
    else:
        # Card has only ignored findings (or none).
        canvas.put_str(x + 2, y + 1, "(quiet)", style="dim")

    # Row 2: filename
    filename = Path(node.file_path).name
    if len(filename) > inner_w:
        filename = filename[: inner_w - 1] + "…"
    canvas.put_str(x + 2, y + 2, filename, style="bold")

    # Row 3: category / triage status hint
    if visible:
        cat = classify_finding(visible[0])
        hint = cat.label[:inner_w]
        canvas.put_str(x + 2, y + 3, hint, style="dim")
    if logged > 0:
        marker = f"✓{logged}"
        canvas.put_str(x + w - 2 - len(marker), y + 3, marker, style="bright_green")


# --- edge routing -----------------------------------------------------

def _draw_edge(canvas: Canvas, src: NodeInfo, dst: NodeInfo) -> None:
    """Draw an L-shaped Manhattan path from src to dst.

    Pick the natural anchor pair based on relative position:
      * dst below src   → src bottom_anchor → dst top_anchor
      * dst above src   → src top_anchor    → dst bottom_anchor
      * dst right of src→ src right_anchor  → dst left_anchor
      * dst left of src → src left_anchor   → dst right_anchor

    Always route as a single right-angle (vertical-then-horizontal or
    horizontal-then-vertical) chosen to minimize the overlap with cards.
    """
    # Decide anchors.
    if dst.cy > src.bottom + 1:
        sx, sy = src.bottom_anchor
        dx, dy = dst.top_anchor
        _draw_v_then_h(canvas, sx, sy + 1, dx, dy - 1)
        _draw_arrow_head(canvas, dx, dy - 1, "down")
        return
    if dst.bottom + 1 < src.cy:
        sx, sy = src.top_anchor
        dx, dy = dst.bottom_anchor
        _draw_v_then_h(canvas, sx, sy - 1, dx, dy + 1)
        _draw_arrow_head(canvas, dx, dy + 1, "up")
        return
    # Same row(ish): horizontal route.
    if dst.cx > src.right:
        sx, sy = src.right_anchor
        dx, dy = dst.left_anchor
        _draw_h_then_v(canvas, sx + 1, sy, dx - 1, dy)
        _draw_arrow_head(canvas, dx - 1, dy, "right")
        return
    if dst.right < src.cx:
        sx, sy = src.left_anchor
        dx, dy = dst.right_anchor
        _draw_h_then_v(canvas, sx - 1, sy, dx + 1, dy)
        _draw_arrow_head(canvas, dx + 1, dy, "left")
        return
    # Overlapping cards — shouldn't happen with grid layout. No-op.


def _draw_v_then_h(canvas: Canvas, x1: int, y1: int, x2: int, y2: int) -> None:
    """Vertical from (x1, y1) → (x1, y2), then horizontal → (x2, y2)."""
    if y2 == y1:
        _line_h(canvas, x1, x2, y1)
        return
    if x2 == x1:
        _line_v(canvas, x1, y1, y2)
        return
    _line_v(canvas, x1, y1, y2)
    _line_h(canvas, x1, x2, y2)
    # Corner glyph at the bend.
    canvas.put(x1, y2, _bend_glyph(y1, y2, x1, x2), style="dim cyan")


def _draw_h_then_v(canvas: Canvas, x1: int, y1: int, x2: int, y2: int) -> None:
    if x2 == x1:
        _line_v(canvas, x1, y1, y2)
        return
    if y2 == y1:
        _line_h(canvas, x1, x2, y1)
        return
    _line_h(canvas, x1, x2, y1)
    _line_v(canvas, x2, y1, y2)
    canvas.put(x2, y1, _bend_glyph_h_first(x1, x2, y1, y2), style="dim cyan")


def _line_h(canvas: Canvas, x1: int, x2: int, y: int) -> None:
    lo, hi = sorted((x1, x2))
    for x in range(lo, hi + 1):
        existing = canvas.get(x, y)
        canvas.put(x, y, _merge_glyph(existing, "─"), style="dim cyan")


def _line_v(canvas: Canvas, x: int, y1: int, y2: int) -> None:
    lo, hi = sorted((y1, y2))
    for y in range(lo, hi + 1):
        existing = canvas.get(x, y)
        canvas.put(x, y, _merge_glyph(existing, "│"), style="dim cyan")


def _bend_glyph(y1: int, y2: int, x1: int, x2: int) -> str:
    """Choose a corner glyph for a vertical-then-horizontal bend at (x1, y2)."""
    going_down = y2 > y1
    going_right = x2 > x1
    if going_down and going_right:
        return "└"
    if going_down and not going_right:
        return "┘"
    if not going_down and going_right:
        return "┌"
    return "┐"


def _bend_glyph_h_first(x1: int, x2: int, y1: int, y2: int) -> str:
    """Corner glyph for a horizontal-then-vertical bend at (x2, y1)."""
    going_right = x2 > x1
    going_down = y2 > y1
    if going_right and going_down:
        return "┐"
    if going_right and not going_down:
        return "┘"
    if not going_right and going_down:
        return "┌"
    return "└"


def _merge_glyph(existing: str, new: str) -> str:
    """When two line segments cross, prefer a crossing glyph."""
    if existing == " " or existing == "":
        return new
    if existing == new:
        return new
    # Both line glyphs but different orientation → crossing.
    if {existing, new}.issubset({"─", "│"}):
        return "┼"
    return new  # Otherwise: new wins (e.g., crossing a corner)


def _draw_arrow_head(canvas: Canvas, x: int, y: int, direction: str) -> None:
    glyph = {"up": "▲", "down": "▼", "left": "◀", "right": "▶"}.get(direction, "·")
    canvas.put(x, y, glyph, style="cyan")
