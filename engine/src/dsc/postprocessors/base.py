"""Post-processor protocol and supporting shapes.

Per scanner-rearchitecture-spec.md Section 4.4. A post-processor takes
a single SARIF match and returns 0..N Findings. Returning [] suppresses
the match (e.g., package is not actually vulnerable). Returning multiple
Findings is rare but supported (e.g., one matched library version
mapping to multiple CVE advisories).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from dsc.scanner.models import Finding


@dataclass(frozen=True, slots=True)
class SarifMatch:
    """A single OpenGrep match expressed in the shape a post-processor
    needs without dragging in the full SARIF tree.

    `metavars` maps OpenGrep pattern variables (e.g. ``$NAME``,
    ``$VERSION``) to their matched abstract content. The mapper extracts
    this from ``extra.metavars[$NAME].abstract_content`` in OpenGrep's
    JSON output.
    """

    rule_id: str
    file_path: str
    line_start: int
    line_end: int
    column: int
    message: str
    severity: str
    metavars: dict[str, str]
    raw_lines: str


@dataclass(frozen=True, slots=True)
class ScanContext:
    """Per-scan context passed to every post-processor invocation.

    Keep this small. Adding fields here grows the trusted surface a
    primitive can read; any addition is a deliberate decision."""

    workspace_root: str
    scanner_version: str
    rulepack_hash: str


@runtime_checkable
class PostProcessor(Protocol):
    name: str

    def process(
        self,
        match: SarifMatch,
        rule_metadata: dict[str, Any],
        args: dict[str, Any],
        context: ScanContext,
    ) -> list[Finding]:
        ...


class PostProcessorRegistry:
    """In-process registry. Rules referencing an unregistered processor
    fail validation at rulepack load time (rulepack_loader, not here)."""

    def __init__(self) -> None:
        self._processors: dict[str, PostProcessor] = {}

    def register(self, processor: PostProcessor) -> None:
        if processor.name in self._processors:
            raise ValueError(
                f"post-processor '{processor.name}' already registered"
            )
        self._processors[processor.name] = processor

    def get(self, name: str) -> PostProcessor:
        if name not in self._processors:
            raise KeyError(
                f"unknown post-processor '{name}'. known: "
                f"{sorted(self._processors)}"
            )
        return self._processors[name]

    def names(self) -> list[str]:
        return sorted(self._processors)
