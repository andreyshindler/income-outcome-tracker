import re
from datetime import datetime
from typing import Optional, Tuple

# Hebrew + English keywords that usually mark the line with the actual total
TOTAL_KEYWORDS = [
    'סה"כ', "סהכ", "סך הכל", "לתשלום", "total", "amount due", "total due", "grand total"
]

# A run of digits that may be grouped with '.', ',', spaces or non-breaking spaces.
# We deliberately capture the whole run (e.g. "1,234.56") and disambiguate the
# thousands/decimal separators in _parse_number, instead of letting a naive
# `\d{1,5}([.,]\d{2})` regex slice "1,234.56" into "1,23" + "4.56".
NUMBER_PATTERN = re.compile(r"\d[\d.,  ]*\d|\d")

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b"),
    re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2})\b"),
]


def _parse_number(token: str) -> Optional[Tuple[float, bool]]:
    """
    Parse a single numeric token into (value, had_decimal_part).

    Handles both decimal conventions and thousands separators:
      "1,234.56" -> (1234.56, True)   "1.234,56" -> (1234.56, True)
      "12,50"    -> (12.5, True)      "1,234"    -> (1234.0, False)
      "50"       -> (50.0, False)     "50.00"    -> (50.0, True)

    `had_decimal_part` lets the caller prefer money-looking figures (which
    almost always carry agorot/cents) over bare integers like phone numbers.
    """
    token = token.strip().replace(" ", "").replace(" ", "")
    if not token:
        return None

    has_dot = "." in token
    has_comma = "," in token
    had_decimal = False

    if has_dot and has_comma:
        # Whichever separator appears last is the decimal point.
        if token.rfind(".") > token.rfind(","):
            token = token.replace(",", "")
        else:
            token = token.replace(".", "").replace(",", ".")
        had_decimal = True
    elif has_comma:
        # A single comma followed by 1-2 digits is a decimal comma; otherwise
        # it's a thousands separator.
        if token.count(",") == 1 and len(token.rsplit(",", 1)[1]) in (1, 2):
            token = token.replace(",", ".")
            had_decimal = True
        else:
            token = token.replace(",", "")
    elif has_dot:
        if token.count(".") == 1 and len(token.rsplit(".", 1)[1]) in (1, 2):
            had_decimal = True
        else:
            token = token.replace(".", "")

    try:
        return float(token), had_decimal
    except ValueError:
        return None


def extract_amount(text: str) -> Optional[float]:
    """
    Receipts usually contain several numbers (line items, VAT, total).
    Strategy: prefer the largest number on a line containing a "total" keyword;
    otherwise fall back to the largest money-looking number (one with a decimal
    part), and only then to the largest bare integer. Preferring decimals first
    avoids latching onto phone numbers / IDs that have no agorot.
    """
    all_nums = []
    decimal_nums = []
    total_line_nums = []

    for line in text.splitlines():
        line_nums = []
        for match in NUMBER_PATTERN.finditer(line):
            parsed = _parse_number(match.group(0))
            if parsed is None:
                continue
            value, had_decimal = parsed
            line_nums.append(value)
            all_nums.append(value)
            if had_decimal:
                decimal_nums.append(value)

        if not line_nums:
            continue

        lowered = line.lower()
        if any(kw.lower() in lowered for kw in TOTAL_KEYWORDS):
            total_line_nums.extend(line_nums)

    if total_line_nums:
        return round(max(total_line_nums), 2)
    if decimal_nums:
        return round(max(decimal_nums), 2)
    if all_nums:
        return round(max(all_nums), 2)
    return None


def extract_date(text: str) -> Optional[str]:
    # Best-effort: returns the first parseable dd/mm/yyyy(-ish) date in the
    # text. On some receipts this can be a print/validity date rather than the
    # purchase date - worth spot-checking against the stored image.
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            day, month, year = match.groups()
            year = int(year)
            if year < 100:
                year += 2000
            try:
                return datetime(year, int(month), int(day)).date().isoformat()
            except ValueError:
                continue
    return None


def extract_vendor(text: str) -> Optional[str]:
    """Best-effort: first non-trivial line of the receipt is usually the business name."""
    for line in text.splitlines():
        cleaned = line.strip()
        if len(cleaned) >= 3 and not cleaned.replace(" ", "").isdigit():
            return cleaned
    return None
