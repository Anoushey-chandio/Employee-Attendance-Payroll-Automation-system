"""Tests for attendance service and anomaly detection.

Tests check-in/out operations, overtime calculation, double check-in prevention,
and auto-flagging logic.
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytz
from sqlalchemy.orm import Session

from models.attendance import Attendance, AttendanceStatus
from models.user import User
from services.attendance_service import AttendanceService
from utils.exceptions import AttendanceError, ValidationError


class TestCheckInOperations:
    """Test cases for employee check-in."""

    def test_check_in_success(self, test_db: Session, sample_user: User):
        """Test successful check-in."""
        attendance_service = AttendanceService(test_db)

        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance = attendance_service.check_in(sample_user.id, check_in_time)

        assert attendance.user_id == sample_user.id
        assert attendance.date == date(2024, 1, 15)
        # SQLite stores naive datetimes, so compare without timezone
        assert attendance.check_in.replace(tzinfo=None) == check_in_time.replace(tzinfo=None)
        assert attendance.check_out is None
        assert attendance.is_open_shift is True
        assert attendance.status == AttendanceStatus.PRESENT

    def test_check_in_default_time(self, test_db: Session, sample_user: User):
        """Test check-in with default current time."""
        attendance_service = AttendanceService(test_db)

        attendance = attendance_service.check_in(sample_user.id)

        assert attendance.user_id == sample_user.id
        assert attendance.check_in is not None
        assert attendance.is_open_shift is True

    def test_double_check_in_prevention(self, test_db: Session, sample_user: User):
        """Test that double check-in on same date is prevented when shift is still active."""
        attendance_service = AttendanceService(test_db)

        # First check-in
        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        # Attempt second check-in on same date while first shift is still open
        with pytest.raises(AttendanceError) as exc_info:
            second_check_in = datetime(2024, 1, 15, 10, 0, 0, tzinfo=pytz.UTC)
            attendance_service.check_in(sample_user.id, second_check_in)

        assert "active shift" in exc_info.value.message.lower()

    def test_check_in_different_days(self, test_db: Session, sample_user: User):
        """Test check-in on different days is allowed."""
        attendance_service = AttendanceService(test_db)

        # Day 1
        day1_check_in = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance1 = attendance_service.check_in(sample_user.id, day1_check_in)

        # Close day 1
        day1_check_out = datetime(2024, 1, 15, 17, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_out(sample_user.id, day1_check_out)

        # Day 2
        day2_check_in = datetime(2024, 1, 16, 9, 0, 0, tzinfo=pytz.UTC)
        attendance2 = attendance_service.check_in(sample_user.id, day2_check_in)

        assert attendance2.date == date(2024, 1, 16)
        assert attendance1.id != attendance2.id

    def test_multiple_shifts_same_day_allowed(self, test_db: Session, sample_user: User):
        """Test that multiple shifts on the same day are allowed after completing previous shift."""
        attendance_service = AttendanceService(test_db)

        # First shift - check in and check out
        shift1_check_in = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance1 = attendance_service.check_in(sample_user.id, shift1_check_in)

        shift1_check_out = datetime(2024, 1, 15, 13, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_out(sample_user.id, shift1_check_out)

        # Second shift on same day - should be allowed after first shift is completed
        shift2_check_in = datetime(2024, 1, 15, 18, 0, 0, tzinfo=pytz.UTC)
        attendance2 = attendance_service.check_in(sample_user.id, shift2_check_in)

        # Verify both shifts exist for the same date
        assert attendance1.date == date(2024, 1, 15)
        assert attendance2.date == date(2024, 1, 15)
        assert attendance1.id != attendance2.id
        assert attendance1.check_out is not None  # First shift is completed
        assert attendance2.check_out is None  # Second shift is still open


class TestCheckOutOperations:
    """Test cases for employee check-out."""

    def test_check_out_success(self, test_db: Session, sample_user: User):
        """Test successful check-out with hours calculation."""
        attendance_service = AttendanceService(test_db)

        # Check in at 9 AM
        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        # Check out at 5 PM (8 hours)
        check_out_time = datetime(2024, 1, 15, 17, 0, 0, tzinfo=pytz.UTC)
        attendance = attendance_service.check_out(sample_user.id, check_out_time)

        # SQLite stores naive datetimes, so compare without timezone
        assert attendance.check_out.replace(tzinfo=None) == check_out_time.replace(tzinfo=None)
        assert attendance.regular_hours == Decimal("8.00")
        assert attendance.overtime_hours == Decimal("0.00")
        assert attendance.total_hours == Decimal("8.00")
        assert attendance.status == AttendanceStatus.COMPLETED

    def test_check_out_with_overtime(self, test_db: Session, sample_user: User):
        """Test check-out with overtime hours calculation."""
        attendance_service = AttendanceService(test_db)

        # Check in at 9 AM
        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        # Check out at 7 PM (10 hours total: 8 regular + 2 overtime)
        check_out_time = datetime(2024, 1, 15, 19, 0, 0, tzinfo=pytz.UTC)
        attendance = attendance_service.check_out(sample_user.id, check_out_time)

        assert attendance.regular_hours == Decimal("8.00")
        assert attendance.overtime_hours == Decimal("2.00")
        assert attendance.total_hours == Decimal("10.00")
        assert attendance.status == AttendanceStatus.COMPLETED

    def test_check_out_excessive_overtime_flagged(self, test_db: Session, sample_user: User):
        """Test that excessive overtime (>4 hours) triggers flagged status."""
        attendance_service = AttendanceService(test_db)

        # Check in at 9 AM
        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        # Check out at 11 PM (14 hours total)
        check_out_time = datetime(2024, 1, 15, 23, 0, 0, tzinfo=pytz.UTC)
        attendance = attendance_service.check_out(sample_user.id, check_out_time)

        # Should cap at 8 regular + 4 overtime = 12 total, status flagged
        assert attendance.regular_hours == Decimal("8.00")
        assert attendance.overtime_hours == Decimal("4.00")
        assert attendance.status == AttendanceStatus.FLAGGED

    def test_check_out_without_check_in(self, test_db: Session, sample_user: User):
        """Test that check-out without check-in fails."""
        attendance_service = AttendanceService(test_db)

        check_out_time = datetime(2024, 1, 15, 17, 0, 0, tzinfo=pytz.UTC)

        with pytest.raises(AttendanceError) as exc_info:
            attendance_service.check_out(sample_user.id, check_out_time)

        assert "no open shift" in exc_info.value.message.lower()

    def test_check_out_before_check_in_fails(self, test_db: Session, sample_user: User):
        """Test that check-out time before check-in time fails."""
        attendance_service = AttendanceService(test_db)

        # Check in at 9 AM
        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        # Try to check out at 8 AM (before check-in)
        invalid_check_out = datetime(2024, 1, 15, 8, 0, 0, tzinfo=pytz.UTC)

        with pytest.raises(AttendanceError) as exc_info:
            attendance_service.check_out(sample_user.id, invalid_check_out)

        assert "after check-in" in exc_info.value.message.lower()

    def test_overtime_cap_boundary(self, test_db: Session, sample_user: User):
        """Test exact overtime cap boundary (8 + 4 = 12 hours)."""
        attendance_service = AttendanceService(test_db)

        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        # Exactly 12 hours (8 regular + 4 overtime)
        check_out_time = datetime(2024, 1, 15, 21, 0, 0, tzinfo=pytz.UTC)
        attendance = attendance_service.check_out(sample_user.id, check_out_time)

        assert attendance.regular_hours == Decimal("8.00")
        assert attendance.overtime_hours == Decimal("4.00")
        assert attendance.status == AttendanceStatus.COMPLETED  # At cap, not flagged

    def test_partial_hour_calculation(self, test_db: Session, sample_user: User):
        """Test calculation with partial hours (e.g., 8.5 hours)."""
        attendance_service = AttendanceService(test_db)

        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        # 8 hours 30 minutes
        check_out_time = datetime(2024, 1, 15, 17, 30, 0, tzinfo=pytz.UTC)
        attendance = attendance_service.check_out(sample_user.id, check_out_time)

        assert attendance.regular_hours == Decimal("8.00")
        assert attendance.overtime_hours == Decimal("0.50")
        assert attendance.total_hours == Decimal("8.50")


class TestAttendanceRetrieval:
    """Test cases for attendance record retrieval."""

    def test_get_attendance_by_user(self, test_db: Session, sample_user: User):
        """Test retrieving attendance records for a user."""
        attendance_service = AttendanceService(test_db)

        # Create multiple attendance records
        for day in range(1, 4):
            check_in = datetime(2024, 1, day, 9, 0, 0, tzinfo=pytz.UTC)
            check_out = datetime(2024, 1, day, 17, 0, 0, tzinfo=pytz.UTC)
            attendance_service.check_in(sample_user.id, check_in)
            attendance_service.check_out(sample_user.id, check_out)

        records = attendance_service.get_attendance_by_user(sample_user.id)

        assert len(records) == 3

    def test_get_attendance_by_date_range(self, test_db: Session, sample_user: User):
        """Test retrieving attendance with date range filter."""
        attendance_service = AttendanceService(test_db)

        # Create records for multiple days
        for day in range(1, 6):
            check_in = datetime(2024, 1, day, 9, 0, 0, tzinfo=pytz.UTC)
            check_out = datetime(2024, 1, day, 17, 0, 0, tzinfo=pytz.UTC)
            attendance_service.check_in(sample_user.id, check_in)
            attendance_service.check_out(sample_user.id, check_out)

        # Query for specific range
        records = attendance_service.get_attendance_by_user(
            user_id=sample_user.id,
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 4)
        )

        assert len(records) == 3  # Days 2, 3, 4

    def test_get_open_shifts(self, test_db: Session, sample_user: User):
        """Test retrieving all open shifts."""
        attendance_service = AttendanceService(test_db)

        # Create open shift
        check_in_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in_time)

        open_shifts = attendance_service.get_open_shifts()

        assert len(open_shifts) == 1
        assert open_shifts[0].is_open_shift is True

    def test_get_flagged_attendance(self, test_db: Session, sample_user: User):
        """Test retrieving flagged attendance records."""
        attendance_service = AttendanceService(test_db)

        # Create excessive overtime (flagged)
        check_in = datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in)

        # 14 hours should be flagged
        check_out = datetime(2024, 1, 15, 23, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_out(sample_user.id, check_out)

        flagged = attendance_service.get_flagged_attendance()

        assert len(flagged) == 1
        assert flagged[0].status == AttendanceStatus.FLAGGED


class TestAnomalyDetection:
    """Test cases for anomaly detection and auto-flagging."""

    def test_auto_flag_unclosed_shifts(self, test_db: Session, sample_user: User):
        """Test auto-flagging of shifts left open past midnight."""
        attendance_service = AttendanceService(test_db)

        # Create attendance from yesterday (unclosed)
        yesterday = datetime.now(pytz.UTC) - timedelta(days=1)
        attendance = Attendance(
            user_id=sample_user.id,
            date=yesterday.date(),
            check_in=yesterday,
            check_out=None,
            regular_hours=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            status=AttendanceStatus.PRESENT
        )
        test_db.add(attendance)
        test_db.commit()

        # Auto-flag
        flagged_count = attendance_service.auto_flag_unclosed_shifts()

        assert flagged_count == 1

        # Verify the record was flagged
        test_db.refresh(attendance)
        assert attendance.status == AttendanceStatus.FLAGGED
        assert attendance.regular_hours == Decimal("0.00")
        assert attendance.overtime_hours == Decimal("0.00")

    def test_auto_flag_ignores_today(self, test_db: Session, sample_user: User):
        """Test that auto-flag doesn't flag today's open shifts."""
        attendance_service = AttendanceService(test_db)

        # Create today's open shift
        today = datetime.now(pytz.UTC)
        attendance = Attendance(
            user_id=sample_user.id,
            date=today.date(),
            check_in=today,
            check_out=None,
            regular_hours=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            status=AttendanceStatus.PRESENT
        )
        test_db.add(attendance)
        test_db.commit()

        # Auto-flag
        flagged_count = attendance_service.auto_flag_unclosed_shifts()

        assert flagged_count == 0

        # Verify status unchanged
        test_db.refresh(attendance)
        assert attendance.status == AttendanceStatus.PRESENT

    def test_approve_flagged_attendance(self, test_db: Session, sample_user: User):
        """Test approving a flagged attendance record."""
        attendance_service = AttendanceService(test_db)

        # Create flagged record
        attendance = Attendance(
            user_id=sample_user.id,
            date=date(2024, 1, 15),
            check_in=datetime(2024, 1, 15, 9, 0, 0, tzinfo=pytz.UTC),
            check_out=datetime(2024, 1, 15, 23, 0, 0, tzinfo=pytz.UTC),
            regular_hours=Decimal("8.00"),
            overtime_hours=Decimal("4.00"),
            status=AttendanceStatus.FLAGGED
        )
        test_db.add(attendance)
        test_db.commit()
        test_db.refresh(attendance)

        # Approve
        approved = attendance_service.approve_flagged_attendance(attendance.id)

        assert approved.status == AttendanceStatus.APPROVED


class TestHoursCalculation:
    """Test cases for hours calculation accuracy."""

    def test_calculate_total_hours_for_period(self, test_db: Session, sample_user: User):
        """Test calculating total hours for a date range."""
        attendance_service = AttendanceService(test_db)

        # Create multiple records
        for day in range(1, 4):
            check_in = datetime(2024, 1, day, 9, 0, 0, tzinfo=pytz.UTC)
            check_out = datetime(2024, 1, day, 19, 0, 0, tzinfo=pytz.UTC)  # 10 hours each
            attendance_service.check_in(sample_user.id, check_in)
            attendance_service.check_out(sample_user.id, check_out)

        totals = attendance_service.calculate_total_hours(
            user_id=sample_user.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 3)
        )

        assert totals["regular_hours"] == Decimal("24.00")  # 8 * 3
        assert totals["overtime_hours"] == Decimal("6.00")  # 2 * 3

    def test_calculate_total_hours_excludes_flagged(self, test_db: Session, sample_user: User):
        """Test that flagged records are excluded from totals."""
        attendance_service = AttendanceService(test_db)

        # Normal day
        check_in1 = datetime(2024, 1, 1, 9, 0, 0, tzinfo=pytz.UTC)
        check_out1 = datetime(2024, 1, 1, 17, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in1)
        attendance_service.check_out(sample_user.id, check_out1)

        # Flagged day (excessive hours)
        check_in2 = datetime(2024, 1, 2, 9, 0, 0, tzinfo=pytz.UTC)
        check_out2 = datetime(2024, 1, 2, 23, 0, 0, tzinfo=pytz.UTC)
        attendance_service.check_in(sample_user.id, check_in2)
        attendance_service.check_out(sample_user.id, check_out2)

        totals = attendance_service.calculate_total_hours(
            user_id=sample_user.id,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2)
        )

        # Should only count the first day (not flagged)
        assert totals["regular_hours"] == Decimal("8.00")
        assert totals["overtime_hours"] == Decimal("0.00")
