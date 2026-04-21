# tests/conftest.py
# Shared pytest fixtures for the Industry News webapp test suite.
# Inputs:  none (fixtures are injected by pytest)
# Outputs: test client, mock RSS bytes, mock ticker data

from __future__ import annotations

import io
import textwrap
from datetime import datetime, timedelta, timezone
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App import (deferred so individual service tests can import without a
# running FastAPI app)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Return the FastAPI application instance."""
    from server.main import create_app
    return create_app()


@pytest.fixture(scope="session")
def client(app) -> Generator[TestClient, None, None]:
    """Synchronous TestClient wrapping the FastAPI app."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Mock RSS feed data
# ---------------------------------------------------------------------------

def _make_rss(
    title: str,
    item_title: str,
    item_link: str,
    item_date: str,
    source: str,
) -> bytes:
    return textwrap.dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>{title}</title>
            <item>
              <title>{item_title}</title>
              <link>{item_link}</link>
              <pubDate>{item_date}</pubDate>
              <description>
                Test summary for {item_title}.
              </description>
            </item>
          </channel>
        </rss>
    """).encode("utf-8")


def _recent_rfc2822(days_ago: int = 1) -> str:
    """Return an RFC-2822 date string for N days ago (UTC)."""
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")


@pytest.fixture
def mock_rss_headlines() -> bytes:
    """Valid RSS feed bytes for a recent Pfizer headline."""
    return _make_rss(
        title="Google News - Pfizer",
        item_title="Pfizer reports positive Phase 3 trial results",
        item_link="https://example.com/pfizer-phase3",
        item_date=_recent_rfc2822(days_ago=1),
        source="example.com",
    )


@pytest.fixture
def mock_rss_press_release() -> bytes:
    """Valid RSS bytes for a recent Pfizer press release."""
    return _make_rss(
        title="PR Newswire - Pfizer",
        item_title="Pfizer Announces Q1 2026 Financial Results",
        item_link="https://www.prnewswire.com/pfizer-q1-2026",
        item_date=_recent_rfc2822(days_ago=2),
        source="prnewswire.com",
    )


@pytest.fixture
def mock_rss_old_item() -> bytes:
    """RSS bytes with a single item published 45 days ago (outside any window)."""
    return _make_rss(
        title="Google News - Pfizer",
        item_title="Old Pfizer news from 45 days ago",
        item_link="https://example.com/old-pfizer",
        item_date=_recent_rfc2822(days_ago=45),
        source="example.com",
    )


@pytest.fixture
def mock_rss_sec_item() -> bytes:
    """RSS bytes for an item that looks like an SEC filing (must be filtered)."""
    return _make_rss(
        title="SEC EDGAR",
        item_title="8-K Filing by Pfizer Inc",
        item_link="https://www.sec.gov/Archives/pfizer-8k",
        item_date=_recent_rfc2822(days_ago=1),
        source="sec.gov",
    )


# ---------------------------------------------------------------------------
# Mock ticker data
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_tickers() -> dict:
    """Minimal ticker map: ABBR -> company name."""
    return {
        "PFE": "Pfizer",
        "MRNA": "Moderna",
        "REGN": "Regeneron Pharmaceuticals",
        "CRSP": "CRISPR Therapeutics",
    }


# ---------------------------------------------------------------------------
# CSV upload helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_csv_bytes() -> bytes:
    """CSV file bytes with 3 valid ticker/company entries."""
    return b"company\nPFE\nMRNA\nREGN\n"


@pytest.fixture
def oversized_csv_bytes() -> bytes:
    """CSV file bytes exceeding the 1 MB size limit."""
    return b"company\n" + b"PFIZER\n" * 200_000  # ~1.4 MB


@pytest.fixture
def too_many_rows_csv_bytes() -> bytes:
    """CSV with 55 rows (above the 50-row limit)."""
    rows = "\n".join(f"COMPANY{i}" for i in range(55))
    return f"company\n{rows}\n".encode()


@pytest.fixture
def malformed_csv_bytes() -> bytes:
    """Bytes that are not valid UTF-8."""
    return b"\xff\xfe invalid utf-8 data"
