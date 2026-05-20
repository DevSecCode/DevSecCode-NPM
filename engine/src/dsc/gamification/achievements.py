"""Achievement definitions + evaluation.

Each achievement key is stored in `Profile.achievements` once unlocked.
Re-running the same hunt won't re-unlock the same achievement — the
caller (`profile.record_hunt`) deduplicates against the existing list.

Achievements are deliberately checked against the *post-mutation*
profile (categories_defeated, hunts_completed, total_xp, level already
updated for this hunt) plus the just-recorded findings, so a single
hunt can cross a threshold and unlock something on its own merit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from dsc.scanner.models import Finding, Severity


@dataclass(frozen=True, slots=True)
class Achievement:
    key: str
    title: str
    description: str
    # icon glyph used in the unlock banner; kept ASCII for cross-term.
    glyph: str = "*"


# Predicate signature: (profile, findings, findings_by_category) -> bool.
_Predicate = Callable[..., bool]


# --- predicates -------------------------------------------------------

def _has_n_in_category(category_key: str, threshold: int) -> _Predicate:
    def _pred(profile, findings, findings_by_category) -> bool:
        return profile.categories_defeated.get(category_key, 0) >= threshold
    return _pred


def _hunts_at_least(threshold: int) -> _Predicate:
    def _pred(profile, findings, findings_by_category) -> bool:
        return profile.hunts_completed >= threshold
    return _pred


def _level_at_least(threshold: int) -> _Predicate:
    def _pred(profile, findings, findings_by_category) -> bool:
        return profile.level >= threshold
    return _pred


def _unique_rules_at_least(threshold: int) -> _Predicate:
    def _pred(profile, findings, findings_by_category) -> bool:
        return len(profile.unique_rules) >= threshold
    return _pred


def _clean_run(profile, findings, findings_by_category) -> bool:
    """No criticals or highs in this hunt's findings — and at least one hunt
    completed (so this can't fire on a literally empty repo with no rules)."""
    if profile.hunts_completed < 1:
        return False
    return not any(f.severity >= Severity.HIGH for f in findings)


# --- registry ---------------------------------------------------------

ACHIEVEMENTS: tuple[tuple[Achievement, _Predicate], ...] = (
    (
        Achievement(
            key="first-blood",
            title="First Blood",
            description="Found your first hardcoded secret.",
            glyph="*",
        ),
        _has_n_in_category("secrets", 1),
    ),
    (
        Achievement(
            key="secret-keeper",
            title="Secret Keeper",
            description="Defeated 10 hardcoded-credential findings across all hunts.",
            glyph="*",
        ),
        _has_n_in_category("secrets", 10),
    ),
    (
        Achievement(
            key="injector",
            title="Injector",
            description="Cleared 10 injection findings (SQLi / XSS / cmd / path).",
            glyph="+",
        ),
        _has_n_in_category("injection", 10),
    ),
    (
        Achievement(
            key="crypto-hardened",
            title="Crypto Hardened",
            description="Retired 5 weak-crypto findings.",
            glyph="#",
        ),
        _has_n_in_category("crypto", 5),
    ),
    (
        Achievement(
            key="container-warden",
            title="Container Warden",
            description="Hardened 5 Dockerfile / Kubernetes issues.",
            glyph="@",
        ),
        _has_n_in_category("container", 5),
    ),
    (
        Achievement(
            key="variety-hunter",
            title="Variety Hunter",
            description="Triggered 10 distinct public rules across your career.",
            glyph="~",
        ),
        _unique_rules_at_least(10),
    ),
    (
        Achievement(
            key="veteran",
            title="Veteran",
            description="Reached Level 5.",
            glyph="^",
        ),
        _level_at_least(5),
    ),
    (
        Achievement(
            key="tenured",
            title="Tenured",
            description="Completed 25 hunts.",
            glyph="^",
        ),
        _hunts_at_least(25),
    ),
    (
        Achievement(
            key="clean-sweep",
            title="Clean Sweep",
            description="Finished a hunt with zero high or critical findings.",
            glyph="=",
        ),
        _clean_run,
    ),
)


_BY_KEY: dict[str, Achievement] = {a.key: a for a, _ in ACHIEVEMENTS}


def get_achievement(key: str) -> Achievement | None:
    return _BY_KEY.get(key)


def evaluate_achievements(
    *,
    profile,
    findings: Iterable[Finding],
    findings_by_category: dict[str, int],
) -> list[str]:
    """Return the list of achievement keys that the profile satisfies.

    `profile.record_hunt` deduplicates against `profile.achievements` so
    we can safely return *all* currently-satisfied keys here; only the
    newly unlocked ones are reported to the user.
    """
    findings_list = list(findings)
    unlocked: list[str] = []
    for ach, pred in ACHIEVEMENTS:
        try:
            if pred(profile=profile, findings=findings_list, findings_by_category=findings_by_category):
                unlocked.append(ach.key)
        except Exception:
            # An evaluation bug must never crash a hunt. Skip silently.
            continue
    return unlocked
