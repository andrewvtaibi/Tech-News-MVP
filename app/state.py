# app/state.py — simple persistent store for seen UIDs (atomic writes, TTL support)
from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
from typing import Dict, Iterable, Tuple, Optional

ISO_DAY = "%Y-%m-%d"

def _utc_today_str() -> str:
    return datetime.now(timezone.utc).strftime(ISO_DAY)

class SeenStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: Dict[str, str] = {}  # uid -> first_seen "YYYY-MM-DD"

    def load(self) -> None:
        if not self.path.exists():
            self.data = {}
            return
        try:
            obj = json.loads(self.path.read_text(encoding="utf-8"))
            self.data = dict(obj.get("uids", {})) if isinstance(obj, dict) else {}
        except Exception:
            # Corrupt store; start fresh
            self.data = {}

    def reset(self) -> None:
        self.data = {}

    def prune(self, ttl_days: int) -> int:
        """Remove entries older than ttl_days. Returns count removed."""
        if ttl_days <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
        removed = 0
        keep: Dict[str, str] = {}
        for uid, day_str in self.data.items():
            try:
                dt = datetime.strptime(day_str, ISO_DAY).replace(tzinfo=timezone.utc)
            except Exception:
                # drop unparsable entries
                removed += 1
                continue
            if dt >= cutoff:
                keep[uid] = day_str
            else:
                removed += 1
        self.data = keep
        return removed

    def is_seen(self, uid: str) -> bool:
        return uid in self.data

    def add(self, uids: Iterable[str]) -> int:
        """Add UIDs with today's date; returns how many were newly added."""
        today = _utc_today_str()
        added = 0
        for uid in uids:
            if uid and uid not in self.data:
                self.data[uid] = today
                added += 1
        return added

    def save(self) -> Path:
        """Atomic write. If locked, write a timestamped fallback."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"uids": self.data}
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
            return self.path
        except PermissionError:
            alt = self.path.with_name(self.path.stem + "-" + _utc_today_str() + self.path.suffix)
            alt.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return alt
