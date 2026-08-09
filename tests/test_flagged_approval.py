"""Tests for flagged attendance approval and ignore functionality."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytz
import pytest
from sqlalchemy.orm import Session

from models.attendance import AttendanceStatus
from models.user import User, UserRole
from services.attendance_service import AttendanceService
from services.auth_service import AuthService
from utils.exceptions import ValidationError


@pytest.fixture
def test_user(test_db: Session) -> User:
    """Create a test user for flagged approval tests."""
    auth_service = AuthService(test_db)
    user = auth_service.register_user(
        email="flagged_test@test.com",
        password="testpass123",
        full_name="Flagged Test User",
        role=UserRole.EMPLOYEE,
        hourly_rate=500.0
    )
    return user


class TestFlaggedApproval:
    """Test approval and ignore functionality for flagged attendance."""

    def test_approve_flagged_attendance_retains_hours(self, test_db: Session, test_user: User):
        """Test that approving a flagged record retains hours for payroll."""
        attendance_service = AttendanceService(test_db)

        # Create a shift with excessive hours (will be flagged)
        check_in = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        check_out = datetime(2024, 1, 15, 23, 0, 0, tzinfo=pytz.UTC)  # 14 hours

        attendance_service.check_in(test_user.id, check_in)
        record = attendance_service.check_out(test_user.id, check_out)

        # Should be flagged with capped hours
        assert record.status == AttendanceStatus.FLAGGED
        assert record.regular_hours == Decimal("8.00")
        assert record.overtime_hours == Decimal("4.00")

        # Approve the record
        approved = attendance_service.approve_flagged_attendance(record.id)

        assert approved.status == AttendanceStatus.APPROVED
        assert approved.regular_hours == Decimal("8.00")
        assert approved.overtime_hours == Decimal("4.00")

        # Verify it's included in total hours calculation
        totals = attendance_service.calculate_total_hours(
            user_id=test_user.id,
            start_date=check_in.date(),
            end_date=check_out.date()
        )

        assert totals["regular_hours"] == Decimal("8.00")
        assert totals["overtime_hours"] == Decimal("4.00")

    def test_ignore_flagged_attendance_zeros_hours(self, test_db: Session, test_user: User):
        """Test that ignoring a flagged record zeros out hours for payroll."""
        attendance_service = AttendanceService(test_db)

        # Create a shift with excessive hours (will be flagged)
        check_in = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        check_out = datetime(2024, 1, 15, 23, 0, 0, tzinfo=pytz.UTC)  # 14 hours

        attendance_service.check_in(test_user.id, check_in)
        record = attendance_service.check_out(test_user.id, check_out)

        # Should be flagged with capped hours
        assert record.status == AttendanceStatus.FLAGGED
        assert record.regular_hours == Decimal("8.00")
        assert record.overtime_hours == Decimal("4.00")

        # Ignore the record
        ignored = attendance_service.ignore_flagged_attendance(record.id)

        assert ignored.status == AttendanceStatus.IGNORED
        assert ignored.regular_hours == Decimal("0.00")
        assert ignored.overtime_hours == Decimal("0.00")

        # Verify it's excluded from total hours calculation
        totals = attendance_service.calculate_total_hours(
            user_id=test_user.id,
            start_date=check_in.date(),
            end_date=check_out.date()
        )

        assert totals["regular_hours"] == Decimal("0.00")
        assert totals["overtime_hours"] == Decimal("0.00")

    def test_approve_non_flagged_fails(self, test_db: Session, test_user: User):
        """Test that approving a non-flagged record fails."""
        attendance_service = AttendanceService(test_db)

        # Create a normal completed shift
        check_in = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        check_out = datetime(2024, 1, 15, 17, 0, 0, tzinfo=pytz.UTC)  # 8 hours

        attendance_service.check_in(test_user.id, check_in)
        record = attendance_service.check_out(test_user.id, check_out)

        assert record.status == AttendanceStatus.COMPLETED

        # Should fail to approve non-flagged record
        with pytest.raises(ValidationError) as exc_info:
            attendance_service.approve_flagged_attendance(record.id)

        assert "not flagged" in exc_info.value.message

    def test_ignore_non_flagged_fails(self, test_db: Session, test_user: User):
        """Test that ignoring a non-flagged record fails."""
        attendance_service = AttendanceService(test_db)

        # Create a normal completed shift
        check_in = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        check_out = datetime(2024, 1, 15, 17, 0, 0, tzinfo=pytz.UTC)  # 8 hours

        attendance_service.check_in(test_user.id, check_in)
        record = attendance_service.check_out(test_user.id, check_out)

        assert record.status == AttendanceStatus.COMPLETED

        # Should fail to ignore non-flagged record
        with pytest.raises(ValidationError) as exc_info:
            attendance_service.ignore_flagged_attendance(record.id)

        assert "not flagged" in exc_info.value.message

    def test_approved_records_included_in_payroll_totals(self, test_db: Session, test_user: User):
        """Test that approved records are included in payroll calculations."""
        attendance_service = AttendanceService(test_db)

        # Create a normal shift (8 hours)
        check_in1 = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        check_out1 = datetime(2024, 1, 15, 17, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(test_user.id, check_in1)
        attendance_service.check_out(test_user.id, check_out1)

        # Create a flagged shift (14 hours) and approve it
        check_in2 = datetime(2024, 1, 16, 9, 0, 0, tzinfo=pytz.UTC)
        check_out2 = datetime(2024, 1, 16, 23, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(test_user.id, check_in2)
        flagged = attendance_service.check_out(test_user.id, check_out2)
        attendance_service.approve_flagged_attendance(flagged.id)

        # Calculate totals
        totals = attendance_service.calculate_total_hours(
            user_id=test_user.id,
            start_date=check_in1.date(),
            end_date=check_out2.date()
        )

        # Should include both shifts: 8 + 8 = 16 regular, 0 + 4 = 4 overtime
        assert totals["regular_hours"] == Decimal("16.00")
        assert totals["overtime_hours"] == Decimal("4.00")

    def test_ignored_records_excluded_from_payroll_totals(self, test_db: Session, test_user: User):
        """Test that ignored records are excluded from payroll calculations."""
        attendance_service = AttendanceService(test_db)

        # Create a normal shift (8 hours)
        check_in1 = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        check_out1 = datetime(2024, 1, 15, 17, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(test_user.id, check_in1)
        attendance_service.check_out(test_user.id, check_out1)

        # Create a flagged shift (14 hours) and ignore it
        check_in2 = datetime(2024, 1, 16, 9, 0, 0, tzinfo=pytz.UTC)
        check_out2 = datetime(2024, 1, 16, 23, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(test_user.id, check_in2)
        flagged = attendance_service.check_out(test_user.id, check_out2)
        attendance_service.ignore_flagged_attendance(flagged.id)

        # Calculate totals
        totals = attendance_service.calculate_total_hours(
            user_id=test_user.id,
            start_date=check_in1.date(),
            end_date=check_out2.date()
        )

        # Should only include the first shift: 8 regular, 0 overtime
        assert totals["regular_hours"] == Decimal("8.00")
        assert totals["overtime_hours"] == Decimal("0.00")
