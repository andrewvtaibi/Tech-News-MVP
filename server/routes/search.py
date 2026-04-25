# server/routes/search.py
# GET /api/search — single-company search endpoint.
#
# Inputs (query params):
#   q:            company name or ticker (required, 1-100 chars)
#   content_type: headlines | press_releases | stock_price (default: headlines)
#   days:         7 | 30 (default: 7)
#
# Outputs: SearchResponse JSON
#
# Failure modes:
#   400: empty / missing query
#   422: invalid content_type or days value (Pydantic auto-handles)
#
# Assumptions:
#   - NewsService and TickerService are instantiated once per process
#     (shared via app.state, injected here via Depends).
#   - Cache is checked before fetching; miss -> fetch -> cache.

from __future__ import annotations

import asyncio
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from server.models.schemas import (
    ContentType,
    NewsItem,
    ResolvedCompany,
    SearchResponse,
    TimeframeDays,
)
from server.security.sanitize import sanitize_query

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_news_service(request: Request):
    return request.app.state.news_service


def _get_ticker_service(request: Request):
    return request.app.state.ticker_service


def _get_cache(request: Request):
    return request.app.state.cache


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get(
    "/search",
    response_model=SearchResponse,
    tags=["search"],
    summary="Search for company headlines, press releases, or stock widget data",
)
async def search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100,
                   description="Company name or ticker symbol"),
    content_type: ContentType = Query(
        default=ContentType.headlines,
        description="Which content type to return",
    ),
    days: TimeframeDays = Query(
        default=TimeframeDays.week,
        description="Lookback window: 7 or 30 days",
    ),
):
    clean_q = sanitize_query(q)
    if not clean_q:
        raise HTTPException(
            status_code=400,
            detail="Query must contain at least one valid character.",
        )

    ticker_svc = _get_ticker_service(request)
    cache = _get_cache(request)
    news_svc = _get_news_service(request)

    resolved = ticker_svc.resolve(clean_q)
    resolved_model = ResolvedCompany(
        ticker=resolved.ticker,
        company_name=resolved.company_name,
        found=resolved.found,
    )

    # Stock price views require no backend fetch — the client renders
    # the TradingView widget directly using the resolved ticker.
    if content_type == ContentType.stock_price:
        return SearchResponse(
            query=clean_q,
            resolved=resolved_model,
            content_type=content_type,
            days=days.value,
            items=[],
        )

    # Cache key uses the resolved canonical name when available, so
    # "MSFT" and "Microsoft" share a single cache entry.
    cache_subject = (
        resolved.company_name if resolved.found else clean_q
    )
    cache_key = cache.make_key(
        cache_subject, content_type.value, days.value
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return SearchResponse(
            query=clean_q,
            resolved=resolved_model,
            content_type=content_type,
            days=days.value,
            items=cached,
        )

    # Determine the best search term: prefer the resolved company name
    # for better RSS query precision.
    search_term = resolved.company_name if resolved.found else clean_q

    # Execute the synchronous RSS fetch in a thread so we don't block
    # the event loop.
    loop = asyncio.get_running_loop()
    if content_type == ContentType.press_releases:
        fetch_fn = partial(
            news_svc.fetch_press_releases, search_term, days.value
        )
    else:
        fetch_fn = partial(
            news_svc.fetch_headlines, search_term, days.value
        )

    items: list[NewsItem] = await loop.run_in_executor(None, fetch_fn)

    # Cache the result
    cache.set(cache_key, items)

    return SearchResponse(
        query=clean_q,
        resolved=resolved_model,
        content_type=content_type,
        days=days.value,
        items=items,
    )
