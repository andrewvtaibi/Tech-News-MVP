# app/fetch.py — resilient fetch + parsing
# Version: v2.2.2 (2025-10-03)
# Goals: never crash; swallow HTTP/parse hiccups; robust date parsing; strict signatures.

from __future__ import annotations

import ssl, urllib.request, urllib.error, time, re, html, random
from typing import Tuple, List, Dict, Any
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import feedparser

from urllib.error import HTTPError, URLError

# ---------- HTTP ----------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.8",
    "Connection": "close",
}

def _mk_request(url: str) -> urllib.request.Request:
    req = urllib.request.Request(url)
    for k, v in _DEFAULT_HEADERS.items():
        req.add_header(k, v)
    return req

def _mk_context(url: str, insecure_hosts: set[str] | None) -> ssl.SSLContext | None:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        host = ""
    insecure = bool(insecure_hosts and host in insecure_hosts)
    if not url.lower().startswith("https"):
        return None
    if not insecure:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def fetch_bytes(
    url: str,
    timeout_sec: int = 15,
    max_retries: int = 3,
    backoff_base: float = 1.0,
    backoff_cap: float = 8.0,
    insecure_hosts: set[str] | None = None,
) -> bytes:
    """
    Fetch URL with retries/backoff. Never raises to caller; returns b"" on failure.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            req = _mk_request(url)
            ctx = _mk_context(url, insecure_hosts)

            # Use HTTPS handler with context only for HTTPS; plain HTTP gets default opener.
            if url.lower().startswith("https") and ctx is not None:
                opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
                resp = opener.open(req, timeout=timeout_sec)
            else:
                resp = urllib.request.urlopen(req, timeout=timeout_sec)

            try:
                data = resp.read() or b""
            finally:
                # Ensure socket is closed even if read() raised
                try:
                    resp.close()
                except Exception:
                    pass
            return data

        except HTTPError as e:
            # Treat common client errors as terminal (don't retry).
            if e.code in (400, 401, 403, 404, 410):
                return b""
            # Server-side or transient: fall through to retry.
        except URLError:
            # Network/transient error -> retry below
            pass
        except Exception:
            # Any other transient error -> retry below
            pass

        if attempt >= max_retries:
            return b""

        # Jittered exponential backoff
        import random, time as _time
        sleep_s = min(
            backoff_cap,
            (backoff_base * (2 ** (attempt - 1))) * (0.75 + 0.5 * random.random()),
        )
        _time.sleep(sleep_s)


# ---------- Normalize ----------

def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<\s*br\s*/?\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

_MONTHS = {
    "jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
    "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12
}
_NEWSROOM_PAT = re.compile(
    r'^(?P<mon>[A-Za-z]{3})\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})'
    r'(?:\s+(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>[AaPp][Mm])?)?$'
)

def _parse_newsroom_date(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    m = _NEWSROOM_PAT.match(s)
    if not m:
        return None
    mm = _MONTHS.get(m.group('mon').lower())
    if not mm:
        return None
    day  = int(m.group('day'))
    year = int(m.group('year'))
    hh   = int(m.group('h')) if m.group('h') else 0
    mn   = int(m.group('m')) if m.group('m') else 0
    ap   = (m.group('ampm') or "").lower()
    if ap == "pm" and hh != 12: hh += 12
    if ap == "am" and hh == 12: hh = 0
    try:
        return datetime(year, mm, day, hh, mn, tzinfo=timezone.utc)
    except ValueError:
        return None

def _to_iso_utc(dt: datetime | None) -> str | None:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def _pick_published_iso(entry: dict) -> str | None:
    """
    Best-effort published time. NEVER raises. Returns ISO-UTC or None.
    Priority: struct_time -> RFC -> newsroom formats.
    """
    # 1) feedparser struct_time
    for k in ("published_parsed", "updated_parsed"):
        st = entry.get(k)
        if st:
            try:
                dt = datetime(st.tm_year, st.tm_mon, st.tm_mday, st.tm_hour, st.tm_min, st.tm_sec, tzinfo=timezone.utc)
                iso = _to_iso_utc(dt)
                if iso: return iso
            except Exception:
                pass

    # 2) strings
    s = (entry.get("published") or entry.get("updated") or "").strip()
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        iso = _to_iso_utc(dt)
        if iso: return iso
    except Exception:
        pass
    iso2 = _to_iso_utc(_parse_newsroom_date(s))
    return iso2  # may be None

def _choose_uid(entry: dict) -> str | None:
    for k in ("id", "guid", "link", "title"):
        v = entry.get(k)
        if v:
            return str(v)
    return None

def _choose_title(entry: dict) -> str:
    for k in ("title", "summary", "description"):
        v = entry.get(k)
        if v:
            return _strip_html(str(v))[:400]
    return "(untitled)"

def _choose_summary(entry: dict) -> str:
    for k in ("summary", "description"):
        v = entry.get(k)
        if v:
            return _strip_html(str(v))[:1200]
    v = entry.get("title")
    return _strip_html(str(v))[:1200] if v else ""

def parse_and_normalize(raw: bytes) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Parse feed bytes into normalized items.
    NEVER raises; returns empty list on failure.
    """
    try:
        if not raw:
            return {"source": "Unknown Feed"}, []
        parsed = feedparser.parse(raw)
    except Exception:
        return {"source": "Unknown Feed"}, []

    try:
        feed_title = ((parsed.get("feed") or {}).get("title") or "").strip()
    except Exception:
        feed_title = ""
    source = {"source": feed_title or "Unknown Feed"}

    out: List[Dict[str, Any]] = []
    entries = parsed.get("entries") or []
    for e in entries:
        try:
            title = _choose_title(e)
            link = (e.get("link") or "").strip()
            summary = _choose_summary(e)
            published_iso = _pick_published_iso(e)  # may be None
            uid = _choose_uid(e)

            item = {
                "title": title,
                "link": link,
                "summary": summary,
                "published_iso": published_iso,
                "uid": uid,
            }
            out.append(item)
        except Exception:
            continue

    return source, out
