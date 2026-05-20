"""OpenGrep subprocess runner.

Invokes the bundled OpenGrep binary against a target path with a given
rulepack and returns the parsed JSON results. We use OpenGrep's native
JSON output (``--json``) rather than SARIF because metavar contents
ride directly on each result, which the post-processor pipeline needs.
The SARIF formatter emits its output from the unified Finding stream.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


def _default_timeout_seconds() -> float:
    """Whole-scan timeout, env-overridable via DSC_OPENGREP_TIMEOUT_SECONDS."""
    raw = os.environ.get("DSC_OPENGREP_TIMEOUT_SECONDS")
    if raw:
        try:
            value = float(raw)
            if value > 0:
                return value
        except ValueError:
            pass
    return 600.0


_DEFAULT_TIMEOUT_SECONDS = _default_timeout_seconds()  # whole-scan; per-file is OpenGrep's job

logger = logging.getLogger(__name__)


class OpenGrepError(RuntimeError):
    """Raised when OpenGrep fails or its output cannot be parsed."""


@dataclass(frozen=True, slots=True)
class OpenGrepResult:
    raw_results: tuple[dict[str, Any], ...]
    raw_errors: tuple[dict[str, Any], ...]
    paths_scanned: tuple[str, ...]
    duration_seconds: float
    exit_code: int
    command: tuple[str, ...] = field(default_factory=tuple)
    # Populated when --time was requested; raw payload from OpenGrep
    # under the top-level "time" key. Shape:
    #   {"profiling_times": {"config_time", "core_time", ...},
    #    "rules": [<rule_id>, ...],
    #    "targets": [{"path", "num_bytes", "parse_time", "run_time",
    #                 "match_times": [<float per rule>]}, ...],
    #    "total_bytes", "max_memory_bytes", "rules_parse_time"}
    timing: dict[str, Any] | None = None


class OpenGrepRunner:
    """Wraps a subprocess invocation of opengrep scan."""

    def __init__(
        self,
        *,
        binary: Path | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.binary = self._resolve_binary(binary)
        # Resolve the timeout LAZILY so DSC_OPENGREP_TIMEOUT_SECONDS
        # set after import (e.g., via .env loaded in main()) still
        # takes effect.
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _default_timeout_seconds()
        )

    @staticmethod
    def _resolve_binary(binary: Path | None) -> Path:
        if binary is not None:
            p = Path(binary)
            if not p.exists():
                raise OpenGrepError(f"opengrep binary not found at {p}")
            return p

        # Two env var names are supported; DSC_OPENGREP_BIN is the preferred
        # form. DSC_OPENGREP_BINARY is kept as a deprecated alias.
        env_value = os.environ.get("DSC_OPENGREP_BIN") or os.environ.get(
            "DSC_OPENGREP_BINARY"
        )
        if env_value:
            p = Path(env_value)
            if not p.exists():
                raise OpenGrepError(
                    f"$DSC_OPENGREP_BIN/$DSC_OPENGREP_BINARY={env_value!r} "
                    "but file does not exist"
                )
            return p

        # Vendored binary at engine/vendor/opengrep/bin/opengrep
        repo_marker = Path(__file__).resolve()
        bin_name = "opengrep.exe" if os.name == "nt" else "opengrep"
        for parent in repo_marker.parents:
            cand = parent / "vendor" / "opengrep" / "bin" / bin_name
            if cand.exists():
                return cand
            if (parent / "pyproject.toml").exists():
                # We've reached the scanner package root without finding it.
                break

        which = shutil.which("opengrep")
        if which:
            return Path(which)

        raise OpenGrepError(
            "opengrep binary not found. Set $DSC_OPENGREP_BIN, place the "
            "binary at vendor/opengrep/bin/opengrep, or add it to PATH."
        )

    def scan(
        self,
        target: Path | Iterable[Path],
        *,
        config: Path,
        excludes: Iterable[str] = (),
        languages: Iterable[str] = (),
        no_git_ignore: bool = True,
        jobs: int | None = None,
        record_timing: bool | None = None,
    ) -> OpenGrepResult:
        # Accept either a single Path (directory or file) or an iterable
        # of paths. OpenGrep takes any number of positional targets, so
        # passing a list of just-the-dirty-files lets the engine cache
        # actually scope the per-scan work (rather than re-running
        # OpenGrep on the whole directory and discarding cached files'
        # results post hoc).
        if isinstance(target, (str, Path)):
            targets: list[Path] = [Path(target)]
        else:
            targets = [Path(t) for t in target]
            if not targets:
                raise OpenGrepError("scan target list is empty")

        for t in targets:
            if not t.exists():
                raise OpenGrepError(f"scan target does not exist: {t}")
        config = Path(config)
        if not config.exists():
            raise OpenGrepError(f"rulepack config does not exist: {config}")

        cmd: list[str] = [
            str(self.binary),
            "scan",
            "--config",
            str(config),
            "--json",
            "--quiet",
            "--disable-version-check",
        ]
        if no_git_ignore:
            cmd.append("--no-git-ignore")
        if jobs is not None and jobs > 0:
            cmd.extend(["--jobs", str(jobs)])
        # --time adds a "time" key to the JSON output with per-rule and
        # per-target timings. Defaults off (the data is hefty); benchmarks
        # opt in via DSC_OPENGREP_RECORD_TIMING=1 or by passing
        # record_timing=True.
        if record_timing is None:
            record_timing = os.environ.get(
                "DSC_OPENGREP_RECORD_TIMING", ""
            ).strip().lower() in ("1", "true", "yes", "on")
        if record_timing:
            cmd.append("--time")
        for pat in excludes:
            cmd.extend(["--exclude", pat])
        for lang in languages:
            # OpenGrep accepts --lang once per language; it filters which
            # rules to run rather than which files to read.
            cmd.extend(["--lang", lang])
        for t in targets:
            cmd.append(str(t))

        import time

        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=False,
                check=False,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenGrepError(
                f"opengrep timed out after {self.timeout_seconds}s"
            ) from exc
        elapsed = time.perf_counter() - t0

        # Exit-code semantics:
        #   0  = clean run, no matches
        #   1  = clean run with matches
        #   2  = recoverable failure -- some rules failed to parse, but
        #        valid rules still ran AND results were emitted on stdout
        #   2  = ALSO returned for CLI-flag rejection (unknown option,
        #        bad value, etc). In that case stdout is empty, stderr
        #        carries the parser error, and there is nothing to
        #        recover. Distinguish by checking that stdout actually
        #        parses to a JSON object before we trust exit 2 as
        #        recoverable.
        #   >=4 = real engine failure (config invalid, internal panic, etc.)
        if proc.returncode not in (0, 1, 2):
            stderr = proc.stderr.decode("utf-8", errors="replace")
            raise OpenGrepError(
                f"opengrep exited {proc.returncode}: "
                f"{stderr[:1000].strip()}"
            )

        # Empty stdout is never a valid JSON scan result. Surface it loudly
        # instead of silently treating an OpenGrep startup failure as a clean
        # zero-finding run.
        if not (proc.stdout or b"").strip():
            stderr = proc.stderr.decode("utf-8", errors="replace")
            raise OpenGrepError(
                f"opengrep exited {proc.returncode} with empty stdout (CLI rejected or "
                f"engine failed before emitting JSON): {stderr[:1000].strip()}"
            )

        try:
            payload = json.loads(proc.stdout or b"{}")
        except json.JSONDecodeError as exc:
            head = proc.stdout[:500].decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")
            # Unparseable stdout on any exit code is fatal -- there's
            # nothing to recover. Include stderr so the caller can see
            # why opengrep died.
            raise OpenGrepError(
                f"could not parse opengrep JSON output: {exc}. "
                f"first 500 bytes: {head!r}. "
                f"stderr: {stderr[:500].strip()!r}"
            ) from exc

        if proc.returncode == 2:
            # Recoverable exit 2 -- valid rules ran, results came back,
            # but some rules failed to parse. Log a warning so it's
            # visible without aborting the scan.
            stderr = proc.stderr.decode("utf-8", errors="replace")
            broken = [
                e.get("type") for e in (payload.get("errors") or [])
                if e.get("type") == "Rule parse error"
            ]
            if broken:
                logger.warning(
                    "opengrep emitted exit 2 with %d rule-parse errors; "
                    "continuing with the rules that did parse "
                    "(stderr head: %r)",
                    len(broken),
                    stderr[:300].strip(),
                )

        timing = payload.get("time") if record_timing else None
        return OpenGrepResult(
            raw_results=tuple(payload.get("results") or ()),
            raw_errors=tuple(payload.get("errors") or ()),
            paths_scanned=tuple(payload.get("paths", {}).get("scanned") or ()),
            duration_seconds=elapsed,
            exit_code=proc.returncode,
            command=tuple(cmd),
            timing=timing if isinstance(timing, dict) else None,
        )
