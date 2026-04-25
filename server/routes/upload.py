# server/routes/upload.py
# POST /api/upload — CSV batch search endpoint.
#
# Inputs (multipart form-data):
#   file: CSV file (max 1 MB, max 50 rows, UTF-8)
#   content_type: headlines | press_releases | stock_price (default: headlines)
#   days: 7 | 30 (default: 7)
#
# Outputs: UploadResponse JSON (list of SearchResponse per company + errors)
#
# Failure modes:
#   400: empty file, size > 1 MB, > 50 rows, non-UTF-8 encoding
#   422: invalid content_type or days value

from __future__ import annotations

import asyncio
from functools import partial

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form

from server.models.schemas import (
    ContentType,
    NewsItem,
    ResolvedCompany,
    SearchResponse,
    TimeframeDays,
    UploadError,
    UploadResponse,
)
from server.security.sanitize import sanitize_query, validate_csv

router = APIRouter()


@router.post(
    "/upload",
    response_model=UploadResponse,
    tags=["upload"],
    summary="Upload a CSV of company names or tickers for batch search",
)
async def upload_csv(
    request: Request,
    file: UploadFile = File(..., description="CSV with company names or tickers"),
    content_type: ContentType = Form(
        default=ContentType.headlines,
        description="Which content type to return",
    ),
    days: TimeframeDays = Form(
        default=TimeframeDays.week,
        description="Lookback window: 7 or 30 days",
    ),
):
    # ---- Validate and extract CSV values --------------------------------
    try:
        raw_bytes = await file.read()
        import io
        queries = validate_csv(io.BytesIO(raw_bytes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not queries:
        raise HTTPException(
            status_code=400,
            detail=(
                "No valid company names or ticker symbols found in the "
                "uploaded CSV."
            ),
        )

    ticker_svc = request.app.state.ticker_service
    cache = request.app.state.cache
    news_svc = request.app.state.news_service

    results: list[SearchResponse] = []
    errors: list[UploadError] = []
    loop = asyncio.get_running_loop()

    for idx, raw_q in enumerate(queries):
        clean_q = sanitize_query(raw_q)
        if not clean_q:
            errors.append(
                UploadError(
                    row=idx + 1,
                    value=raw_q,
                    reason="Value is empty after sanitization.",
                )
            )
            continue

        resolved = ticker_svc.resolve(clean_q)
        resolved_model = ResolvedCompany(
            ticker=resolved.ticker,
            company_name=resolved.company_name,
            found=resolved.found,
        )

        if content_type == ContentType.stock_price:
            results.append(
                SearchResponse(
                    query=clean_q,
                    resolved=resolved_model,
                    content_type=content_type,
                    days=days.value,
                    items=[],
                )
            )
            continue

        cache_subject = (
            resolved.company_name if resolved.found else clean_q
        )
        cache_key = cache.make_key(
            cache_subject, content_type.value, days.value
        )
        cached = cache.get(cache_key)
        if cached is not None:
            results.append(
                SearchResponse(
                    query=clean_q,
                    resolved=resolved_model,
                    content_type=content_type,
                    days=days.value,
                    items=cached,
                )
            )
            continue

        search_term = resolved.company_name if resolved.found else clean_q

        try:
            if content_type == ContentType.press_releases:
                fetch_fn = partial(
                    news_svc.fetch_press_releases, search_term, days.value
                )
            else:
                fetch_fn = partial(
                    news_svc.fetch_headlines, search_term, days.value
                )

            items: list[NewsItem] = await loop.run_in_executor(None, fetch_fn)
            cache.set(cache_key, items)

            results.append(
                SearchResponse(
                    query=clean_q,
                    resolved=resolved_model,
                    content_type=content_type,
                    days=days.value,
                    items=items,
                )
            )
        except Exception as exc:
            errors.append(
                UploadError(
                    row=idx + 1,
                    value=raw_q,
                    reason=f"Fetch failed: {type(exc).__name__}",
                )
            )

    return UploadResponse(
        total_requested=len(queries),
        results=results,
        errors=errors,
    )
