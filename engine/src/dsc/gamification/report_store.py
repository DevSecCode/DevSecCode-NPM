"""Persistent last-hunt report storage.

Saves the most recent hunt summary to ~/.devseccode/last_report.json
so the player can view or export it later from the play menu without
re-running the scan.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from dsc.gamification.profile import _profile_root
from dsc.scanner.models import Finding, Severity


def _report_path() -> Path:
    return _profile_root() / "last_report.json"


@dataclass
class StoredReport:
    """Serializable snapshot of a hunt's results."""
    timestamp: str = ""
    targets: list[str] = field(default_factory=list)
    total_findings: int = 0
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    findings_by_category: dict[str, int] = field(default_factory=dict)
    shield_score: int = 0
    shield_rank: str = ""
    files_scanned: int = 0
    duration_ms: int = 0
    gate_passed: bool = True
    xp_earned: int = 0
    level_after: int = 0
    new_achievements: list[str] = field(default_factory=list)
    # Per-finding detail for export.
    finding_details: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "targets": self.targets,
            "total_findings": self.total_findings,
            "findings_by_severity": self.findings_by_severity,
            "findings_by_category": self.findings_by_category,
            "shield_score": self.shield_score,
            "shield_rank": self.shield_rank,
            "files_scanned": self.files_scanned,
            "duration_ms": self.duration_ms,
            "gate_passed": self.gate_passed,
            "xp_earned": self.xp_earned,
            "level_after": self.level_after,
            "new_achievements": self.new_achievements,
            "finding_details": self.finding_details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StoredReport":
        return cls(
            timestamp=str(data.get("timestamp", "")),
            targets=[str(t) for t in (data.get("targets") or [])],
            total_findings=int(data.get("total_findings", 0)),
            findings_by_severity={str(k): int(v) for k, v in (data.get("findings_by_severity") or {}).items()},
            findings_by_category={str(k): int(v) for k, v in (data.get("findings_by_category") or {}).items()},
            shield_score=int(data.get("shield_score", 0)),
            shield_rank=str(data.get("shield_rank", "")),
            files_scanned=int(data.get("files_scanned", 0)),
            duration_ms=int(data.get("duration_ms", 0)),
            gate_passed=bool(data.get("gate_passed", True)),
            xp_earned=int(data.get("xp_earned", 0)),
            level_after=int(data.get("level_after", 0)),
            new_achievements=[str(a) for a in (data.get("new_achievements") or [])],
            finding_details=list(data.get("finding_details") or []),
        )


def build_report(
    *,
    findings: list[Finding],
    targets: list[Path],
    files_scanned: int,
    duration_ms: int,
    gate_passed: bool,
    xp_earned: int,
    level_after: int,
    new_achievements: list[str],
    findings_by_category: dict[str, int],
) -> StoredReport:
    """Build a StoredReport from hunt results."""
    from collections import defaultdict
    from datetime import datetime, timezone

    from dsc.gamification.summary import shield_score

    sev_counts: dict[str, int] = defaultdict(int)
    details: list[dict] = []
    for f in findings:
        sev_counts[f.severity.name] += 1
        details.append({
            "file": f.file_path,
            "line": f.line_start,
            "rule_id": f.rule_id,
            "cwe": f.cwe,
            "severity": f.severity.name,
            "message": f.message or "",
            "snippet": f.snippet or "",
            "fix": f.fix_suggestion or "",
        })

    score, rank, _stars = shield_score(findings)

    return StoredReport(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        targets=[str(t) for t in targets],
        total_findings=len(findings),
        findings_by_severity=dict(sev_counts),
        findings_by_category=dict(findings_by_category),
        shield_score=score,
        shield_rank=rank,
        files_scanned=files_scanned,
        duration_ms=duration_ms,
        gate_passed=gate_passed,
        xp_earned=xp_earned,
        level_after=level_after,
        new_achievements=new_achievements,
        finding_details=details,
    )


def save_report(report: StoredReport) -> None:
    """Persist the report to ~/.devseccode/last_report.json."""
    path = _report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report.to_dict(), indent=2)
    fd, tmp = tempfile.mkstemp(prefix=".report.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_report() -> StoredReport | None:
    """Load the last saved report, or None if no report exists."""
    path = _report_path()
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return StoredReport.from_dict(data)
    except (OSError, json.JSONDecodeError):
        return None


def export_report(report: StoredReport, output_path: str) -> str:
    """Export the report to a file. Returns the absolute path written."""
    out = Path(output_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return str(out)
