"""
Skill Extension Loader.

Reads user-defined pattern extensions from:
  ~/.bsp-diagnostics/skill_extensions.json

The path can be overridden for testing via the BSP_EXTENSIONS_PATH
environment variable.

Extension file schema:
  {
    "version": 1,
    "skills": {
      "<skill_name>": {
        "patterns": [
          {
            "match": "<regex string>",
            "category": "<skill-specific category>",
            "description": "<human-readable description>"
          }
        ]
      }
    }
  }
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path


def _extensions_path() -> Path:
    """Return the active extension file path (env override or default)."""
    override = os.environ.get("BSP_EXTENSIONS_PATH")
    if override:
        return Path(override)
    return Path.home() / ".bsp-diagnostics" / "skill_extensions.json"


def get_extension_patterns(skill_name: str) -> list[dict]:
    """
    Return user-defined patterns for *skill_name*.

    Returns an empty list if the extension file does not exist, cannot be
    parsed, or contains no patterns for the requested skill.  Never raises.
    """
    path = _extensions_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("skills", {}).get(skill_name, {}).get("patterns", [])
    except Exception:
        return []


def write_extension_pattern(skill_name: str, pattern: dict) -> str:
    """
    Append *pattern* to the extension file under *skill_name*.

    Creates the file and parent directories if they do not exist.
    Returns the absolute path of the extension file.
    """
    path = _extensions_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {"version": 1, "skills": {}}
    else:
        data = {"version": 1, "skills": {}}

    if skill_name not in data.setdefault("skills", {}):
        data["skills"][skill_name] = {"patterns": []}

    pattern_entry = {**pattern, "added": str(date.today())}
    data["skills"][skill_name]["patterns"].append(pattern_entry)

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)
