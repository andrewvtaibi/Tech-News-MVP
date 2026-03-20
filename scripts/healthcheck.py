# scripts/healthcheck.py
import sys
from pathlib import Path

# Ensure project root is on sys.path even if run from scripts/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print("Import sanity…")
from app import config as cfg  # now robust

assert hasattr(cfg, "load_feeds"), "load_feeds missing in app.config"
assert hasattr(cfg, "load_settings"), "load_settings missing in app.config"
print("OK: app.config has load_feeds & load_settings")

s = cfg.load_settings(str(ROOT / "settings.json"))
print("OK: settings loaded. outputs=", s.get("outputs"))

feeds = cfg.load_feeds(str(ROOT / "feeds.json"))
print(f"OK: feeds loaded: {len(feeds)} feed(s)")
print("Healthcheck passed.")
