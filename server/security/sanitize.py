# server/security/sanitize.py
# Input sanitization: search query cleaning and CSV upload validation.
#
# Inputs:  raw user string or file-like BytesIO object
# Outputs: cleaned string or list[str]
# Failure modes:
#   - validate_csv raises ValueError with a descriptive message for:
#       empty file, size > 1 MB, rows > 50, non-UTF-8 encoding
#   - sanitize_query never raises; returns empty string for None / bad input

from __future__ import annotations

import csv
import io
import re
import urllib.parse
from typing import BinaryIO

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_QUERY_LEN = 100

_MAX_CSV_BYTES = 1_048_576      # 1 MB
_MAX_CSV_ROWS  = 50

# Characters allowed in a sanitized query:
# letters, digits, spaces, hyphens, ampersands, periods, commas, colons.
# Colon supports exchange-prefixed tickers (e.g. TSE:7974, LSE:BP).
_ALLOWED_RE = re.compile(r"[^A-Za-z0-9 &\-\.,:]")

# Dangerous tag blocks (script, style, etc.) including their content
_DANGEROUS_TAG_BLOCK_RE = re.compile(
    r"<(script|style|iframe|object|embed|form)[^>]*>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)

# Remaining HTML/XML tags (opening, closing, self-closing)
_TAG_RE = re.compile(r"<[^>]*>", re.DOTALL)

# Dangerous control characters
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_query(raw) -> str:
    """
    Return a clean, safe version of *raw* suitable for use in RSS URL
    query parameters.

    Steps (in order):
      1. Coerce None / non-str to str.
      2. URL-decode (catches %3Cscript%3E patterns).
      3. Strip HTML tags.
      4. Remove control characters (\\x00, \\n, \\t, etc.).
      5. Remove characters outside the allowed set.
      6. Collapse whitespace and strip.
      7. Truncate to _MAX_QUERY_LEN.

    Never raises.
    """
    if raw is None:
        return ""
    if not isinstance(raw, str):
        try:
            raw = str(raw)
        except Exception:
            return ""

    # 1. URL-decode (handles %3Cscript%3E etc.)
    try:
        raw = urllib.parse.unquote(raw)
    except Exception:
        pass

    # 2. Strip dangerous tag blocks (including inner content) then any
    #    remaining HTML tags
    raw = _DANGEROUS_TAG_BLOCK_RE.sub("", raw)
    raw = _TAG_RE.sub("", raw)

    # 3. Remove control characters
    raw = _CONTROL_RE.sub(" ", raw)

    # 4. Remove disallowed characters
    raw = _ALLOWED_RE.sub("", raw)

    # 5. Collapse whitespace and strip
    raw = re.sub(r"\s+", " ", raw).strip()

    # 6. Truncate
    return raw[:_MAX_QUERY_LEN]


def validate_csv(file: BinaryIO) -> list[str]:
    """
    Validate and extract company names / ticker symbols from a CSV upload.

    Arguments:
        file: a binary file-like object (e.g. io.BytesIO or UploadFile.file)

    Returns:
        list[str] -- cleaned, non-empty values from the first column,
                     excluding any detected header row.

    Raises:
        ValueError with a descriptive message for:
          - empty file
          - file size > 1 MB
          - non-UTF-8 encoding
          - more than 50 data rows
    """
    raw_bytes = file.read()

    if not raw_bytes:
        raise ValueError(
            "Uploaded file is empty. "
            "Please provide a CSV with company names or ticker symbols."
        )

    if len(raw_bytes) > _MAX_CSV_BYTES:
        raise ValueError(
            f"Uploaded file size ({len(raw_bytes):,} bytes) exceeds the "
            f"1 MB limit. Please reduce the number of rows."
        )

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError(
            "File encoding error: the CSV must be saved as UTF-8. "
            "Please re-save the file with UTF-8 encoding and try again."
        )

    reader = csv.reader(io.StringIO(text))

    values: list[str] = []
    header_skipped = False

    for row in reader:
        if not row:
            continue
        cell = row[0].strip()
        if not cell:
            continue

        # Skip the header row: if the value is clearly a header label
        # (all letters, no digits, e.g. "company", "ticker", "name"),
        # and we haven't seen real data yet.
        if not header_skipped:
            if re.match(r"^[A-Za-z ]+$", cell) and cell.lower() in {
                "company", "ticker", "name", "symbol", "tickers",
                "companies", "company name", "ticker symbol",
            }:
                header_skipped = True
                continue

        # Sanitize each cell value
        clean = sanitize_query(cell)
        if clean:
            values.append(clean)

    if len(values) > _MAX_CSV_ROWS:
        raise ValueError(
            f"CSV contains {len(values)} data rows, which exceeds the "
            f"{_MAX_CSV_ROWS}-row limit per upload."
        )

    return values
