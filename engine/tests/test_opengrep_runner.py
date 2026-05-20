"""Regression tests for the OpenGrep subprocess runner.

The runner accepts exit codes 0 / 1 / 2 as recoverable but has to
distinguish two different exit-2 scenarios:

  - exit 2 with JSON on stdout = rule-parse errors, valid rules still
    ran. Recoverable, log a warning and return what we have.
  - exit 2 with empty / unparseable stdout = OpenGrep rejected the CLI
    (unknown flag, bad option value) or died before emitting JSON.
    Not recoverable -- raise so the caller sees the error instead of
    silently treating it as "0 findings".

These tests exercise both branches by stubbing ``subprocess.run`` so
no real OpenGrep binary is required.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from dsc.engine.opengrep_runner import (
    OpenGrepError,
    OpenGrepResult,
    OpenGrepRunner,
)


@dataclass
class _FakeCompletedProcess:
    returncode: int
    stdout: bytes
    stderr: bytes


def _runner_with_stub(monkeypatch, fake_proc: _FakeCompletedProcess) -> OpenGrepRunner:
    """Build an OpenGrepRunner whose subprocess.run is replaced with a stub.

    Also short-circuits binary resolution so we don't need the real
    OpenGrep binary on disk.
    """
    monkeypatch.setattr(
        OpenGrepRunner,
        "_resolve_binary",
        staticmethod(lambda _binary: Path("/usr/bin/true")),
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: fake_proc,
    )
    return OpenGrepRunner(timeout_seconds=60)


@pytest.fixture
def tmp_target(tmp_path: Path) -> Path:
    """A real file to satisfy the runner's `target.exists()` check."""
    f = tmp_path / "sample.py"
    f.write_text("x = 1\n", encoding="utf-8")
    return f


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """A real config dir to satisfy the runner's `config.exists()` check."""
    d = tmp_path / "rulepack"
    d.mkdir()
    return d


def test_exit_2_with_empty_stdout_is_fatal(monkeypatch, tmp_target, tmp_config):
    """OpenGrep rejecting a CLI flag exits 2 with no stdout. The runner
    must raise, not silently emit a zero-finding result.
    """
    fake = _FakeCompletedProcess(
        returncode=2,
        stdout=b"",
        stderr=b"Usage: opengrep scan [OPTIONS] [TARGETS]...\n"
               b"Error: No such option: --exclude-minified-files\n",
    )
    runner = _runner_with_stub(monkeypatch, fake)

    with pytest.raises(OpenGrepError) as excinfo:
        runner.scan(tmp_target, config=tmp_config)
    msg = str(excinfo.value)
    assert "empty stdout" in msg
    assert "No such option" in msg


def test_exit_2_with_whitespace_only_stdout_is_fatal(
    monkeypatch, tmp_target, tmp_config
):
    """A stdout of only whitespace is just as empty as b'' for our
    purposes. Same branch should fire.
    """
    fake = _FakeCompletedProcess(
        returncode=2,
        stdout=b"   \n  \t\n",
        stderr=b"Error: bad option value\n",
    )
    runner = _runner_with_stub(monkeypatch, fake)
    with pytest.raises(OpenGrepError):
        runner.scan(tmp_target, config=tmp_config)


def test_exit_2_with_rule_parse_errors_is_recoverable(
    monkeypatch, tmp_target, tmp_config
):
    """The original exit-2 contract: valid rules ran, some rules failed
    to parse, results are on stdout. The runner should return the
    parsed result and log a warning.
    """
    payload = (
        b'{"version":"1.20.0",'
        b'"results":[{"check_id":"rule-x","path":"sample.py",'
        b'"start":{"line":1,"col":1},"end":{"line":1,"col":5},'
        b'"extra":{"message":"m","severity":"WARNING","lines":"x = 1"}}],'
        b'"errors":[{"type":"Rule parse error","level":"warn","message":"bad rule"}],'
        b'"paths":{"scanned":["sample.py"]}}'
    )
    fake = _FakeCompletedProcess(
        returncode=2,
        stdout=payload,
        stderr=b"warning: rule X did not parse\n",
    )
    runner = _runner_with_stub(monkeypatch, fake)
    result = runner.scan(tmp_target, config=tmp_config)
    assert isinstance(result, OpenGrepResult)
    assert result.exit_code == 2
    assert len(result.raw_results) == 1
    assert len(result.raw_errors) == 1
    assert result.raw_errors[0]["type"] == "Rule parse error"


def test_exit_2_with_unparseable_stdout_is_fatal(
    monkeypatch, tmp_target, tmp_config
):
    """Exit 2 with non-empty but non-JSON stdout should also raise,
    not silently produce a zero-finding result.
    """
    fake = _FakeCompletedProcess(
        returncode=2,
        stdout=b"oh no this is not json at all\n",
        stderr=b"some stderr context here\n",
    )
    runner = _runner_with_stub(monkeypatch, fake)
    with pytest.raises(OpenGrepError) as excinfo:
        runner.scan(tmp_target, config=tmp_config)
    msg = str(excinfo.value)
    assert "could not parse" in msg
    assert "stderr" in msg  # stderr is now propagated for diagnosis


def test_exit_0_clean_no_matches(monkeypatch, tmp_target, tmp_config):
    """Sanity: the happy clean-no-matches path still works."""
    fake = _FakeCompletedProcess(
        returncode=0,
        stdout=b'{"version":"1.20.0","results":[],"errors":[],'
               b'"paths":{"scanned":["sample.py"]}}',
        stderr=b"",
    )
    runner = _runner_with_stub(monkeypatch, fake)
    result = runner.scan(tmp_target, config=tmp_config)
    assert result.exit_code == 0
    assert result.raw_results == ()
    assert result.paths_scanned == ("sample.py",)


def test_exit_1_clean_with_matches(monkeypatch, tmp_target, tmp_config):
    """Sanity: exit 1 (matches found) is recoverable."""
    fake = _FakeCompletedProcess(
        returncode=1,
        stdout=b'{"version":"1.20.0",'
               b'"results":[{"check_id":"rule-x","path":"sample.py",'
               b'"start":{"line":1,"col":1},"end":{"line":1,"col":5},'
               b'"extra":{"message":"m","severity":"WARNING","lines":"x = 1"}}],'
               b'"errors":[],'
               b'"paths":{"scanned":["sample.py"]}}',
        stderr=b"",
    )
    runner = _runner_with_stub(monkeypatch, fake)
    result = runner.scan(tmp_target, config=tmp_config)
    assert result.exit_code == 1
    assert len(result.raw_results) == 1


def test_exit_4_engine_failure_is_fatal(monkeypatch, tmp_target, tmp_config):
    """Sanity: exit codes outside {0, 1, 2} stay fatal."""
    fake = _FakeCompletedProcess(
        returncode=4,
        stdout=b"",
        stderr=b"Error: internal panic\n",
    )
    runner = _runner_with_stub(monkeypatch, fake)
    with pytest.raises(OpenGrepError) as excinfo:
        runner.scan(tmp_target, config=tmp_config)
    assert "internal panic" in str(excinfo.value)
