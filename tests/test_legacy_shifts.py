"""Tests for legacy shift auto-close functionality."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytz
import pytest
from sqlalchemy.orm import Session

from models.attendance import AttendanceStatus
from models.user import User, UserRole
from services.attendance_service import AttendanceService
from services.auth_service import AuthService


@pytest.fixture
def test_user(test_db: Session) -> User:
    """Create a test user for legacy shift tests."""
    auth_service = AuthService(test_db)
    user = auth_service.register_user(
        email="legacy_test@test.com",
        password="testpass123",
        full_name="Legacy Test User",
        role=UserRole.EMPLOYEE,
        hourly_rate=500.0
    )
    return user


class TestLegacyShiftAutoClose:
    """Test automatic closure of legacy shifts older than 24 hours."""

    def test_auto_close_legacy_shift_48_hours_old(self, test_db: Session, test_user: User):
        """Test that a shift 48 hours old is automatically closed."""
        attendance_service = AttendanceService(test_db)

        # Create a shift 48 hours ago
        old_check_in = datetime.now(pytz.UTC) - timedelta(hours=48)
        shift = attendance_service.check_in(test_user.id, old_check_in)

        assert shift.check_out is None
        assert shift.status == AttendanceStatus.PRESENT

        # Run auto-close
        count = attendance_service.auto_close_legacy_shifts()

        assert count == 1

        # Verify shift was closed with 12-hour duration
        test_db.refresh(shift)
        assert shift.check_out is not None
        assert shift.status == AttendanceStatus.FLAGGED

        # Check_out should be check_in + 12 hours
        expected_check_out = old_check_in + timedelta(hours=12)
        assert shift.check_out.replace(tzinfo=None) == expected_check_out.replace(tzinfo=None)

        # Should have 12 hours: 8 regular + 4 overtime
        assert shift.regular_hours == Decimal("8.00")
        assert shift.overtime_hours == Decimal("4.00")
        assert shift.total_hours == Decimal("12.00")

    def test_auto_close_ignores_shifts_under_24_hours(self, test_db: Session, test_user: User):
        """Test that shifts under 24 hours old are not auto-closed."""
        attendance_service = AttendanceService(test_db)

        # Create a shift 12 hours ago (under 24-hour threshold)
        recent_check_in = datetime.now(pytz.UTC) - timedelta(hours=12)
        shift = attendance_service.check_in(test_user.id, recent_check_in)

        assert shift.check_out is None

        # Run auto-close
        count = attendance_service.auto_close_legacy_shifts()

        # Should not close any shifts
        assert count == 0

        # Verify shift is still open
        test_db.refresh(shift)
        assert shift.check_out is None
        assert shift.status == AttendanceStatus.PRESENT

    def test_auto_close_multiple_legacy_shifts(self, test_db: Session, test_user: User):
        """Test auto-closing multiple legacy shifts."""
        attendance_service = AttendanceService(test_db)

        # Create three old shifts on different days
        for days_ago in [3, 4, 5]:
            old_check_in = datetime.now(pytz.UTC) - timedelta(days=days_ago)
            attendance_service.check_in(test_user.id, old_check_in)

        # Run auto-close
        count = attendance_service.auto_close_legacy_shifts()

        # Should close all three shifts
        assert count == 3

        # Verify all were flagged
        flagged = attendance_service.get_flagged_attendance()
        assert len(flagged) == 3
        for shift in flagged:
            assert shift.check_out is not None
            assert shift.status == AttendanceStatus.FLAGGED

    def test_get_active_attendance_returns_none_after_auto_close(
        self, test_db: Session, test_user: User
    ):
        """Test that get_active_attendance returns None after auto-close."""
        attendance_service = AttendanceService(test_db)

        # Create a legacy shift
        old_check_in = datetime.now(pytz.UTC) - timedelta(hours=72)
        attendance_service.check_in(test_user.id, old_check_in)

        # Verify shift is active before auto-close
        active = attendance_service.get_active_attendance(test_user.id)
        assert active is not None

        # Run auto-close
        attendance_service.auto_close_legacy_shifts()

        # Verify no active attendance now
        active_after = attendance_service.get_active_attendance(test_user.id)
        assert active_after is None

    def test_check_out_targets_most_recent_shift(self, test_db: Session, test_user: User):
        """Test that check_out targets the most recent open shift."""
        attendance_service = AttendanceService(test_db)

        # Create an old legacy shift (48 hours ago)
        old_check_in = datetime.now(pytz.UTC) - timedelta(hours=48)
        old_shift = attendance_service.check_in(test_user.id, old_check_in)

        # Close the legacy shift automatically
        attendance_service.auto_close_legacy_shifts()
        test_db.refresh(old_shift)
        assert old_shift.check_out is not None

        # Create a new current shift (1 hour ago)
        recent_check_in = datetime.now(pytz.UTC) - timedelta(hours=1)
        new_shift = attendance_service.check_in(test_user.id, recent_check_in)

        # Check out should target the NEW shift, not the old one
        checked_out = attendance_service.check_out(test_user.id)

        # Verify the NEW shift was checked out
        assert checked_out.id == new_shift.id
        assert checked_out.check_out is not None
        assert checked_out.regular_hours == Decimal("1.00")
        assert checked_out.overtime_hours == Decimal("0.00")

        # Verify old shift remains unchanged
        test_db.refresh(old_shift)
        assert old_shift.status == AttendanceStatus.FLAGGED
