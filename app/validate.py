# app/validate.py
from typing import Any, Dict, List

_REQUIRED_SETTINGS = [
    "outputs", "out_dir", "window_days", "allow_missing_timestamps",
    "only_new", "seen_ttl_days", "skip_write_when_empty"
]

def validate_settings(s: Dict[str, Any]) -> list[str]:
    errs: List[str] = []
    for k in _REQUIRED_SETTINGS:
        if k not in s:
            errs.append(f"settings.json missing '{k}'")
    if s.get("outputs") and not all(x in {"csv","json","html"} for x in s["outputs"]):
        errs.append("settings.outputs must be any of csv/json/html")
    if not isinstance(s.get("window_days", 0), int) or s["window_days"] < 0:
        errs.append("settings.window_days must be a non-negative integer")
    if not isinstance(s.get("seen_ttl_days", 0), int) or s["seen_ttl_days"] < 0:
        errs.append("settings.seen_ttl_days must be a non-negative integer")
    # optional numeric
    for k in ["max_total_items","per_source_max_count","fetch_workers","fetch_task_timeout_sec"]:
        if k in s and (not isinstance(s[k], int) or s[k] < 0):
            errs.append(f"settings.{k} must be a non-negative integer")
    for k in ["per_source_max_fraction"]:
        if k in s and not (isinstance(s[k], float) or isinstance(s[k], int)):
            errs.append(f"settings.{k} must be a number")
    return errs

def validate_feeds(feeds: List[Dict[str, Any]]) -> list[str]:
    errs: List[str] = []
    if not isinstance(feeds, list) or not feeds:
        return ["feeds.json must be a non-empty list"]
    for i, f in enumerate(feeds):
        if "url" not in f or "tag" not in f:
            errs.append(f"feeds[{i}] requires 'url' and 'tag'")
    return errs
