from __future__ import annotations

import json

from dsc.scanner.models import ScanResult


def format_json(result: ScanResult, *, json_lines: bool = False) -> str:
    if not json_lines:
        return result.to_json(indent=2) + "\n"

    # Stream-friendly: one finding per line (plus a final summary line).
    lines: list[str] = []
    for f in result.findings:
        lines.append(json.dumps(f.to_dict(), sort_keys=True))
    lines.append(json.dumps({"summary": result.to_dict() | {"findings": None}}, sort_keys=True))
    return "\n".join(lines) + "\n"

