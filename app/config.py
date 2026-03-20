# app/config.py
# Centralized config/feeds loading with clear errors and portable path resolution.

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def app_root() -> Path:
    """Return app root directory for dev and PyInstaller."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[1]


def _read_json_file(p: Path) -> Any:
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to read {p}: {e}") from e
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        loc = f"{p} (line {e.lineno}, col {e.colno})"
        raise ValueError(f"Invalid JSON in {loc}: {e.msg}") from e
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON in {p}: {e}") from e


def load_settings(name: str = "settings.json") -> Dict[str, Any]:
    p = app_root() / name
    data = _read_json_file(p)
    if not isinstance(data, dict):
        raise TypeError(f"{p} must contain a JSON object (got {type(data).__name__})")
    return data


def load_feeds(name: str = "feeds.json") -> List[Dict[str, Any]]:
    p = app_root() / name
    data = _read_json_file(p)
    if not isinstance(data, list):
        raise TypeError(f"{p} must contain a JSON array (got {type(data).__name__})")
    for i, f in enumerate(data):
        if not isinstance(f, dict):
            raise TypeError(f"{p}[{i}] must be an object (got {type(f).__name__})")
        if "url" not in f or "tag" not in f:
            raise ValueError(f"{p}[{i}] must include 'url' and 'tag' fields")
    return data


def try_load_feeds(name: str) -> List[Dict[str, Any]]:
    p = app_root() / name
    if not p.exists():
        return []
    return load_feeds(name)
