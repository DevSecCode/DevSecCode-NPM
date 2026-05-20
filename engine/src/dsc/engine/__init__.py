"""Scanner engine module.

The engine module replaces the bespoke detector layer described in
scanner-rearchitecture-spec.md. Public surface:

- ``OpenGrepRunner``: subprocess invocation of OpenGrep
- ``ResultMapper``: SARIF/JSON -> Finding, with post-processors inline
- ``RulepackLoader``: discover + validate rule YAML
- ``RealtimeMatcher``: in-process fast-path for inline UX
- ``run_scan``: end-to-end convenience wrapper used by scanner/engine.py
"""

from __future__ import annotations

from .opengrep_runner import OpenGrepError, OpenGrepRunner, OpenGrepResult
from .realtime_matcher import RealtimeMatcher
from .result_mapper import ResultMapper
from .rulepack_loader import (
    LoadedRule,
    LoadedRulepack,
    RulepackLoader,
    RulepackValidationError,
)
from .schema import RuleSchemaError, validate_rule_dict

__all__ = [
    "LoadedRule",
    "LoadedRulepack",
    "OpenGrepError",
    "OpenGrepResult",
    "OpenGrepRunner",
    "RealtimeMatcher",
    "ResultMapper",
    "RulepackLoader",
    "RulepackValidationError",
    "RuleSchemaError",
    "validate_rule_dict",
]
