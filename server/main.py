# server/main.py
# FastAPI application factory.
# Inputs:  environment variables for CORS / rate limiting / cache TTL
# Outputs: ASGI app object
#
# Responsibilities:
#   - Instantiate shared services (TickerService, NewsService, NewsCache)
#   - Register API routers under /api
#   - Mount /static for the frontend
#   - Apply security middleware: CSP headers, CORS, rate limiting
#   - Structured error handling that never leaks internal details

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from server.routes import health, search, upload
from server.services.cache import NewsCache
from server.services.news import NewsService
from server.services.ticker import TickerService
from server.security.limiter import limiter

logger = logging.getLogger("industry-news.server")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]
_STATIC_DIR = _ROOT / "static"

# ---------------------------------------------------------------------------
# Security headers middleware
# ---------------------------------------------------------------------------

_TRADINGVIEW_CSP = (
    "https://s3.tradingview.com "
    "https://s.tradingview.com "
    "https://widget.tradingview.com"
)

_CSP = (
    "default-src 'self'; "
    f"script-src 'self' 'unsafe-inline' {_TRADINGVIEW_CSP}; "
    "frame-src 'self' "
    "https://www.tradingview.com "
    "https://www.tradingview-widget.com "
    "https://s3.tradingview.com "
    "https://s.tradingview.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security-hardening HTTP response headers to every response.
    Never modifies or inspects the request body.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )
        return response


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """
    Build and return the FastAPI application.
    Called once at startup (and by tests).
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: initialize shared services
        cache_ttl = int(os.environ.get("CACHE_TTL_SECONDS", "900"))
        app.state.cache = NewsCache(default_ttl=cache_ttl)
        app.state.ticker_service = TickerService.from_data_file()
        app.state.news_service = NewsService()
        logger.info(
            "Industry News server started. "
            f"Ticker entries: {len(app.state.ticker_service)}. "
            f"Cache TTL: {cache_ttl}s."
        )
        yield
        # Shutdown: nothing to clean up for in-memory services
        logger.info("Industry News server shutting down.")

    app = FastAPI(
        title="Company Reports and Information Engine",
        description=(
            "Search companies or ticker symbols for headlines, "
            "press releases, and stock widgets."
        ),
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # -- Rate limiting -------------------------------------------------------
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # -- CORS ----------------------------------------------------------------
    raw_origins = os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000",
    )
    allowed_origins = [o.strip() for o in raw_origins.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
    )

    # -- Security headers ----------------------------------------------------
    app.add_middleware(SecurityHeadersMiddleware)

    # -- Global error handler (never leak internals) -------------------------
    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled server error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal server error occurred."},
        )

    # -- API routes ----------------------------------------------------------
    app.include_router(health.router, prefix="/api")
    app.include_router(search.router, prefix="/api")
    app.include_router(upload.router, prefix="/api")

    # -- Static files (frontend) ---------------------------------------------
    if _STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")

    return app


# ---------------------------------------------------------------------------
# Entry point for `uvicorn server.main:app`
# ---------------------------------------------------------------------------

app = create_app()
