"""Formatting utilities for currency, dates, and decimal values.

Ensures consistent display formatting across the UI layer.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import pytz

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

if ZoneInfo is not None:
    PKT_TZ = ZoneInfo("Asia/Karachi")
else:
    PKT_TZ = pytz.timezone("Asia/Karachi")


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


def _get_timezone(timezone_name: Optional[str] = None):
    """Resolve a timezone name safely, falling back to PKT."""
    if not timezone_name:
        return PKT_TZ

    try:
        if ZoneInfo is not None:
            return ZoneInfo(timezone_name)
        return pytz.timezone(timezone_name)
    except Exception:
        return PKT_TZ


def _coerce_datetime(dt: Optional[datetime], timezone_name: Optional[str] = None) -> Optional[datetime]:
    """Normalize a datetime to a timezone-aware value without crashing on naive data."""
    if dt is None or not isinstance(dt, datetime):
        return None

    if dt.tzinfo is None:
        try:
            target_tz = _get_timezone(timezone_name)
            if hasattr(target_tz, "localize"):
                return target_tz.localize(dt)
            return dt.replace(tzinfo=target_tz)
        except Exception:
            return dt.replace(tzinfo=pytz.UTC)

    return dt


def format_datetime(
    dt: datetime,
    timezone: str = "Asia/Karachi",
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

    try:
        dt = _coerce_datetime(dt, timezone)
        if dt is None:
            return ""
        target_tz = _get_timezone(timezone)
        dt_converted = dt.astimezone(target_tz)
        return dt_converted.strftime(format_str)
    except Exception:
        try:
            return dt.strftime(format_str)
        except Exception:
            return str(dt)


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


def calculate_shift_metrics(check_in: Optional[datetime], check_out: Optional[datetime] = None) -> dict:
    """
    Centralized calculation engine for shift duration and status.
    Single source of truth for all time calculations across the system.

    Args:
        check_in: Check-in timestamp (timezone-aware or naive)
        check_out: Check-out timestamp (timezone-aware or naive, None for open shifts)

    Returns:
        dict with:
            - display_duration: str - "X mins" if < 60 mins, "X.X hrs" if >= 1 hr
            - status_label: str - "IN PROGRESS", "PARTIAL (X mins)", "PARTIAL (X.X hrs)", "COMPLETED", "FLAGGED", "ABSENT"
            - total_hours_numeric: Decimal - Raw hours for payroll calculation
            - total_minutes: int - Total minutes worked
    """
    # Handle ABSENT case
    if check_in is None:
        return {
            "display_duration": "0 mins",
            "status_label": "ABSENT",
            "total_hours_numeric": Decimal("0.00"),
            "total_minutes": 0
        }

    # Normalize check_in to timezone-aware
    check_in_normalized = _coerce_datetime(check_in)
    if check_in_normalized is None:
        check_in_normalized = check_in

    # Handle IN PROGRESS case
    if check_out is None:
        current_time = datetime.now(PKT_TZ)
        duration_seconds = (current_time - check_in_normalized).total_seconds()
        total_minutes = int(duration_seconds / 60)
        total_hours = Decimal(str(duration_seconds / 3600)).quantize(Decimal("0.01"))

        if total_minutes < 60:
            display = f"{total_minutes} mins"
        else:
            display = f"{float(total_hours):.1f} hrs"

        return {
            "display_duration": display,
            "status_label": "IN PROGRESS",
            "total_hours_numeric": total_hours,
            "total_minutes": total_minutes
        }

    # Normalize check_out to timezone-aware
    check_out_normalized = _coerce_datetime(check_out)
    if check_out_normalized is None:
        check_out_normalized = check_out

    # Calculate completed shift duration
    duration_seconds = (check_out_normalized - check_in_normalized).total_seconds()
    total_minutes = int(duration_seconds / 60)
    total_hours = Decimal(str(duration_seconds / 3600)).quantize(Decimal("0.01"))

    # Determine display format
    if total_minutes < 60:
        display_duration = f"{total_minutes} mins"
        status_label = f"PARTIAL ({total_minutes} mins)"
    else:
        hours_float = float(total_hours)
        display_duration = f"{hours_float:.1f} hrs"

        # Determine status based on duration thresholds
        if hours_float < 7.5:
            status_label = f"PARTIAL ({hours_float:.1f} hrs)"
        elif hours_float >= 12.0:
            status_label = "FLAGGED"
        else:
            status_label = "COMPLETED"

    return {
        "display_duration": display_duration,
        "status_label": status_label,
        "total_hours_numeric": total_hours,
        "total_minutes": total_minutes
    }


def format_employee_id(uuid_str: str, all_users: list = None) -> str:
    """
    Format a UUID employee ID into a clean sequential display format.

    Args:
        uuid_str: The UUID string to format
        all_users: Optional list of all User objects for sequential numbering

    Returns:
        Formatted employee ID (e.g., "EMP-001")
    """
    if not uuid_str:
        return "N/A"

    # If we have a list of all users, generate sequential number based on position
    if all_users:
        try:
            # Find the index position of this user in the sorted list
            user_ids = sorted([user.id for user in all_users])
            if uuid_str in user_ids:
                sequential_num = user_ids.index(uuid_str) + 1
                return f"EMP-{sequential_num:03d}"
        except Exception:
            pass

    # Fallback: generate a consistent hash-based short ID from UUID
    # This ensures the same UUID always maps to the same short ID
    import hashlib
    hash_digest = hashlib.md5(uuid_str.encode()).hexdigest()
    # Use first 6 hex characters for a short, consistent ID
    short_id = hash_digest[:6].upper()
    return f"EMP-{short_id}"


def format_attendance_status(attendance_record) -> str:
    """
    Format attendance status for UI display with enhanced clarity.

    Preserves backend enum values while providing user-friendly display strings.

    Args:
        attendance_record: Attendance model object with check_in, check_out, and status

    Returns:
        Formatted status string for display:
        - "PRESENT (Shift Completed)" - when check_out is not null
        - "PRESENT (In Progress)" - when check_in exists but check_out is null
        - "ABSENT" - when no check_in
        - "IGNORED" - when status is IGNORED
        - "FLAGGED" - when status is FLAGGED
        - "APPROVED" - when status is APPROVED
    """
    from models.attendance import AttendanceStatus

    # Handle null/missing record
    if attendance_record is None:
        return "ABSENT"

    # Check backend status first for special cases
    status = attendance_record.status

    # IGNORED shifts - clearly marked
    if status == AttendanceStatus.IGNORED:
        return "IGNORED"

    # FLAGGED shifts - clearly marked
    if status == AttendanceStatus.FLAGGED:
        return "FLAGGED"

    # APPROVED shifts - show as completed
    if status == AttendanceStatus.APPROVED:
        return "APPROVED (Shift Completed)"

    # Check if shift is completed (has check_out timestamp)
    if attendance_record.check_out is not None:
        # Shift is completed - show PRESENT (Shift Completed)
        return "PRESENT (Shift Completed)"

    # Check if shift is in progress (has check_in but no check_out)
    if attendance_record.check_in is not None:
        # Shift is active - show PRESENT (In Progress)
        return "PRESENT (In Progress)"

    # No check_in - absent
    return "ABSENT"
