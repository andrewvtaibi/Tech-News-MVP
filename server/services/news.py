# server/services/news.py
# Fetches and filters company-specific headlines and press releases via RSS.
#
# Inputs:  company name string, days (7 or 30)
# Outputs: list[NewsItem] — validated, filtered, deduplicated
# Assumptions:
#   - Google News RSS is the primary source for headlines.
#   - PR Newswire / GlobeNewswire / BusinessWire for press releases.
#   - app/fetch.py (fetch_bytes, parse_and_normalize) handles HTTP + parsing.
#   - All filtering is post-fetch; no pre-fetch scoping beyond the query URL.
#
# Failure modes:
#   - Network errors: return [] (never raise to caller)
#   - Malformed RSS: feedparser handles gracefully, empty list returned
#   - Items outside date window: excluded silently

from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Optional

from server.models.schemas import NewsItem

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RESULTS_PER_QUERY = 50

# Patterns that identify SEC filings or EDGAR content
_SEC_PATTERNS = re.compile(
    r"\b(8-K|10-K|10-Q|EDGAR|SEC\s+filing|Form\s+8|Form\s+10|"
    r"proxy\s+statement|DEF\s+14A|S-1\s+filing|prospectus)\b",
    re.IGNORECASE,
)
_SEC_DOMAINS = {"sec.gov", "edgar.sec.gov"}

# arXiv domain
_ARXIV_DOMAIN = "arxiv.org"

# Words excluded when building the relevance-filter token set.
_STOPWORDS = {
    "inc", "corp", "ltd", "llc", "co", "the", "and", "&", "of",
    "a", "an", "for", "in", "on", "at", "by",
}

# PR wire domains used for per-site Google News queries.
_PR_WIRE_DOMAINS = [
    "prnewswire.com",
    "businesswire.com",
    "globenewswire.com",
]

_GNEWS_BASE = (
    "https://news.google.com/rss/search"
    "?hl=en-US&gl=US&ceid=US%3Aen&q="
)


def _pr_wire_urls(company: str) -> list[str]:
    """
    Build one Google News RSS query per PR wire domain.
    Quoting the company name forces an exact-phrase match;
    a single site: operator per query is more reliably honoured
    than a combined OR expression.
    """
    urls = []
    for domain in _PR_WIRE_DOMAINS:
        q = urllib.parse.quote_plus(f'"{company}" site:{domain}')
        urls.append(_GNEWS_BASE + q)
    return urls


def _relevant_tokens(company: str) -> list[str]:
    """
    Return the significant lowercase words from *company* that an
    article title must contain at least one of to be considered relevant.
    """
    return [
        w for w in company.lower().split()
        if w not in _STOPWORDS and len(w) > 1
    ]


def _is_relevant(item: dict, tokens: list[str]) -> bool:
    """
    Return True if the item title contains at least one token from
    the company name.  Keeps the filter permissive enough that
    ticker-symbol-only mentions are not accidentally dropped.
    """
    if not tokens:
        return True
    title = (item.get("title") or "").lower()
    return any(tok in title for tok in tokens)


# ---------------------------------------------------------------------------
# Internal HTTP helper (thin wrapper so tests can patch a single symbol)
# ---------------------------------------------------------------------------

def _fetch_raw(url: str) -> bytes:
    """
    Fetch *url* and return raw bytes.
    Delegates entirely to app.fetch.fetch_bytes.
    Never raises; returns b"" on any failure.
    """
    try:
        from app.fetch import fetch_bytes
        return fetch_bytes(url, timeout_sec=15, max_retries=2)
    except Exception:
        return b""


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def _headlines_url(company: str) -> str:
    # Quote the company name so common-word names ("Apple", "Target",
    # "Block", "Visa", "Ford") don't return generic dictionary-sense
    # articles. For multi-word names the quotes also force exact phrase.
    q = urllib.parse.quote_plus(f'"{company}"')
    return (
        f"https://news.google.com/rss/search"
        f"?q={q}&hl=en-US&gl=US&ceid=US%3Aen"
    )


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------

def _parse_date(iso: Optional[str]) -> Optional[datetime]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _is_within_window(item: dict, cutoff: datetime) -> bool:
    dt = _parse_date(item.get("published_iso"))
    if dt is None:
        # Drop items with missing dates — they're more likely stale
        # than "very recent" and would pollute time-windowed views.
        return False
    return dt >= cutoff


def _is_sec_item(item: dict) -> bool:
    title = item.get("title", "")
    link = item.get("link", "")
    if _SEC_PATTERNS.search(title):
        return True
    try:
        from urllib.parse import urlparse
        domain = urlparse(link).hostname or ""
        return domain in _SEC_DOMAINS
    except Exception:
        return False


def _is_arxiv_item(item: dict) -> bool:
    link = item.get("link", "")
    try:
        from urllib.parse import urlparse
        domain = (urlparse(link).hostname or "").lower()
        return _ARXIV_DOMAIN in domain
    except Exception:
        return False


def _to_news_item(item: dict) -> Optional[NewsItem]:
    """
    Convert a normalized feed dict to a NewsItem.
    Returns None if mandatory fields are missing.
    """
    title = (item.get("title") or "").strip()
    link = (item.get("link") or "").strip()
    if not title or not link:
        return None
    source = (item.get("source") or "").strip() or _domain_from(link)
    summary = (item.get("summary") or "")[:300].strip() or None
    return NewsItem(
        title=title,
        link=link,
        source=source,
        published_date=item.get("published_iso"),
        summary_snippet=summary,
    )


def _domain_from(link: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(link).hostname or ""
    except Exception:
        return ""


def _deduplicate(items: list[dict]) -> list[dict]:
    seen_titles: set[str] = set()
    seen_links: set[str] = set()
    out: list[dict] = []
    for it in items:
        t = (it.get("title") or "").lower().strip()
        l = (it.get("link") or "").lower().strip()
        if t in seen_titles or l in seen_links:
            continue
        if t:
            seen_titles.add(t)
        if l:
            seen_links.add(l)
        out.append(it)
    return out


def _filter_and_convert(
    raw_items: list[dict],
    cutoff: datetime,
    *,
    relevance_tokens: list[str] | None = None,
) -> list[NewsItem]:
    """
    Apply date window, SEC/arXiv exclusion, optional company-relevance
    check, deduplication, and conversion to NewsItem.
    """
    tokens = relevance_tokens or []
    filtered = [
        it for it in raw_items
        if _is_within_window(it, cutoff)
        and not _is_sec_item(it)
        and not _is_arxiv_item(it)
        and _is_relevant(it, tokens)
    ]

    filtered = _deduplicate(filtered)[:MAX_RESULTS_PER_QUERY]

    news_items: list[NewsItem] = []
    for it in filtered:
        ni = _to_news_item(it)
        if ni:
            news_items.append(ni)

    return news_items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class NewsService:
    """
    Fetches company-specific news from RSS feeds.
    All methods are synchronous; they are run in a thread executor
    from the async route handlers.
    """

    def fetch_headlines(self, company: str, days: int) -> list[NewsItem]:
        """
        Fetch recent headlines mentioning *company* from Google News RSS.
        Returns [] on any failure.
        """
        try:
            url = _headlines_url(company)
            raw = _fetch_raw(url)
            if not raw:
                return []
            from app.fetch import parse_and_normalize
            _meta, items = parse_and_normalize(raw)
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            tokens = _relevant_tokens(company)
            return _filter_and_convert(items, cutoff, relevance_tokens=tokens)
        except Exception:
            return []

    def fetch_press_releases(self, company: str, days: int) -> list[NewsItem]:
        """
        Fetch recent press releases for *company* from PR Newswire,
        Business Wire, and GlobeNewswire via targeted Google News RSS
        queries (one per domain, company name quoted for exact match).
        Results from all three are merged, deduplicated, date-filtered,
        and checked for company-name relevance.
        Returns [] if all sources fail.
        """
        try:
            from app.fetch import parse_and_normalize
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            tokens = _relevant_tokens(company)
            all_raw: list[dict] = []

            for url in _pr_wire_urls(company):
                raw = _fetch_raw(url)
                if not raw:
                    continue
                _meta, items = parse_and_normalize(raw)
                all_raw.extend(items)

            return _filter_and_convert(
                all_raw, cutoff, relevance_tokens=tokens
            )
        except Exception:
            return []
