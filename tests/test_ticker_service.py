# tests/test_ticker_service.py
# TDD tests for server/services/ticker.py
# Written BEFORE implementation (red phase).

from __future__ import annotations

from unittest.mock import patch

import pytest

from server.services.ticker import TickerService, ResolvedCompany


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ticker_map() -> dict:
    return {
        "PFE": "Pfizer",
        "MRNA": "Moderna",
        "REGN": "Regeneron Pharmaceuticals",
        "CRSP": "CRISPR Therapeutics",
        "ABBV": "AbbVie",
    }


@pytest.fixture
def service(ticker_map) -> TickerService:
    return TickerService(ticker_map)


# ---------------------------------------------------------------------------
# A. Specification tests
# ---------------------------------------------------------------------------

class TestTickerServiceResolve:
    def test_resolve_known_ticker_uppercase(self, service):
        result = service.resolve("PFE")
        assert result.found is True
        assert result.ticker == "PFE"
        assert result.company_name == "Pfizer"

    def test_resolve_known_ticker_lowercase(self, service):
        """Ticker lookup is case-insensitive."""
        result = service.resolve("pfe")
        assert result.found is True
        assert result.ticker == "PFE"

    def test_resolve_known_company_name_exact(self, service):
        result = service.resolve("Pfizer")
        assert result.found is True
        assert result.ticker == "PFE"
        assert result.company_name == "Pfizer"

    def test_resolve_known_company_name_lowercase(self, service):
        """Company-name lookup is also case-insensitive."""
        result = service.resolve("moderna")
        assert result.found is True
        assert result.ticker == "MRNA"

    def test_resolve_partial_company_name(self, service):
        """Partial match on company name returns the best match."""
        result = service.resolve("Regeneron")
        assert result.found is True
        assert result.ticker == "REGN"

    def test_resolve_unknown_name_returns_not_found(self, service):
        # A multi-word string that doesn't match any ticker pattern
        # should yield found=False with no ticker (treat as private /
        # unrecognized company name).
        result = service.resolve("Unknown Random Company")
        assert result.found is False
        assert result.ticker is None
        assert result.company_name == "Unknown Random Company"

    def test_resolve_unknown_ticker_format_passes_through(self, service):
        # A bare 1-5 letter all-caps input that isn't in the hint map
        # should still pass through as a ticker (let TradingView resolve).
        result = service.resolve("ZZZZZ")
        assert result.found is False
        assert result.ticker == "ZZZZZ"
        assert result.company_name == "ZZZZZ"

    def test_resolve_empty_string_returns_not_found(self, service):
        result = service.resolve("")
        assert result.found is False
        assert result.company_name == ""

    def test_resolve_returns_resolved_company_type(self, service):
        result = service.resolve("PFE")
        assert isinstance(result, ResolvedCompany)

    def test_resolve_whitespace_stripped(self, service):
        """Leading/trailing spaces on input are tolerated."""
        result = service.resolve("  PFE  ")
        assert result.found is True
        assert result.ticker == "PFE"


# ---------------------------------------------------------------------------
# B. Adversarial tests
# ---------------------------------------------------------------------------

class TestTickerServiceAdversarial:
    def test_xss_payload_returns_not_found(self, service):
        result = service.resolve("<script>alert(1)</script>")
        assert result.found is False

    def test_very_long_input_returns_not_found(self, service):
        result = service.resolve("A" * 500)
        assert result.found is False

    def test_sql_injection_returns_not_found(self, service):
        result = service.resolve("'; DROP TABLE tickers; --")
        assert result.found is False

    def test_numeric_input_returns_not_found(self, service):
        result = service.resolve("12345")
        assert result.found is False


# ---------------------------------------------------------------------------
# C. Invariant checks
# ---------------------------------------------------------------------------

class TestTickerServiceInvariants:
    def test_company_name_always_non_none(self, service):
        """company_name must never be None, even for unknown queries."""
        for q in ["PFE", "Unknown Corp", "", "   "]:
            result = service.resolve(q)
            assert result.company_name is not None

    def test_found_true_implies_ticker_set(self, service):
        for ticker in ["PFE", "MRNA", "REGN"]:
            result = service.resolve(ticker)
            if result.found:
                assert result.ticker is not None

    def test_found_false_for_non_ticker_implies_ticker_none(self, service):
        # Inputs that don't look like tickers (multi-word names, very
        # long strings) should still yield ticker=None when not in the
        # hint map. Inputs that look like tickers pass through (covered
        # by test_resolve_unknown_ticker_format_passes_through).
        result = service.resolve("Some Unknown Company Inc")
        assert result.found is False
        assert result.ticker is None


# ---------------------------------------------------------------------------
# Factory / load tests
# ---------------------------------------------------------------------------

class TestTickerServiceFactory:
    def test_from_data_file_loads_successfully(self):
        """TickerService.from_data_file() loads the real tickers.json."""
        svc = TickerService.from_data_file()
        # The real file must contain at least PFE
        result = svc.resolve("PFE")
        assert result.found is True

    def test_from_data_file_contains_minimum_entries(self):
        """Real tickers.json must have at least 50 entries."""
        svc = TickerService.from_data_file()
        assert len(svc) >= 50
