"""Tests for the test-file filter in the quality layer.

The filter drops findings under test / spec / fixture paths because
they routinely contain deliberately-bad-looking content (fake keys,
fake emails, sample payloads) that's noise in a security report.
Covers path-pattern recognition, opt-out env var, and per-rule
opt-in via metadata.
"""
from __future__ import annotations

import pytest

from dsc.scanner.models import Finding, Severity
from dsc.scanner.quality import (
    FULL_BALANCED,
    apply_quality_layer,
    is_test_path,
)


def _finding(*, file_path: str, line_start: int = 10, metadata: dict | None = None) -> Finding:
    meta = {
        "fingerprint": f"fp-{file_path}-{line_start}",
        "occurrence_id": f"occ-{file_path}-{line_start}",
        "precision_tier": "A",
        "confidence": 0.95,
        "family": "secrets",
    }
    if metadata:
        meta.update(metadata)
    return Finding(
        rule_id="deva.cwe-798.private-key-header",
        cwe="CWE-798",
        severity=Severity.CRITICAL,
        file_path=file_path,
        line_start=line_start,
        line_end=line_start,
        column=1,
        message="PEM-encoded private key material detected",
        snippet='"-----BEGIN PRIVATE KEY-----abc"',
        metadata=meta,
    )


# ───── path pattern recognition ────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        # Jest / Vitest / Mocha
        "src/foo.test.ts",
        "src/foo.test.tsx",
        "src/foo.test.js",
        "src/foo.test.jsx",
        "src/foo.spec.ts",
        "src/foo.spec.js",
        "/abs/path/__tests__/foo.ts",
        "src/__tests__/snapshots/foo.test.ts",
        "__mocks__/fs.ts",
        # pytest
        "tests/test_module.py",
        "src/my_pkg/test_helpers.py",
        # Go
        "internal/cache/cache_test.go",
        "pkg/runner_test.go",
        # Rust
        "src/parser_test.rs",
        # Java / Kotlin / Swift xUnit-family
        "src/test/java/com/foo/UserServiceTest.java",
        "android/app/src/test/UserTests.kt",
        "Tests/SwiftTests.swift",
        # Ruby
        "spec/models/user_spec.rb",
        "spec/foo_spec.rb",
        "test/foo_test.rb",
        # C#
        "src/MyLib.Tests/UserTests.cs",
        # Cypress / Playwright / e2e
        "cypress/integration/login.spec.ts",
        "e2e/login.spec.ts",
        "playwright/login.spec.ts",
        # Bare test/tests directories
        "tests/integration/auth.py",
        "test/fixtures/data.json",
        # Test fixtures
        "fixtures/user.json",
        "test-fixtures/sample.txt",
        "testdata/golden.json",  # Go convention
        # Windows paths
        r"src\foo.test.ts",
        r"src\__tests__\foo.ts",
    ],
)
def test_is_test_path_true(path: str) -> None:
    assert is_test_path(path), f"expected {path!r} to be a test path"


@pytest.mark.parametrize(
    "path",
    [
        # Production source
        "src/foo.ts",
        "src/auth/login.ts",
        "lib/parser.py",
        "internal/cache/cache.go",
        # Names that contain "test" as a substring but aren't tests.
        # We're intentionally permissive on directory names so this
        # is best-effort: "testing-library" would match "test" word
        # boundary but on the dir-pattern path it'd need to be a
        # whole segment; "testing-library/foo.ts" should NOT be a
        # test path.
        "src/testing-library/foo.ts",
        "src/contests/scoring.ts",         # "test" inside "contests"
        "src/protesting.ts",                # "test" inside "protesting"
        # Docs / config / generated
        "README.md",
        "package.json",
        "src/schema.generated.ts",
        # Empty / weird inputs
        "",
        "/",
    ],
)
def test_is_test_path_false(path: str) -> None:
    assert not is_test_path(path), f"expected {path!r} NOT to be a test path"


# ───── apply_quality_layer integration ─────────────────────────────────────


def test_findings_in_test_files_are_dropped() -> None:
    prod = _finding(file_path="/ws/src/auth.ts")
    test = _finding(file_path="/ws/src/auth.test.ts")
    spec = _finding(file_path="/ws/src/auth.spec.ts")
    fixture = _finding(file_path="/ws/__tests__/fixtures/key.pem")
    go = _finding(file_path="/ws/cache_test.go")

    out = apply_quality_layer(
        [prod, test, spec, fixture, go],
        detectors={},
        target_root="/ws",
        policy=FULL_BALANCED,
        suppressions={},
    )
    paths = [o.file_path for o in out]
    assert paths == ["/ws/src/auth.ts"]


def test_per_rule_opt_in_keeps_test_findings() -> None:
    """A rule that declares apply_to_tests=true on the finding's
    metadata survives the test-file filter. No bundled rule sets this
    today; the hook is here for future rules like "test fixture leaks
    a production credential".
    """
    test_finding = _finding(
        file_path="/ws/src/auth.test.ts",
        metadata={"apply_to_tests": True},
    )
    out = apply_quality_layer(
        [test_finding],
        detectors={},
        target_root="/ws",
        policy=FULL_BALANCED,
        suppressions={},
    )
    assert len(out) == 1
    assert out[0].file_path == "/ws/src/auth.test.ts"


def test_nested_deva_apply_to_tests_metadata_works() -> None:
    """Some rules carry `apply_to_tests` under a nested `deva` subdict
    rather than as a top-level metadata key. The filter respects both.
    """
    test_finding = _finding(
        file_path="/ws/src/auth.test.ts",
        metadata={"deva": {"apply_to_tests": True}},
    )
    out = apply_quality_layer(
        [test_finding],
        detectors={},
        target_root="/ws",
        policy=FULL_BALANCED,
        suppressions={},
    )
    assert len(out) == 1


def test_env_opt_out_keeps_test_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DSC_INCLUDE_TEST_FINDINGS=1 disables the filter entirely."""
    monkeypatch.setenv("DSC_INCLUDE_TEST_FINDINGS", "1")
    test_finding = _finding(file_path="/ws/src/auth.test.ts")
    out = apply_quality_layer(
        [test_finding],
        detectors={},
        target_root="/ws",
        policy=FULL_BALANCED,
        suppressions={},
    )
    assert len(out) == 1


def test_test_filter_and_allowlist_filter_compose() -> None:
    """Both filters run on the same finding stream; either should fire
    independently. A test-file finding with no pragma still gets
    dropped (by the test filter); a prod-file finding with a pragma
    still gets dropped (by the allowlist filter).
    """
    prod_kept = _finding(file_path="/ws/src/auth.ts")
    prod_pragma = Finding(
        rule_id="deva.cwe-798.private-key-header",
        cwe="CWE-798",
        severity=Severity.CRITICAL,
        file_path="/ws/src/keys.ts",
        line_start=5,
        line_end=5,
        column=1,
        message="key detected",
        snippet='"BEGIN PRIVATE KEY" // pragma: allowlist secret',
        metadata={
            "fingerprint": "fp-pragma",
            "occurrence_id": "occ-pragma",
            "precision_tier": "A",
            "confidence": 0.95,
        },
    )
    test_no_pragma = _finding(file_path="/ws/src/auth.test.ts")

    out = apply_quality_layer(
        [prod_kept, prod_pragma, test_no_pragma],
        detectors={},
        target_root="/ws",
        policy=FULL_BALANCED,
        suppressions={},
    )
    paths = [o.file_path for o in out]
    assert paths == ["/ws/src/auth.ts"]
