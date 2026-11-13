"""
STUDIQS® SmartParent™ (v6.3 Complete) - Academic Calendar & Date Utilities
=============================================================================
Module: src.smartparent.utils.date_helpers

Provides production date helpers tailored to Indian Academic Schedules
(CBSE / ICSE / State Boards: Academic Year cycles from April 1 to March 31).
=============================================================================
"""

from datetime import date, datetime, timezone
from typing import Any, Optional, Union


def get_academic_year(d: Optional[date] = None) -> str:
    """
    Computes Indian academic year (April 1 to March 31).
    Example: 2026-02-15 falls into '2025-2026'; 2026-05-10 falls into '2026-2027'.
    """
    target = d or date.today()
    if target.month >= 4:
        return f"{target.year}-{target.year + 1}"
    return f"{target.year - 1}-{target.year}"


def parse_date_safe(val: Any) -> Optional[date]:
    """
    Safely parses diverse date inputs (ISO strings, timestamps, datetimes, dates).
    Returns None rather than raising exceptions on malformed formats.
    """
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        val_str = val.strip()
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(val_str, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(val_str).date()
        except ValueError:
            return None
    return None


def format_iso_date(d: Optional[Union[date, datetime]]) -> Optional[str]:
    """Formats date or datetime to YYYY-MM-DD string."""
    if d is None:
        return None
    if isinstance(d, datetime):
        return d.strftime("%Y-%m-%d")
    return d.isoformat()


def calculate_days_until(target_date: date) -> int:
    """Calculates days remaining from today until target date (can be negative if elapsed)."""
    return (target_date - date.today()).days


def get_current_utc_timestamp() -> datetime:
    """Returns current datetime in UTC with explicit timezone awareness."""
    return datetime.now(timezone.utc)
