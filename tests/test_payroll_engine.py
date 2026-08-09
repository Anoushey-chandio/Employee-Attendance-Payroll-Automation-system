"""Tests for payroll calculation engine with Decimal precision.

Tests salary calculations, overtime multipliers, deductions, net pay,
and batch processing with strict financial accuracy.
"""

import pytest
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

import pytz
from sqlalchemy.orm import Session

from models.attendance import Attendance, AttendanceStatus
from models.payroll import PayrollRun, PayrollStatus
from models.user import User
from services.attendance_service import AttendanceService
from services.payroll_engine import PayrollEngine
from utils.exceptions import PayrollProcessingError, ValidationError


class TestGrossPayCalculation:
    """Test cases for gross pay calculation with Decimal precision."""

    def test_calculate_gross_pay_regular_only(self):
        """Test gross pay calculation with only regular hours."""
        result = PayrollEngine.calculate_gross_pay(
            regular_hours=Decimal("40.00"),
            overtime_hours=Decimal("0.00"),
            hourly_rate=Decimal("20.00")
        )

        assert result["base_salary"] == Decimal("800.00")
        assert result["overtime_pay"] == Decimal("0.00")
        assert result["gross_pay"] == Decimal("800.00")

    def test_calculate_gross_pay_with_overtime(self):
        """Test gross pay with overtime at 1.5x rate."""
        result = PayrollEngine.calculate_gross_pay(
            regular_hours=Decimal("40.00"),
            overtime_hours=Decimal("10.00"),
            hourly_rate=Decimal("20.00")
        )

        # Base: 40 * 20 = 800
        # OT: 10 * 20 * 1.5 = 300
        # Total: 1100
        assert result["base_salary"] == Decimal("800.00")
        assert result["overtime_pay"] == Decimal("300.00")
        assert result["gross_pay"] == Decimal("1100.00")

    def test_overtime_multiplier_precision(self):
        """Test that overtime multiplier (1.5x) is applied with precision."""
        result = PayrollEngine.calculate_gross_pay(
            regular_hours=Decimal("8.00"),
            overtime_hours=Decimal("2.00"),
            hourly_rate=Decimal("15.50")
        )

        # Base: 8 * 15.50 = 124.00
        # OT: 2 * 15.50 * 1.5 = 46.50
        # Total: 170.50
        assert result["base_salary"] == Decimal("124.00")
        assert result["overtime_pay"] == Decimal("46.50")
        assert result["gross_pay"] == Decimal("170.50")

    def test_decimal_precision_no_floating_point_errors(self):
        """Test that Decimal prevents floating-point precision errors."""
        # Using values that cause floating-point errors
        result = PayrollEngine.calculate_gross_pay(
            regular_hours=Decimal("8.33"),
            overtime_hours=Decimal("1.67"),
            hourly_rate=Decimal("22.75")
        )

        # All calculations should maintain 2 decimal places
        assert result["base_salary"].as_tuple().exponent == -2
        assert result["overtime_pay"].as_tuple().exponent == -2
        assert result["gross_pay"].as_tuple().exponent == -2

    def test_rounding_half_up(self):
        """Test that calculations use ROUND_HALF_UP."""
        # Create scenario that requires rounding
        result = PayrollEngine.calculate_gross_pay(
            regular_hours=Decimal("7.777"),
            overtime_hours=Decimal("1.111"),
            hourly_rate=Decimal("13.333")
        )

        # Results should be rounded to 2 decimal places
        assert isinstance(result["base_salary"], Decimal)
        assert isinstance(result["overtime_pay"], Decimal)
        assert result["base_salary"] == Decimal("103.69")  # 7.777 * 13.333 = 103.685441 rounds to 103.69
        assert result["overtime_pay"] == Decimal("22.22")  # 1.111 * 13.333 * 1.5 = 22.221945 rounds to 22.22

    def test_zero_hours(self):
        """Test calculation with zero hours."""
        result = PayrollEngine.calculate_gross_pay(
            regular_hours=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            hourly_rate=Decimal("25.00")
        )

        assert result["base_salary"] == Decimal("0.00")
        assert result["overtime_pay"] == Decimal("0.00")
        assert result["gross_pay"] == Decimal("0.00")

    def test_high_hourly_rate(self):
        """Test calculation with high hourly rate."""
        result = PayrollEngine.calculate_gross_pay(
            regular_hours=Decimal("40.00"),
            overtime_hours=Decimal("5.00"),
            hourly_rate=Decimal("150.00")
        )

        # Base: 40 * 150 = 6000
        # OT: 5 * 150 * 1.5 = 1125
        # Total: 7125
        assert result["base_salary"] == Decimal("6000.00")
        assert result["overtime_pay"] == Decimal("1125.00")
        assert result["gross_pay"] == Decimal("7125.00")


class TestNetPayCalculation:
    """Test cases for net pay calculation with deductions."""

    def test_calculate_net_pay_with_deductions(self):
        """Test net pay calculation with deductions."""
        net_pay = PayrollEngine.calculate_net_pay(
            gross_pay=Decimal("1000.00"),
            deductions=Decimal("200.00")
        )

        assert net_pay == Decimal("800.00")

    def test_calculate_net_pay_no_deductions(self):
        """Test net pay with zero deductions."""
        net_pay = PayrollEngine.calculate_net_pay(
            gross_pay=Decimal("1000.00"),
            deductions=Decimal("0.00")
        )

        assert net_pay == Decimal("1000.00")

    def test_calculate_net_pay_high_deductions(self):
        """Test net pay with high deductions."""
        net_pay = PayrollEngine.calculate_net_pay(
            gross_pay=Decimal("5000.00"),
            deductions=Decimal("1500.00")
        )

        assert net_pay == Decimal("3500.00")

    def test_negative_net_pay_protection(self):
        """Test that net pay cannot go negative (capped at 0.00)."""
        net_pay = PayrollEngine.calculate_net_pay(
            gross_pay=Decimal("1000.00"),
            deductions=Decimal("1500.00")  # Deductions exceed gross
        )

        # Should be capped at 0.00, not negative
        assert net_pay == Decimal("0.00")

    def test_net_pay_decimal_precision(self):
        """Test net pay maintains Decimal precision."""
        net_pay = PayrollEngine.calculate_net_pay(
            gross_pay=Decimal("1234.56"),
            deductions=Decimal("234.56")
        )

        assert net_pay == Decimal("1000.00")
        assert net_pay.as_tuple().exponent == -2


class TestPayrollProcessing:
    """Test cases for payroll processing operations."""

    def test_process_payroll_for_user_success(self, test_db: Session, sample_user: User):
        """Test successful payroll processing for a single user."""
        attendance_service = AttendanceService(test_db)
        payroll_engine = PayrollEngine(test_db)

        # Create attendance records
        for day in range(1, 6):  # 5 days
            check_in = datetime(2024, 1, day, 9, 0, 0, tzinfo=pytz.UTC)
            check_out = datetime(2024, 1, day, 19, 0, 0, tzinfo=pytz.UTC)  # 10 hours
            attendance_service.check_in(sample_user.id, check_in)
            attendance_service.check_out(sample_user.id, check_out)

        # Process payroll
        payroll = payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 5),
            deductions=Decimal("100.00")
        )

        # 5 days * 8 regular hours = 40 regular hours
        # 5 days * 2 overtime hours = 10 overtime hours
        # Hourly rate: 20.00
        # Base: 40 * 20 = 800
        # OT: 10 * 20 * 1.5 = 300
        # Gross: 1100
        # Deductions: 100
        # Net: 1000
        assert payroll.base_salary == Decimal("800.00")
        assert payroll.overtime_pay == Decimal("300.00")
        assert payroll.gross_pay == Decimal("1100.00")
        assert payroll.deductions == Decimal("100.00")
        assert payroll.net_pay == Decimal("1000.00")
        assert payroll.status == PayrollStatus.DRAFT

    def test_process_payroll_duplicate_period_fails(self, test_db: Session, sample_user: User):
        """Test that duplicate DRAFT payroll is consolidated, but APPROVED/PAID cannot be overwritten."""
        payroll_engine = PayrollEngine(test_db)

        # First payroll - creates DRAFT
        payroll1 = payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31),
            deductions=Decimal("0.00")
        )
        assert payroll1.status == PayrollStatus.DRAFT

        # Second call with same period - should overwrite DRAFT (consolidation)
        payroll2 = payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31),
            deductions=Decimal("100.00")  # Different deductions
        )

        # Should have succeeded and created a new record
        assert payroll2.status == PayrollStatus.DRAFT
        assert payroll2.deductions == Decimal("100.00")

        # Verify only ONE record exists for this period (consolidated)
        from models.payroll import PayrollRun
        from sqlalchemy import and_
        all_runs = test_db.query(PayrollRun).filter(
            and_(
                PayrollRun.user_id == sample_user.id,
                PayrollRun.pay_period_start == date(2024, 1, 1),
                PayrollRun.pay_period_end == date(2024, 1, 31)
            )
        ).all()
        assert len(all_runs) == 1

        # Approve the payroll
        payroll_engine.approve_payroll(payroll2.id)

        # Now attempting to create another should fail (cannot overwrite APPROVED)
        with pytest.raises(PayrollProcessingError) as exc_info:
            payroll_engine.process_payroll_for_user(
                user_id=sample_user.id,
                pay_period_start=date(2024, 1, 1),
                pay_period_end=date(2024, 1, 31),
                deductions=Decimal("0.00")
            )

        assert "already exists" in exc_info.value.message.lower()

    def test_process_payroll_invalid_date_range(self, test_db: Session, sample_user: User):
        """Test that invalid date range (end before start) fails."""
        payroll_engine = PayrollEngine(test_db)

        with pytest.raises(ValidationError) as exc_info:
            payroll_engine.process_payroll_for_user(
                user_id=sample_user.id,
                pay_period_start=date(2024, 1, 31),
                pay_period_end=date(2024, 1, 1),  # End before start
                deductions=Decimal("0.00")
            )

        assert "after start date" in exc_info.value.message.lower()

    def test_process_payroll_no_attendance(self, test_db: Session, sample_user: User):
        """Test payroll processing with no attendance records."""
        payroll_engine = PayrollEngine(test_db)

        payroll = payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31),
            deductions=Decimal("0.00")
        )

        # All values should be zero
        assert payroll.base_salary == Decimal("0.00")
        assert payroll.overtime_pay == Decimal("0.00")
        assert payroll.gross_pay == Decimal("0.00")
        assert payroll.net_pay == Decimal("0.00")

    def test_process_payroll_default_deductions(self, test_db: Session, sample_user: User):
        """Test payroll processing with default deductions (None)."""
        payroll_engine = PayrollEngine(test_db)

        payroll = payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31)
            # deductions not provided
        )

        assert payroll.deductions == Decimal("0.00")


class TestPayrollBatchProcessing:
    """Test cases for batch payroll processing."""

    def test_process_payroll_batch_all_users(self, test_db: Session, sample_user: User, sample_admin: User):
        """Test batch processing for all active users."""
        payroll_engine = PayrollEngine(test_db)

        payroll_runs = payroll_engine.process_payroll_batch(
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31),
            default_deductions=Decimal("50.00")
        )

        # Should process both users
        assert len(payroll_runs) == 2
        assert all(p.status == PayrollStatus.DRAFT for p in payroll_runs)
        assert all(p.deductions == Decimal("50.00") for p in payroll_runs)

    def test_process_payroll_batch_specific_users(self, test_db: Session, sample_user: User, sample_admin: User):
        """Test batch processing for specific user IDs."""
        payroll_engine = PayrollEngine(test_db)

        payroll_runs = payroll_engine.process_payroll_batch(
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31),
            user_ids=[sample_user.id],
            default_deductions=Decimal("0.00")
        )

        # Should only process specified user
        assert len(payroll_runs) == 1
        assert payroll_runs[0].user_id == sample_user.id


class TestPayrollStatusTransitions:
    """Test cases for payroll status management."""

    def test_approve_payroll(self, test_db: Session, sample_payroll: PayrollRun):
        """Test approving a draft payroll."""
        payroll_engine = PayrollEngine(test_db)

        assert sample_payroll.status == PayrollStatus.DRAFT

        approved = payroll_engine.approve_payroll(sample_payroll.id)

        assert approved.status == PayrollStatus.APPROVED

    def test_approve_non_draft_fails(self, test_db: Session, sample_payroll: PayrollRun):
        """Test that only draft payroll can be approved."""
        payroll_engine = PayrollEngine(test_db)

        # Approve first
        payroll_engine.approve_payroll(sample_payroll.id)

        # Try to approve again
        with pytest.raises(ValidationError) as exc_info:
            payroll_engine.approve_payroll(sample_payroll.id)

        assert "only draft" in exc_info.value.message.lower()

    def test_mark_as_paid(self, test_db: Session, sample_payroll: PayrollRun):
        """Test marking approved payroll as paid."""
        payroll_engine = PayrollEngine(test_db)

        # Approve first
        payroll_engine.approve_payroll(sample_payroll.id)

        # Mark as paid
        paid = payroll_engine.mark_as_paid(sample_payroll.id)

        assert paid.status == PayrollStatus.PAID

    def test_mark_as_paid_requires_approval(self, test_db: Session, sample_payroll: PayrollRun):
        """Test that only approved payroll can be marked as paid."""
        payroll_engine = PayrollEngine(test_db)

        with pytest.raises(ValidationError) as exc_info:
            payroll_engine.mark_as_paid(sample_payroll.id)

        assert "only approved" in exc_info.value.message.lower()

    def test_payroll_status_methods(self, test_db: Session, sample_payroll: PayrollRun):
        """Test payroll status helper methods."""
        payroll_engine = PayrollEngine(test_db)

        # Draft state
        assert sample_payroll.can_modify() is True
        assert sample_payroll.is_approved() is False

        # Approved state
        payroll_engine.approve_payroll(sample_payroll.id)
        test_db.refresh(sample_payroll)
        assert sample_payroll.can_modify() is False
        assert sample_payroll.is_approved() is True

        # Paid state
        payroll_engine.mark_as_paid(sample_payroll.id)
        test_db.refresh(sample_payroll)
        assert sample_payroll.can_modify() is False
        assert sample_payroll.is_approved() is True


class TestPayrollRetrieval:
    """Test cases for payroll record retrieval."""

    def test_get_payroll_by_user(self, test_db: Session, sample_user: User):
        """Test retrieving payroll runs for a user."""
        payroll_engine = PayrollEngine(test_db)

        # Create multiple payroll runs
        for month in range(1, 4):
            payroll_engine.process_payroll_for_user(
                user_id=sample_user.id,
                pay_period_start=date(2024, month, 1),
                pay_period_end=date(2024, month, 28)
            )

        payroll_runs = payroll_engine.get_payroll_by_user(sample_user.id)

        assert len(payroll_runs) == 3

    def test_get_payroll_by_user_with_status_filter(self, test_db: Session, sample_user: User):
        """Test retrieving payroll with status filter."""
        payroll_engine = PayrollEngine(test_db)

        # Create and approve one payroll
        payroll1 = payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31)
        )
        payroll_engine.approve_payroll(payroll1.id)

        # Create another in draft
        payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 2, 1),
            pay_period_end=date(2024, 2, 28)
        )

        # Filter by approved
        approved_runs = payroll_engine.get_payroll_by_user(
            sample_user.id,
            status=PayrollStatus.APPROVED
        )

        assert len(approved_runs) == 1
        assert approved_runs[0].status == PayrollStatus.APPROVED

    def test_get_all_payroll_runs(self, test_db: Session, sample_user: User, sample_admin: User):
        """Test retrieving all payroll runs."""
        payroll_engine = PayrollEngine(test_db)

        # Create payroll for multiple users
        payroll_engine.process_payroll_for_user(
            user_id=sample_user.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31)
        )
        payroll_engine.process_payroll_for_user(
            user_id=sample_admin.id,
            pay_period_start=date(2024, 1, 1),
            pay_period_end=date(2024, 1, 31)
        )

        all_runs = payroll_engine.get_all_payroll_runs()

        assert len(all_runs) == 2


class TestPayrollModelMethods:
    """Test cases for PayrollRun model methods."""

    def test_gross_pay_property(self, sample_payroll: PayrollRun):
        """Test gross_pay calculated property."""
        gross = sample_payroll.gross_pay

        assert gross == sample_payroll.base_salary + sample_payroll.overtime_pay
        assert gross == Decimal("3650.00")

    def test_period_duration_days(self, sample_payroll: PayrollRun):
        """Test pay period duration calculation."""
        # Jan 1 to Jan 31 = 31 days
        assert sample_payroll.period_duration_days == 31
