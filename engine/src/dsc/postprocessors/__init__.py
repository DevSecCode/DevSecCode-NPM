"""Post-processor base types for the scanner.

The public CLI doesn't register any postprocessors — the gamified
scan path passes an empty `known_post_processors` tuple to ScanEngine,
which means rules cannot reference dynamic transforms. Findings come
out of the SARIF mapper exactly as the rule defines them.
"""

from __future__ import annotations

from .base import (
    PostProcessor,
    PostProcessorRegistry,
    SarifMatch,
    ScanContext,
)

__all__ = [
    "PostProcessor",
    "PostProcessorRegistry",
    "SarifMatch",
    "ScanContext",
]
