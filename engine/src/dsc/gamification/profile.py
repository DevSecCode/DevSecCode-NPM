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
from datetime import datetime, timedelta, timezone
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


DIFFICULTY_MODES = ("easy", "normal", "hard")

# Difficulty → severity threshold for gate pass.
DIFFICULTY_FAIL_ON = {
    "easy": Severity.CRITICAL,    # only criticals fail
    "normal": Severity.HIGH,       # high+ fails (default)
    "hard": Severity.MEDIUM,       # medium+ fails
}

# XP multiplier per difficulty.
DIFFICULTY_XP_MULT = {
    "easy": 0.75,
    "normal": 1.0,
    "hard": 1.5,
}


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
    # Streak tracking.
    current_streak: int = 0
    longest_streak: int = 0
    last_streak_date: str = ""   # YYYY-MM-DD of last hunt
    # Difficulty mode.
    difficulty: str = "normal"
    # Loot — cosmetic titles the player has earned.
    loot: list[str] = field(default_factory=list)
    active_title: str | None = None
    # Leaderboard — best shield scores per target.
    best_scores: dict[str, int] = field(default_factory=dict)

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
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "last_streak_date": self.last_streak_date,
            "difficulty": self.difficulty,
            "loot": list(self.loot),
            "active_title": self.active_title,
            "best_scores": dict(self.best_scores),
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
            current_streak=int(data.get("current_streak") or 0),
            longest_streak=int(data.get("longest_streak") or 0),
            last_streak_date=str(data.get("last_streak_date") or ""),
            difficulty=str(data.get("difficulty") or "normal"),
            loot=[str(l) for l in (data.get("loot") or [])],
            active_title=data.get("active_title"),
            best_scores={str(k): int(v) for k, v in (data.get("best_scores") or {}).items()},
        )


XP_PER_STREAK_DAY = 5    # bonus per consecutive day of hunting


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
    streak: int = 0
    streak_bonus: int = 0
    new_loot: list[str] = field(default_factory=list)
    new_best_score: bool = False
    difficulty: str = "normal"


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


def set_hunter_class(profile: Profile, key: str) -> None:
    """Update the player's chosen character and persist."""
    profile.hunter_class = key
    save_profile(profile)


def record_hunt(
    profile: Profile,
    findings: Iterable[Finding],
    *,
    achievements_evaluator=None,
    target_key: str | None = None,
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

    # Streak tracking.
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    streak_bonus = 0
    if profile.last_streak_date == today:
        # Already hunted today — streak stays the same.
        pass
    elif profile.last_streak_date == yesterday:
        # Consecutive day — extend streak.
        profile.current_streak += 1
        streak_bonus = min(profile.current_streak, 10) * XP_PER_STREAK_DAY
    else:
        # Streak broken (or first hunt).
        profile.current_streak = 1 if profile.hunts_completed > 0 else 1
    profile.last_streak_date = today
    if profile.current_streak > profile.longest_streak:
        profile.longest_streak = profile.current_streak

    # Difficulty XP multiplier.
    diff_mult = DIFFICULTY_XP_MULT.get(profile.difficulty, 1.0)

    xp_delta = int((
        xp_from_findings
        + XP_PER_HUNT
        + new_rules * XP_PER_NEW_RULE
        + (XP_FIRST_HUNT_BONUS if is_first_hunt else 0)
        + streak_bonus
    ) * diff_mult)

    profile.total_xp += xp_delta
    profile.hunts_completed += 1
    profile.last_hunt_at = _now_iso()

    # Loot drops — roll for cosmetic titles at milestones.
    new_loot = _roll_loot(profile, findings)
    for loot_key in new_loot:
        if loot_key not in profile.loot:
            profile.loot.append(loot_key)

    # Leaderboard — track best shield score per target.
    new_best_score = False
    if target_key is not None:
        from dsc.gamification.summary import shield_score
        score, _, _ = shield_score(findings)
        prev_best = profile.best_scores.get(target_key, -1)
        if score > prev_best:
            profile.best_scores[target_key] = score
            new_best_score = prev_best >= 0  # Only "new best" if there was a previous

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
        streak=profile.current_streak,
        streak_bonus=streak_bonus,
        new_loot=new_loot,
        new_best_score=new_best_score,
        difficulty=profile.difficulty,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Loot drop system ────────────────────────────────────────────────
# Cosmetic titles earned at specific milestones. Each loot item has a
# key, display name, and a predicate checked after every hunt. Once
# dropped, loot persists in the profile and the player can set an
# active_title.

_LOOT_TABLE: list[tuple[str, str, str]] = [
    # (key, display_name, description)
    ("title-rookie", "Rookie Hunter", "Complete your first hunt"),
    ("title-seasoned", "Seasoned Hunter", "Complete 10 hunts"),
    ("title-veteran", "Battle-Scarred", "Complete 50 hunts"),
    ("title-legend", "Living Legend", "Complete 100 hunts"),
    ("title-streak-3", "Consistent", "3-day hunt streak"),
    ("title-streak-7", "Relentless", "7-day hunt streak"),
    ("title-streak-30", "Unstoppable", "30-day hunt streak"),
    ("title-clean", "Perfectionist", "Score 100/100 shield on any target"),
    ("title-hard-mode", "Glutton for Punishment", "Complete a hunt on hard difficulty"),
    ("title-variety", "Polyglot", "Trigger 20 distinct rules"),
    ("title-secret-slayer", "Secret Slayer", "Defeat 25 credential findings"),
    ("title-injection-master", "Injection Master", "Defeat 25 injection findings"),
    ("title-xp-1000", "Thousandaire", "Earn 1,000 total XP"),
    ("title-xp-5000", "XP Hoarder", "Earn 5,000 total XP"),
    ("title-level-10", "Double Digits", "Reach level 10"),
]


def _roll_loot(profile: Profile, findings: list[Finding]) -> list[str]:
    """Check every loot item and return newly earned keys."""
    earned: list[str] = []
    already = set(profile.loot)

    def _check(key: str, condition: bool) -> None:
        if key not in already and condition:
            earned.append(key)

    _check("title-rookie", profile.hunts_completed >= 1)
    _check("title-seasoned", profile.hunts_completed >= 10)
    _check("title-veteran", profile.hunts_completed >= 50)
    _check("title-legend", profile.hunts_completed >= 100)
    _check("title-streak-3", profile.current_streak >= 3)
    _check("title-streak-7", profile.current_streak >= 7)
    _check("title-streak-30", profile.current_streak >= 30)
    _check("title-hard-mode", profile.difficulty == "hard" and profile.hunts_completed >= 1)
    _check("title-variety", len(profile.unique_rules) >= 20)
    _check("title-secret-slayer", profile.categories_defeated.get("secrets", 0) >= 25)
    _check("title-injection-master", profile.categories_defeated.get("injection", 0) >= 25)
    _check("title-xp-1000", profile.total_xp >= 1000)
    _check("title-xp-5000", profile.total_xp >= 5000)
    _check("title-level-10", profile.level >= 10)

    # Shield 100 check requires import.
    if "title-clean" not in already:
        try:
            from dsc.gamification.summary import shield_score
            score, _, _ = shield_score(findings)
            if score >= 100:
                earned.append("title-clean")
        except Exception:
            pass

    return earned


def get_loot_info(key: str) -> tuple[str, str] | None:
    """Return (display_name, description) for a loot key."""
    for k, name, desc in _LOOT_TABLE:
        if k == key:
            return name, desc
    return None


def set_difficulty(profile: Profile, difficulty: str) -> None:
    """Change difficulty and persist."""
    if difficulty not in DIFFICULTY_MODES:
        raise ValueError(f"Invalid difficulty: {difficulty!r}. Must be one of {DIFFICULTY_MODES}")
    profile.difficulty = difficulty
    save_profile(profile)


def set_active_title(profile: Profile, title_key: str | None) -> None:
    """Set or clear the player's displayed title."""
    if title_key is not None and title_key not in profile.loot:
        raise ValueError(f"Title {title_key!r} not yet earned.")
    profile.active_title = title_key
    save_profile(profile)
