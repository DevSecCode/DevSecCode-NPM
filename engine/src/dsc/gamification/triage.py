"""Per-finding triage state — logged / ignored / unseen.

Stored at `~/.devseccode/triage.json` (alongside profile.json). The
triage map keys findings by (rel_path, rule_id, line_start) so the
state survives re-scans: same finding, same triage decision.

Status semantics:
  - "logged"  — player confirmed this is a real vulnerability and will
                handle it. Still counts toward XP but renders with ✓.
  - "ignored" — player dismissed it (false positive or accepted risk).
                Hidden from the default map view and the summary card.
  - "unseen"  — implicit default. Renders normally.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from dsc.gamification.profile import _profile_root
from dsc.scanner.models import Finding


TriageStatus = Literal["unseen", "logged", "ignored"]

VALID_STATUSES: tuple[TriageStatus, ...] = ("unseen", "logged", "ignored")
TRIAGE_VERSION = 1


def triage_path() -> Path:
    return _profile_root() / "triage.json"


def _finding_key(finding: Finding) -> str:
    """Stable key derived from the finding's identity, not its severity.

    Severity can change between scans (rule edits, --scan-profile changes),
    so we deliberately exclude it. Identity = (file path, rule, line) —
    enough to recognize the same finding next time the player scans.
    """
    return f"{finding.file_path}::{finding.rule_id}::{finding.line_start}"


@dataclass
class TriageStore:
    """In-memory mirror of triage.json with atomic save."""
    version: int = TRIAGE_VERSION
    entries: dict[str, TriageStatus] = field(default_factory=dict)

    def status_of(self, finding: Finding) -> TriageStatus:
        return self.entries.get(_finding_key(finding), "unseen")

    def set_status(self, finding: Finding, status: TriageStatus) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid triage status: {status!r}")
        key = _finding_key(finding)
        if status == "unseen":
            self.entries.pop(key, None)
        else:
            self.entries[key] = status

    def filter_visible(self, findings: Iterable[Finding]) -> list[Finding]:
        """Hide ignored findings; keep logged + unseen."""
        return [f for f in findings if self.status_of(f) != "ignored"]

    def to_dict(self) -> dict:
        return {"version": self.version, "entries": dict(self.entries)}

    @classmethod
    def from_dict(cls, data: dict) -> "TriageStore":
        raw_entries = data.get("entries") or {}
        entries: dict[str, TriageStatus] = {}
        for k, v in raw_entries.items():
            if v in VALID_STATUSES and v != "unseen":
                entries[str(k)] = v  # type: ignore[assignment]
        return cls(
            version=int(data.get("version") or TRIAGE_VERSION),
            entries=entries,
        )


def load_triage() -> TriageStore:
    path = triage_path()
    if not path.exists():
        return TriageStore()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return TriageStore.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return TriageStore()


def save_triage(store: TriageStore) -> None:
    path = triage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store.to_dict(), indent=2, sort_keys=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".triage.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
