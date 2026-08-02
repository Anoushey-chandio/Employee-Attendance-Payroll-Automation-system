"""Formatting utilities for currency, dates, and decimal values.

Ensures consistent display formatting across the UI layer.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import pytz


def format_currency(amount: Decimal, currency_symbol: str = "PKR") -> str:
    """
    Format a Decimal amount as currency with thousands separators.

    Args:
        amount: Decimal amount to format
        currency_symbol: Currency symbol to append (default: PKR)

    Returns:
        Formatted currency string (e.g., "1,234.56 PKR")
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    # Format with 2 decimal places and thousands separator
    formatted = f"{amount:,.2f}"
    return f"{formatted} {currency_symbol}"


def format_decimal(value: Decimal, decimal_places: int = 2) -> str:
    """
    Format a Decimal value with specified decimal places.

    Args:
        value: Decimal value to format
        decimal_places: Number of decimal places (default: 2)

    Returns:
        Formatted decimal string
    """
    if not isinstance(value, Decimal):
        value = Decimal(str(value))

    format_str = f"{{:,.{decimal_places}f}}"
    return format_str.format(value)


def format_datetime(
    dt: datetime,
    timezone: str = "UTC",
    format_str: str = "%Y-%m-%d %H:%M:%S"
) -> str:
    """
    Format a datetime object to string with timezone conversion.

    Args:
        dt: Datetime object to format
        timezone: Target timezone name (default: UTC)
        format_str: Output format string

    Returns:
        Formatted datetime string
    """
    if dt is None:
        return ""

    # Ensure datetime is timezone-aware
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)

    # Convert to target timezone
    target_tz = pytz.timezone(timezone)
    dt_converted = dt.astimezone(target_tz)

    return dt_converted.strftime(format_str)


def format_date(d: date, format_str: str = "%Y-%m-%d") -> str:
    """
    Format a date object to string.

    Args:
        d: Date object to format
        format_str: Output format string (default: ISO format)

    Returns:
        Formatted date string
    """
    if d is None:
        return ""

    return d.strftime(format_str)


def format_hours(hours: Decimal) -> str:
    """
    Format hours with 2 decimal places.

    Args:
        hours: Decimal hours value

    Returns:
        Formatted hours string (e.g., "8.50 hrs")
    """
    if not isinstance(hours, Decimal):
        hours = Decimal(str(hours))

    return f"{hours:.2f} hrs"
