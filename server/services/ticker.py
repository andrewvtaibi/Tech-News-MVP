# server/services/ticker.py
# Resolves user input (ticker or company name) to a canonical
# {ticker, company_name, found} result.
#
# Inputs:  raw string query (ticker abbreviation or company name)
# Outputs: ResolvedCompany dataclass
# Assumptions:
#   - tickers.json maps TICKER -> "Company Name" (all caps keys)
#   - Partial company-name matching: first token of input matched against
#     names that START with that token (case-insensitive)
#   - This is intentionally a static local lookup; no network calls.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ResolvedCompany:
    ticker: Optional[str]
    company_name: str
    found: bool


_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "tickers.json"

# Allowed characters in a query (letters, digits, spaces, hyphens, ampersands,
# periods, colons). Colon supports EXCHANGE:TICKER format (e.g. TSE:7974).
# Anything else indicates noise / injection attempt.
_CLEAN_PATTERN = re.compile(r"^[A-Za-z0-9 &\-\.:]+$")

# Matches a bare ticker symbol. Accepts:
#   - 1-6 uppercase letters:                AAPL, MSFT, F, BRK
#   - dot share-class suffix:               BRK.A, BRK.B, NESN.SW
#   - exchange-prefixed (digits allowed):   TSE:7974, LSE:BP, ASX:CBA
# Pure numeric inputs (e.g. "12345") are intentionally rejected to
# avoid treating arbitrary numbers as US-exchange tickers.
_TICKER_FORMAT = re.compile(
    r"^(?:[A-Z]{2,6}:[A-Z0-9]{1,6}|[A-Z]{1,6})(\.[A-Z]{1,3})?$"
)


class TickerService:
    """
    Bidirectional ticker <-> company name lookup.

    The internal store is:
        _by_ticker:  { "PFE": "Pfizer" }          (uppercased keys)
        _by_name:    { "pfizer": "PFE" }           (lowercased keys)
    """

    def __init__(self, ticker_map: dict[str, str]) -> None:
        self._by_ticker: dict[str, str] = {}
        self._by_name: dict[str, str] = {}
        for ticker, name in ticker_map.items():
            t = ticker.strip().upper()
            n = name.strip()
            if t and n:
                self._by_ticker[t] = n
                self._by_name[n.lower()] = t

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, query: str) -> ResolvedCompany:
        """
        Resolve *query* to a ResolvedCompany.
        Never raises; returns found=False for unrecognized inputs.
        """
        q = (query or "").strip()

        if not q:
            return ResolvedCompany(ticker=None, company_name=q, found=False)

        # Reject obviously hostile or nonsensical input early
        if not _CLEAN_PATTERN.match(q) or len(q) > 200:
            return ResolvedCompany(
                ticker=None, company_name=q, found=False
            )

        # 1. Exact ticker match (case-insensitive)
        upper_q = q.upper()
        if upper_q in self._by_ticker:
            name = self._by_ticker[upper_q]
            return ResolvedCompany(
                ticker=upper_q, company_name=name, found=True
            )

        # 2. Exact company-name match (case-insensitive)
        lower_q = q.lower()
        if lower_q in self._by_name:
            ticker = self._by_name[lower_q]
            name = self._by_ticker[ticker]
            return ResolvedCompany(
                ticker=ticker, company_name=name, found=True
            )

        # 3. Partial company-name match: find names that contain *q* as a
        #    word-prefix or substring (case-insensitive, first match wins)
        for name_lower, ticker in self._by_name.items():
            if name_lower.startswith(lower_q):
                name = self._by_ticker[ticker]
                return ResolvedCompany(
                    ticker=ticker, company_name=name, found=True
                )

        # Broader substring scan (lower priority)
        for name_lower, ticker in self._by_name.items():
            if lower_q in name_lower:
                name = self._by_ticker[ticker]
                return ResolvedCompany(
                    ticker=ticker, company_name=name, found=True
                )

        # Passthrough: input looks like a valid ticker symbol but isn't in
        # the local hint map. Let TradingView attempt to resolve it.
        if _TICKER_FORMAT.match(upper_q):
            return ResolvedCompany(
                ticker=upper_q, company_name=upper_q, found=False
            )

        return ResolvedCompany(ticker=None, company_name=q, found=False)

    def __len__(self) -> int:
        return len(self._by_ticker)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_data_file(
        cls, path: Path | None = None
    ) -> "TickerService":
        """
        Load from the bundled data/tickers.json.
        Raises RuntimeError with a clear message if the file is missing
        or malformed.
        """
        p = path or _DATA_FILE
        if not p.exists():
            raise RuntimeError(
                f"Ticker data file not found: {p}. "
                "Ensure data/tickers.json exists in the project root."
            )
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Invalid JSON in ticker data file {p}: {exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Failed to read ticker data file {p}: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                f"Ticker data file {p} must be a JSON object "
                f"(TICKER -> company name), got {type(data).__name__}"
            )
        return cls(data)
