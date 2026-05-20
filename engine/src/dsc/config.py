from __future__ import annotations

import ast
import json
from importlib import resources
from pathlib import Path
from typing import Any

from dsc.scanner.models import Severity
from dsc.scanner.parser import find_git_root


class ConfigError(RuntimeError):
    pass


DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "scan": {
        "paths": ["."],
        "ignore": [],
        "languages": [
            "python",
            "javascript",
            "typescript",
            "go",
            "java",
            "ruby",
            "rust",
            "json",
            "yaml",
            "toml",
            "ini",
            "xml",
            "html",
            "dockerfile",
            "dockercompose",
            "terraform",
            "requirements",
            "lockfile",
            "gomod",
            "gradle",
            "runtime",
            "swift",
            "objc",
            "plist",
            "kotlin",
            "php",
            "csharp",
            "dart",
            "c",
            "cpp",
        ],
    },
    "detectors": {
        "enabled": "all",
        "disabled": [],
        "severity_override": {},
    },
    "compliance": [],
    "fail_on": "high",
    "quality": {
        "profile": "balanced",
    },
    "suppressions": {},
}


def find_config_file(start: Path, filename: str = ".dsc.yml") -> Path | None:
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent

    git_root = find_git_root(cur)
    stop = git_root if git_root is not None else cur.anchor

    for parent in [cur, *cur.parents]:
        candidate = parent / filename
        if candidate.exists():
            return candidate
        if git_root is not None and parent == git_root:
            break
        if git_root is None and str(parent) == str(stop):
            break
    return None


def _parse_scalar(value: str) -> Any:
    v = value.strip()
    if v == "":
        return ""
    lowered = v.lower()
    if lowered in {"null", "none"}:
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if v.isdigit():
        return int(v)
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    if v.startswith("[") and v.endswith("]"):
        try:
            return json.loads(v)
        except Exception:
            try:
                return ast.literal_eval(v)
            except Exception:
                return v
    if v.startswith("{") and v.endswith("}"):
        try:
            return json.loads(v)
        except Exception:
            try:
                return ast.literal_eval(v)
            except Exception:
                return v
    return v


def parse_config(text: str) -> dict[str, Any]:
    # First, accept JSON (valid YAML) for strict, dependency-free configs.
    try:
        json_candidate = "\n".join(
            line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
        )
        data = json.loads(json_candidate)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Minimal YAML subset parser (enough for the schema this project writes).
    root: dict[str, Any] = {}
    stack: list[dict[str, Any]] = [
        {"indent": 0, "container": root, "parent": None, "parent_key": None}
    ]

    def current_frame() -> dict[str, Any]:
        return stack[-1]

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()

        while len(stack) > 1 and indent < int(current_frame()["indent"]):
            stack.pop()

        frame = current_frame()
        container = frame["container"]

        if line.startswith("- "):
            item = _parse_scalar(line[2:])
            if not isinstance(container, list):
                # Convert an empty dict created for a pending key into a list.
                parent = frame.get("parent")
                parent_key = frame.get("parent_key")
                if (
                    isinstance(container, dict)
                    and not container
                    and isinstance(parent, dict)
                    and isinstance(parent_key, str)
                ):
                    new_list: list[Any] = []
                    parent[parent_key] = new_list
                    frame["container"] = new_list
                    container = new_list
                else:
                    raise ConfigError("Invalid YAML structure: list item without list context")
            container.append(item)
            continue

        if ":" not in line:
            raise ConfigError(f"Invalid YAML line (missing ':'): {raw!r}")

        key, rest = line.split(":", 1)
        key = key.strip()
        value_part = rest.strip()

        if not isinstance(container, dict):
            raise ConfigError("Invalid YAML structure: mapping inside list is not supported")

        if value_part == "":
            container[key] = {}
            stack.append(
                {
                    "indent": indent + 1,
                    "container": container[key],
                    "parent": container,
                    "parent_key": key,
                }
            )
            continue

        container[key] = _parse_scalar(value_part)

    if not isinstance(root, dict):
        raise ConfigError("Config root must be a mapping")
    return root


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(start: Path) -> tuple[dict[str, Any], Path | None]:
    cfg_path = find_config_file(start)
    if cfg_path is None:
        return dict(DEFAULT_CONFIG), None
    try:
        raw = cfg_path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_config(raw)
    except Exception as exc:
        raise ConfigError(f"Failed to read config {cfg_path}: {exc}") from exc
    return deep_merge(DEFAULT_CONFIG, parsed), cfg_path


def load_preset(preset_name: str) -> dict[str, Any] | None:
    try:
        preset_file = resources.files("dsc.presets").joinpath(f"{preset_name}.yml")
        if not preset_file.is_file():
            return None
        raw = preset_file.read_text(encoding="utf-8")
        return parse_config(raw)
    except Exception:
        return None


def parse_severity(value: str | None, *, default: Severity) -> Severity:
    if not value:
        return default
    return Severity.from_str(value)


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]
