"""Persistent hunter profile (~/.devseccode/profile.json).

Tracks XP, level, class pick, hunts completed, per-category defeats,
rules first-encountered, and earned achievement keys. The profile is
the single source of truth across hunts — every `devseccode hunt`
reads, updates, and writes it atomically.

CI / scriptable surfaces (`devseccode scan ...`) intentionally do not
touch the profile. Side-effecting global state from a non-interactive
scan would surprise users running this in pipelines.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from dsc.gamification.categories import (
    ALL_CATEGORIES,
    DefenseCategory,
    classify_finding,
)
from dsc.scanner.models import Finding, Severity


PROFILE_VERSION = 1
XP_PER_LEVEL = 100

# XP per finding by severity. Tuned so a typical first hunt (a handful
# of HIGH findings on a vulnerable repo) ranks the player at Level 1
# and gives the first achievement a satisfying chime.
_XP_PER_SEVERITY: dict[Severity, int] = {
    Severity.CRITICAL: 25,
    Severity.HIGH: 15,
    Severity.MEDIUM: 8,
    Severity.LOW: 3,
    Severity.INFO: 1,
}

XP_PER_HUNT = 10            # base reward just for running a hunt
XP_PER_NEW_RULE = 10        # bonus per rule never triggered before
XP_FIRST_HUNT_BONUS = 25    # one-time bonus on first hunt


def _profile_root() -> Path:
    """Resolve `~/.devseccode/`, honoring DEVSECCODE_HOME for tests."""
    override = os.environ.get("DEVSECCODE_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".devseccode"


def profile_path() -> Path:
    return _profile_root() / "profile.json"


@dataclass
class Profile:
    version: int = PROFILE_VERSION
    hunter_class: str | None = None
    total_xp: int = 0
    hunts_completed: int = 0
    created_at: str = ""
    last_hunt_at: str = ""
    categories_defeated: dict[str, int] = field(
        default_factory=lambda: {cat.key: 0 for cat in ALL_CATEGORIES}
    )
    unique_rules: list[str] = field(default_factory=list)
    achievements: list[str] = field(default_factory=list)

    @property
    def level(self) -> int:
        return self.total_xp // XP_PER_LEVEL

    @property
    def xp_into_level(self) -> int:
        return self.total_xp % XP_PER_LEVEL

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "hunter_class": self.hunter_class,
            "total_xp": self.total_xp,
            "hunts_completed": self.hunts_completed,
            "created_at": self.created_at,
            "last_hunt_at": self.last_hunt_at,
            "categories_defeated": dict(self.categories_defeated),
            "unique_rules": list(self.unique_rules),
            "achievements": list(self.achievements),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        # Fill in missing keys defensively — older profiles from earlier
        # versions should keep loading rather than wiping the user's XP.
        cats = {cat.key: 0 for cat in ALL_CATEGORIES}
        cats.update({str(k): int(v) for k, v in (data.get("categories_defeated") or {}).items()})
        return cls(
            version=int(data.get("version") or PROFILE_VERSION),
            hunter_class=data.get("hunter_class"),
            total_xp=int(data.get("total_xp") or 0),
            hunts_completed=int(data.get("hunts_completed") or 0),
            created_at=str(data.get("created_at") or ""),
            last_hunt_at=str(data.get("last_hunt_at") or ""),
            categories_defeated=cats,
            unique_rules=[str(r) for r in (data.get("unique_rules") or [])],
            achievements=[str(a) for a in (data.get("achievements") or [])],
        )


@dataclass(frozen=True, slots=True)
class HuntRecord:
    """Deltas from a single hunt, used to render the summary card."""
    xp_before: int
    xp_after: int
    xp_delta: int
    level_before: int
    level_after: int
    level_up: bool
    new_rules: int
    findings_by_category: dict[str, int]
    new_achievements: list[str]


def load_profile() -> Profile:
    path = profile_path()
    if not path.exists():
        now = _now_iso()
        return Profile(created_at=now, last_hunt_at="")
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return Profile.from_dict(data)
    except (OSError, json.JSONDecodeError):
        # Don't crash a hunt because the profile file got corrupted; start
        # over but preserve the file by leaving the corrupt one in place
        # (the next save will overwrite). The hunt UX is too brittle to
        # die on a bad JSON in a config file.
        return Profile(created_at=_now_iso(), last_hunt_at="")


def save_profile(profile: Profile) -> None:
    path = profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(profile.to_dict(), indent=2, sort_keys=True)
    # Atomic write so a Ctrl-C mid-write leaves the previous file intact.
    fd, tmp_path = tempfile.mkstemp(prefix=".profile.", suffix=".json", dir=str(path.parent))
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


def record_hunt(
    profile: Profile,
    findings: Iterable[Finding],
    *,
    achievements_evaluator=None,
) -> HuntRecord:
    """Apply a hunt's findings to the profile and return the deltas.

    Mutates `profile` in place; the caller is responsible for save_profile.
    Separating mutation from persistence lets `cmd_hunt` decide whether
    to commit (default) or skip the write (e.g. `--no-profile`).

    `achievements_evaluator` is injected to avoid an import cycle —
    `achievements` imports `profile.HuntRecord`, so we accept the
    evaluator as a callable here instead of importing it at module top.
    """
    findings = list(findings)

    xp_before = profile.total_xp
    level_before = profile.level
    is_first_hunt = profile.hunts_completed == 0

    findings_by_category: dict[str, int] = {cat.key: 0 for cat in ALL_CATEGORIES}
    new_rules = 0
    xp_from_findings = 0

    known_rules = set(profile.unique_rules)
    for f in findings:
        cat = classify_finding(f)
        findings_by_category[cat.key] += 1
        profile.categories_defeated[cat.key] = (
            profile.categories_defeated.get(cat.key, 0) + 1
        )
        xp_from_findings += _XP_PER_SEVERITY.get(f.severity, 0)
        if f.rule_id and f.rule_id not in known_rules:
            new_rules += 1
            known_rules.add(f.rule_id)
            profile.unique_rules.append(f.rule_id)

    xp_delta = (
        xp_from_findings
        + XP_PER_HUNT
        + new_rules * XP_PER_NEW_RULE
        + (XP_FIRST_HUNT_BONUS if is_first_hunt else 0)
    )
    profile.total_xp += xp_delta
    profile.hunts_completed += 1
    profile.last_hunt_at = _now_iso()

    new_achievements: list[str] = []
    if achievements_evaluator is not None:
        already = set(profile.achievements)
        unlocked = achievements_evaluator(
            profile=profile,
            findings=findings,
            findings_by_category=findings_by_category,
        )
        for ach_key in unlocked:
            if ach_key not in already:
                profile.achievements.append(ach_key)
                new_achievements.append(ach_key)
                already.add(ach_key)

    return HuntRecord(
        xp_before=xp_before,
        xp_after=profile.total_xp,
        xp_delta=xp_delta,
        level_before=level_before,
        level_after=profile.level,
        level_up=profile.level > level_before,
        new_rules=new_rules,
        findings_by_category=findings_by_category,
        new_achievements=new_achievements,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
