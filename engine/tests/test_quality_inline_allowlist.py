"""Tests for the inline-allowlist filter in the quality layer.

Covers the comment markers the scan honors (`pragma: allowlist secret`,
`nosec`, etc.), the snippet-vs-disk-read fallback, and the
`DSC_DISABLE_INLINE_ALLOWLIST` opt-out.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dsc.scanner.models import Finding, Severity
from dsc.scanner.quality import (
    FULL_BALANCED,
    _ALLOWLIST_MARKERS,
    _has_inline_allowlist_marker,
    apply_quality_layer,
)


def _finding(
    *,
    snippet: str = "",
    file_path: str = "",
    line_start: int = 1,
    line_end: int = 1,
) -> Finding:
    return Finding(
        rule_id="deva.cwe-798.private-key-header",
        cwe="CWE-798",
        severity=Severity.CRITICAL,
        file_path=file_path,
        line_start=line_start,
        line_end=line_end,
        column=1,
        message="PEM-encoded private key material detected",
        snippet=snippet,
        metadata={
            "fingerprint": f"fp-{file_path}-{line_start}",
            "occurrence_id": f"occ-{file_path}-{line_start}",
            "precision_tier": "A",
            "confidence": 0.95,
            "family": "secrets",
        },
    )


# ───── marker recognition ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "snippet",
    [
        '"-----BEGIN PRIVATE KEY-----", // pragma: allowlist secret',
        '"-----BEGIN PRIVATE KEY-----", # pragma: allowlist secret',
        '"-----BEGIN PRIVATE KEY-----",  //pragma:allowlist secret',  # no spaces
        '"-----BEGIN PRIVATE KEY-----", // Pragma: Allowlist Secret',  # mixed case
        'password = "x"  # nosec',
        'password = "x"  # nosec B105',
        'password = "x"  # noqa: bandit',
        'password = "x"  # noqa: S105',
        'password = "x"  // nosemgrep',
        'password = "x"  // nosem',
        'password = "x"  // deva-ignore',
        'eval(input)  // lgtm[js/code-injection]',
    ],
)
def test_marker_recognized_in_snippet(snippet: str) -> None:
    f = _finding(snippet=snippet)
    assert _has_inline_allowlist_marker(f, target_root="/")


@pytest.mark.parametrize(
    "snippet",
    [
        '"-----BEGIN PRIVATE KEY-----"',
        '"-----BEGIN PRIVATE KEY-----", // legitimate code',
        'password = "x"  # this is a regular comment',
        # Adjacent words that look similar but aren't the marker.
        'allowlistsecret = "abc"',
        '// pragma allow list secret',  # missing the colon
    ],
)
def test_no_marker_means_kept(snippet: str) -> None:
    f = _finding(snippet=snippet)
    assert not _has_inline_allowlist_marker(f, target_root="/")


# ───── disk-read fallback ──────────────────────────────────────────────────


def test_marker_in_file_when_snippet_missing(tmp_path: Path) -> None:
    """Some rules don't include the trailing comment in the snippet
    (depends on how OpenGrep emits raw_lines). The filter must fall
    back to reading the actual source line.
    """
    src = tmp_path / "leak.py"
    src.write_text(
        'password = "hunter2"  # pragma: allowlist secret\n',
        encoding="utf-8",
    )
    f = _finding(
        snippet='password = "hunter2"',  # comment not in snippet
        file_path=str(src),
        line_start=1,
        line_end=1,
    )
    assert _has_inline_allowlist_marker(f, target_root=str(tmp_path))


def test_marker_on_different_line_does_not_match(tmp_path: Path) -> None:
    """The marker must be on the finding's line range (start..end);
    a pragma several lines earlier doesn't allowlist later findings.
    """
    src = tmp_path / "two-secrets.py"
    src.write_text(
        '\n'.join([
            'first = "abc"  # pragma: allowlist secret',
            'unrelated = 1',
            'unrelated = 2',
            'second = "real-secret"',  # line 4: NOT allowlisted
        ]) + '\n',
        encoding="utf-8",
    )
    f = _finding(
        snippet='second = "real-secret"',
        file_path=str(src),
        line_start=4,
        line_end=4,
    )
    assert not _has_inline_allowlist_marker(f, target_root=str(tmp_path))


def test_missing_file_returns_false_not_raises(tmp_path: Path) -> None:
    f = _finding(
        snippet='password = "x"',
        file_path=str(tmp_path / "nope.py"),
        line_start=1,
        line_end=1,
    )
    # Should swallow the OSError and just return False rather than crash.
    assert _has_inline_allowlist_marker(f, target_root=str(tmp_path)) is False


# ───── apply_quality_layer integration ─────────────────────────────────────


def test_apply_quality_layer_drops_allowlisted(tmp_path: Path) -> None:
    """End-to-end: a CRITICAL finding annotated with `pragma: allowlist
    secret` must not survive apply_quality_layer.
    """
    f_keep = _finding(
        snippet='"-----BEGIN PRIVATE KEY-----actual-leaked-key"',
        file_path=str(tmp_path / "leak.py"),
        line_start=10,
    )
    f_drop = _finding(
        snippet='"-----BEGIN PRIVATE KEY-----abc", // pragma: allowlist secret',
        file_path=str(tmp_path / "test_fixture.ts"),
        line_start=42,
    )
    out = apply_quality_layer(
        [f_keep, f_drop],
        detectors={},
        target_root=str(tmp_path),
        policy=FULL_BALANCED,
        suppressions={},
    )
    paths = [o.file_path for o in out]
    assert any("leak.py" in p for p in paths)
    assert not any("test_fixture.ts" in p for p in paths)


def test_apply_quality_layer_respects_opt_out_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setting DSC_DISABLE_INLINE_ALLOWLIST=1 keeps even allowlisted
    findings — useful for audit runs where every flag matters.
    """
    monkeypatch.setenv("DSC_DISABLE_INLINE_ALLOWLIST", "1")
    f_drop = _finding(
        snippet='"-----BEGIN PRIVATE KEY-----", // pragma: allowlist secret',
        file_path=str(tmp_path / "test_fixture.ts"),
        line_start=42,
    )
    out = apply_quality_layer(
        [f_drop],
        detectors={},
        target_root=str(tmp_path),
        policy=FULL_BALANCED,
        suppressions={},
    )
    assert len(out) == 1


# ───── regex shape sanity ──────────────────────────────────────────────────


def test_marker_regex_is_case_insensitive() -> None:
    assert _ALLOWLIST_MARKERS.search("Pragma: Allowlist Secret")
    assert _ALLOWLIST_MARKERS.search("NOSEC")
    assert _ALLOWLIST_MARKERS.search("NoSemgrep")
