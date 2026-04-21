# server/models/schemas.py
# Pydantic request/response models for the Industry News webapp API.
# Inputs:  raw user-facing query/upload parameters
# Outputs: typed, validated Python objects consumed by routes and services
# Assumptions: days is constrained to exactly 7 or 30; content_type is an enum.

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ContentType(str, Enum):
    headlines = "headlines"
    press_releases = "press_releases"
    stock_price = "stock_price"


class TimeframeDays(int, Enum):
    week = 7
    month = 30


class SearchRequest(BaseModel):
    """Query parameters for a single-company search."""

    q: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Company name or ticker symbol",
    )
    content_type: ContentType = Field(
        default=ContentType.headlines,
        description="Which view to return",
    )
    days: TimeframeDays = Field(
        default=TimeframeDays.week,
        description="Lookback window: 7 or 30 days",
    )

    @field_validator("q")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class NewsItem(BaseModel):
    """A single news headline or press release."""

    title: str
    link: str
    source: str
    published_date: Optional[str] = None  # ISO-8601 UTC string or None
    summary_snippet: Optional[str] = None


class ResolvedCompany(BaseModel):
    """Result of ticker / company-name resolution."""

    ticker: Optional[str] = None
    company_name: str
    found: bool  # True when a known ticker <-> name mapping was found


class SearchResponse(BaseModel):
    """Full response for a single-company search."""

    query: str
    resolved: ResolvedCompany
    content_type: ContentType
    days: int
    items: list[NewsItem] = Field(default_factory=list)
    # For stock_price views the items list is empty; the client renders the
    # TradingView widget directly using `resolved.ticker`.


class UploadError(BaseModel):
    """A per-row error from CSV batch processing."""

    row: int
    value: str
    reason: str


class UploadResponse(BaseModel):
    """Response for a CSV batch upload."""

    total_requested: int
    results: list[SearchResponse] = Field(default_factory=list)
    errors: list[UploadError] = Field(default_factory=list)
