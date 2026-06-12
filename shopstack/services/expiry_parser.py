from __future__ import annotations

import re
from datetime import date, datetime

_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "SEPT": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}

_DATE_PATTERNS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d-%m-%y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d %b %y",
)


def parse_expiry_value(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None

    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue

    normalized = _normalize_month_text(text)
    if normalized != text:
        for pattern in _DATE_PATTERNS:
            try:
                return datetime.strptime(normalized, pattern).date()
            except ValueError:
                continue

    match = re.search(r"(\d{1,2})\s+([A-Za-z]{3,4})\s+(\d{2,4})", text)
    if match:
        day = int(match.group(1))
        month = _MONTHS.get(match.group(2).upper(), 0)
        year = int(match.group(3))
        if year < 100:
            year += 2000
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def expiry_risk_label(expiry_date: date | None, today: date | None = None) -> str:
    if expiry_date is None:
        return "unknown"
    ref = today or date.today()
    delta = (expiry_date - ref).days
    if delta < 0:
        return "expired"
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta <= 3:
        return "soon"
    return "fine"


def _normalize_month_text(text: str) -> str:
    parts = text.upper().split()
    if len(parts) < 3:
        return text
    rebuilt = []
    for part in parts:
        rebuilt.append(part if part not in _MONTHS else f"{part.title()}")
    return " ".join(rebuilt)

