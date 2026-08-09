"""Payroll calculation engine with financial precision.

Handles salary calculations, overtime pay, deductions, and payroll processing
with strict Decimal precision for financial accuracy.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from config.settings import get_settings
from models.payroll import PayrollRun, PayrollStatus
from models.user import User
from services.attendance_service import AttendanceService
from utils.exceptions import PayrollProcessingError, ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class PayrollEngine:
    """Payroll calculation and processing engine with Decimal precision."""

    def __init__(self, db: Session) -> None:
        """
        Initialize payroll engine.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.attendance_service = AttendanceService(db)

    @staticmethod
    def calculate_gross_pay(
        regular_hours: Decimal,
        overtime_hours: Decimal,
        hourly_rate: Decimal
    ) -> dict[str, Decimal]:
        """
        Calculate gross pay with financial precision.

        Formula:
        - Base Salary = Regular Hours × Hourly Rate
        - Overtime Pay = Overtime Hours × Hourly Rate × 1.5
        - Gross Pay = Base Salary + Overtime Pay

        Args:
            regular_hours: Regular hours worked
            overtime_hours: Overtime hours worked
            hourly_rate: Employee hourly rate

        Returns:
            Dictionary with 'base_salary', 'overtime_pay', and 'gross_pay'
        """
        # Ensure all inputs are Decimal
        regular_hours = Decimal(str(regular_hours))
        overtime_hours = Decimal(str(overtime_hours))
        hourly_rate = Decimal(str(hourly_rate))

        overtime_multiplier = Decimal(str(settings.overtime_multiplier))

        # Calculate base salary (regular hours)
        base_salary = (regular_hours * hourly_rate).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        # Calculate overtime pay (1.5x rate)
        overtime_pay = (overtime_hours * hourly_rate * overtime_multiplier).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        # Calculate gross pay
        gross_pay = base_salary + overtime_pay

        return {
            "base_salary": base_salary,
            "overtime_pay": overtime_pay,
            "gross_pay": gross_pay
        }

    @staticmethod
    def calculate_net_pay(gross_pay: Decimal, deductions: Decimal) -> Decimal:
        """
        Calculate net pay after deductions.

        Formula: Net Pay = Gross Pay - Deductions

        Args:
            gross_pay: Total gross earnings
            deductions: Total deductions (tax, etc.)

        Returns:
            Net pay as Decimal
        """
        gross_pay = Decimal(str(gross_pay))
        deductions = Decimal(str(deductions))

        net_pay = (gross_pay - deductions).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        # Net pay cannot be negative
        if net_pay < Decimal("0.00"):
            logger.warning(
                f"Negative net pay calculated: gross={gross_pay}, deductions={deductions}"
            )
            net_pay = Decimal("0.00")

        return net_pay

    def process_payroll_for_user(
        self,
        user_id: str,
        pay_period_start: date,
        pay_period_end: date,
        deductions: Optional[Decimal] = None
    ) -> PayrollRun:
        """
        Process payroll for a single user for a pay period.

        Args:
            user_id: User UUID
            pay_period_start: Start date of pay period
            pay_period_end: End date of pay period
            deductions: Optional deductions amount (default: 0.00)

        Returns:
            Created PayrollRun object

        Raises:
            PayrollProcessingError: If processing fails
            ValidationError: If validation fails
        """
        # Validate dates
        if pay_period_end < pay_period_start:
            raise ValidationError(
                "Pay period end date must be after start date",
                details={
                    "start": str(pay_period_start),
                    "end": str(pay_period_end)
                }
            )

        # Get user
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValidationError("User not found", details={"user_id": user_id})

        # Check for existing payroll runs - delete ALL DRAFT duplicates to consolidate
        existing_records = self.db.query(PayrollRun).filter(
            and_(
                PayrollRun.user_id == user_id,
                PayrollRun.pay_period_start == pay_period_start,
                PayrollRun.pay_period_end == pay_period_end
            )
        ).all()

        if existing_records:
            # Check for any non-DRAFT records (prevent overwriting approved/paid)
            non_draft = [r for r in existing_records if r.status != PayrollStatus.DRAFT]
            if non_draft:
                raise PayrollProcessingError(
                    f"Payroll run already exists with status '{non_draft[0].status.value}' for this period",
                    details={
                        "user_id": user_id,
                        "period": f"{pay_period_start} to {pay_period_end}",
                        "status": non_draft[0].status.value
                    }
                )

            # Delete ALL DRAFT records to ensure clean consolidation
            draft_records = [r for r in existing_records if r.status == PayrollStatus.DRAFT]
            if draft_records:
                logger.info(
                    f"Deleting {len(draft_records)} existing DRAFT payroll run(s) for consolidation: "
                    f"user_id={user_id}, period={pay_period_start} to {pay_period_end}"
                )
                for record in draft_records:
                    self.db.delete(record)
                self.db.flush()

        try:
            # Calculate total hours from attendance
            hours_summary = self.attendance_service.calculate_total_hours(
                user_id=user_id,
                start_date=pay_period_start,
                end_date=pay_period_end
            )

            regular_hours = hours_summary["regular_hours"]
            overtime_hours = hours_summary["overtime_hours"]

            # Calculate gross pay
            pay_breakdown = self.calculate_gross_pay(
                regular_hours=regular_hours,
                overtime_hours=overtime_hours,
                hourly_rate=user.hourly_rate
            )

            # Apply deductions
            if deductions is None:
                deductions = Decimal("0.00")
            else:
                deductions = Decimal(str(deductions))

            # Calculate net pay
            net_pay = self.calculate_net_pay(
                gross_pay=pay_breakdown["gross_pay"],
                deductions=deductions
            )

            # Create payroll run (atomic transaction)
            payroll_run = PayrollRun(
                user_id=user_id,
                pay_period_start=pay_period_start,
                pay_period_end=pay_period_end,
                base_salary=pay_breakdown["base_salary"],
                overtime_pay=pay_breakdown["overtime_pay"],
                deductions=deductions,
                net_pay=net_pay,
                status=PayrollStatus.DRAFT
            )

            self.db.add(payroll_run)
            self.db.commit()
            self.db.refresh(payroll_run)

            logger.info(
                f"Payroll processed: user_id={user_id}, "
                f"period={pay_period_start} to {pay_period_end}, "
                f"net_pay={net_pay}"
            )

            return payroll_run

        except Exception as e:
            self.db.rollback()
            logger.error(f"Payroll processing failed: {str(e)}")
            raise PayrollProcessingError(
                "Failed to process payroll",
                details={"error": str(e)}
            )

    def process_payroll_batch(
        self,
        pay_period_start: date,
        pay_period_end: date,
        user_ids: Optional[List[str]] = None,
        default_deductions: Optional[Decimal] = None
    ) -> List[PayrollRun]:
        """
        Process payroll for multiple users in batch.

        Automatically cleans up existing DRAFT records for the same period
        before processing to prevent duplicates.

        Args:
            pay_period_start: Start date of pay period
            pay_period_end: End date of pay period
            user_ids: Optional list of user IDs (default: all active users)
            default_deductions: Default deductions to apply (default: 0.00)

        Returns:
            List of created PayrollRun objects
        """
        if default_deductions is None:
            default_deductions = Decimal("0.00")

        # Get users to process
        if user_ids:
            users = self.db.query(User).filter(
                and_(User.id.in_(user_ids), User.is_active == True)
            ).all()
        else:
            users = self.db.query(User).filter(User.is_active == True).all()

        # PRE-CLEANUP: Delete existing DRAFT records for this exact period
        # This prevents duplicate accumulation when re-running batch processing
        existing_drafts = self.db.query(PayrollRun).filter(
            and_(
                PayrollRun.pay_period_start == pay_period_start,
                PayrollRun.pay_period_end == pay_period_end,
                PayrollRun.status == PayrollStatus.DRAFT
            )
        ).all()

        if existing_drafts:
            logger.info(
                f"Batch processing: Cleaning {len(existing_drafts)} existing DRAFT records "
                f"for period {pay_period_start} to {pay_period_end}"
            )
            for draft in existing_drafts:
                self.db.delete(draft)
            self.db.flush()

        payroll_runs = []
        failed_users = []

        for user in users:
            try:
                payroll_run = self.process_payroll_for_user(
                    user_id=user.id,
                    pay_period_start=pay_period_start,
                    pay_period_end=pay_period_end,
                    deductions=default_deductions
                )
                payroll_runs.append(payroll_run)
            except Exception as e:
                logger.error(f"Failed to process payroll for user {user.email}: {str(e)}")
                failed_users.append(user.email)

        if failed_users:
            logger.warning(
                f"Batch payroll processing completed with {len(failed_users)} failures: "
                f"{', '.join(failed_users)}"
            )
        else:
            logger.info(
                f"Batch payroll processing completed successfully: {len(payroll_runs)} runs"
            )

        return payroll_runs

    def approve_payroll(self, payroll_id: int) -> PayrollRun:
        """
        Approve a draft payroll run.

        Args:
            payroll_id: PayrollRun ID

        Returns:
            Updated PayrollRun object

        Raises:
            ValidationError: If payroll not found or cannot be approved
        """
        payroll = self.db.query(PayrollRun).filter(PayrollRun.id == payroll_id).first()

        if not payroll:
            raise ValidationError(
                "Payroll run not found",
                details={"payroll_id": payroll_id}
            )

        if payroll.status != PayrollStatus.DRAFT:
            raise ValidationError(
                "Only draft payroll runs can be approved",
                details={"current_status": payroll.status.value}
            )

        try:
            payroll.status = PayrollStatus.APPROVED
            self.db.commit()
            self.db.refresh(payroll)

            logger.info(f"Payroll approved: id={payroll_id}")
            return payroll

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to approve payroll: {str(e)}")
            raise PayrollProcessingError(
                "Failed to approve payroll",
                details={"error": str(e)}
            )

    def mark_as_paid(self, payroll_id: int) -> PayrollRun:
        """
        Mark an approved payroll run as paid.

        Args:
            payroll_id: PayrollRun ID

        Returns:
            Updated PayrollRun object

        Raises:
            ValidationError: If payroll not found or not approved
        """
        payroll = self.db.query(PayrollRun).filter(PayrollRun.id == payroll_id).first()

        if not payroll:
            raise ValidationError(
                "Payroll run not found",
                details={"payroll_id": payroll_id}
            )

        if payroll.status != PayrollStatus.APPROVED:
            raise ValidationError(
                "Only approved payroll runs can be marked as paid",
                details={"current_status": payroll.status.value}
            )

        try:
            payroll.status = PayrollStatus.PAID
            self.db.commit()
            self.db.refresh(payroll)

            logger.info(f"Payroll marked as paid: id={payroll_id}")
            return payroll

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to mark payroll as paid: {str(e)}")
            raise PayrollProcessingError(
                "Failed to mark payroll as paid",
                details={"error": str(e)}
            )

    def get_payroll_by_user(
        self,
        user_id: str,
        status: Optional[PayrollStatus] = None
    ) -> List[PayrollRun]:
        """
        Get payroll runs for a user.

        Args:
            user_id: User UUID
            status: Optional status filter

        Returns:
            List of PayrollRun objects
        """
        query = self.db.query(PayrollRun).filter(PayrollRun.user_id == user_id)

        if status:
            query = query.filter(PayrollRun.status == status)

        return query.order_by(PayrollRun.pay_period_end.desc()).all()

    def get_all_payroll_runs(
        self,
        status: Optional[PayrollStatus] = None
    ) -> List[PayrollRun]:
        """
        Get all payroll runs.

        Args:
            status: Optional status filter

        Returns:
            List of PayrollRun objects
        """
        query = self.db.query(PayrollRun)

        if status:
            query = query.filter(PayrollRun.status == status)

        return query.order_by(PayrollRun.pay_period_end.desc()).all()

    def cleanup_duplicate_payroll_runs(self) -> int:
        """
        Clean up duplicate DRAFT payroll runs, keeping only the latest record per user.

        For each user_id:
        - Keeps the most recent DRAFT record (highest ID)
        - Deletes all older DRAFT duplicates
        - Leaves APPROVED and PAID records untouched

        Returns:
            Number of duplicate records deleted

        Raises:
            PayrollProcessingError: If cleanup fails
        """
        try:
            # Get all DRAFT payroll runs grouped by user
            draft_runs = self.db.query(PayrollRun).filter(
                PayrollRun.status == PayrollStatus.DRAFT
            ).order_by(PayrollRun.user_id, PayrollRun.id.desc()).all()

            # Group by user_id
            user_drafts = {}
            for run in draft_runs:
                if run.user_id not in user_drafts:
                    user_drafts[run.user_id] = []
                user_drafts[run.user_id].append(run)

            deleted_count = 0
            for user_id, runs in user_drafts.items():
                if len(runs) > 1:
                    # Keep the first (most recent by ID), delete the rest
                    for old_run in runs[1:]:
                        logger.info(
                            f"Cleanup: Deleting duplicate DRAFT payroll run "
                            f"id={old_run.id}, user_id={user_id}, "
                            f"period={old_run.pay_period_start} to {old_run.pay_period_end}"
                        )
                        self.db.delete(old_run)
                        deleted_count += 1

            self.db.commit()
            logger.info(f"Cleanup completed: Deleted {deleted_count} duplicate DRAFT records")
            return deleted_count

        except Exception as e:
            self.db.rollback()
            logger.error(f"Cleanup failed: {str(e)}")
            raise PayrollProcessingError(
                "Failed to clean up duplicate payroll runs",
                details={"error": str(e)}
            )

    def get_latest_payroll_per_user(
        self,
        status: Optional[PayrollStatus] = None
    ) -> List[PayrollRun]:
        """
        Get the latest (most recent) payroll run for each user.

        Returns only ONE payroll run per user_id - the one with the most recent
        pay_period_end date, or highest ID if dates are identical.

        Args:
            status: Optional status filter

        Returns:
            List of PayrollRun objects (one per user)
        """
        query = self.db.query(PayrollRun)

        if status:
            query = query.filter(PayrollRun.status == status)

        all_runs = query.order_by(
            PayrollRun.user_id,
            PayrollRun.pay_period_end.desc(),
            PayrollRun.id.desc()
        ).all()

        # Keep only the first (latest) record per user
        seen_users = set()
        latest_runs = []

        for run in all_runs:
            if run.user_id not in seen_users:
                latest_runs.append(run)
                seen_users.add(run.user_id)

        return latest_runs

    def recalculate_draft_payroll(self, payroll_id: int) -> PayrollRun:
        """
        Recalculate an existing DRAFT payroll run with fresh attendance data.

        This pulls the latest attendance records (excluding IGNORED shifts)
        and updates the payroll calculations in-place.

        Args:
            payroll_id: PayrollRun ID to recalculate

        Returns:
            Updated PayrollRun object

        Raises:
            ValidationError: If payroll not found or not DRAFT status
            PayrollProcessingError: If recalculation fails
        """
        payroll = self.db.query(PayrollRun).filter(PayrollRun.id == payroll_id).first()

        if not payroll:
            raise ValidationError(
                "Payroll run not found",
                details={"payroll_id": payroll_id}
            )

        if payroll.status != PayrollStatus.DRAFT:
            raise ValidationError(
                "Only DRAFT payroll runs can be recalculated",
                details={"status": payroll.status.value}
            )

        try:
            # Recalculate hours from attendance (excludes IGNORED shifts)
            hours_summary = self.attendance_service.calculate_total_hours(
                user_id=payroll.user_id,
                start_date=payroll.pay_period_start,
                end_date=payroll.pay_period_end
            )

            regular_hours = hours_summary["regular_hours"]
            overtime_hours = hours_summary["overtime_hours"]

            # Get user for hourly rate
            user = self.db.query(User).filter(User.id == payroll.user_id).first()
            if not user:
                raise ValidationError("User not found", details={"user_id": payroll.user_id})

            # Recalculate gross pay
            pay_breakdown = self.calculate_gross_pay(
                regular_hours=regular_hours,
                overtime_hours=overtime_hours,
                hourly_rate=user.hourly_rate
            )

            # Update payroll record (keep existing deductions)
            payroll.base_salary = pay_breakdown["base_salary"]
            payroll.overtime_pay = pay_breakdown["overtime_pay"]

            # Recalculate net pay
            payroll.net_pay = self.calculate_net_pay(
                gross_pay=pay_breakdown["gross_pay"],
                deductions=payroll.deductions
            )

            self.db.commit()
            self.db.refresh(payroll)

            logger.info(
                f"Payroll recalculated: id={payroll_id}, "
                f"regular_hours={regular_hours}, overtime_hours={overtime_hours}, "
                f"net_pay={payroll.net_pay}"
            )

            return payroll

        except Exception as e:
            self.db.rollback()
            logger.error(f"Payroll recalculation failed: {str(e)}")
            raise PayrollProcessingError(
                "Failed to recalculate payroll",
                details={"error": str(e)}
            )

    def recalculate_drafts_for_user(self, user_id: str) -> List[PayrollRun]:
        """
        Recalculate all DRAFT payroll runs for a specific user.

        Useful when attendance records are approved/ignored and need to
        reflect in existing draft payrolls.

        Args:
            user_id: User UUID

        Returns:
            List of recalculated PayrollRun objects
        """
        draft_runs = self.db.query(PayrollRun).filter(
            and_(
                PayrollRun.user_id == user_id,
                PayrollRun.status == PayrollStatus.DRAFT
            )
        ).all()

        recalculated = []
        for draft in draft_runs:
            try:
                updated = self.recalculate_draft_payroll(draft.id)
                recalculated.append(updated)
            except Exception as e:
                logger.error(
                    f"Failed to recalculate draft {draft.id} for user {user_id}: {str(e)}"
                )

        logger.info(f"Recalculated {len(recalculated)} draft payroll(s) for user {user_id}")
        return recalculated

    def recalculate_all_drafts(self) -> int:
        """
        Recalculate ALL existing DRAFT payroll runs with fresh attendance data.

        This ensures all drafts reflect the current state of attendance records,
        including any IGNORED shifts that should now contribute 0.00 hours.

        Returns:
            Number of payroll runs successfully recalculated

        Raises:
            PayrollProcessingError: If operation fails
        """
        try:
            draft_runs = self.db.query(PayrollRun).filter(
                PayrollRun.status == PayrollStatus.DRAFT
            ).all()

            recalculated_count = 0
            failed_count = 0

            for draft in draft_runs:
                try:
                    self.recalculate_draft_payroll(draft.id)
                    recalculated_count += 1
                except Exception as e:
                    logger.error(f"Failed to recalculate draft {draft.id}: {str(e)}")
                    failed_count += 1

            logger.info(
                f"Recalculated {recalculated_count} draft payroll runs "
                f"({failed_count} failures)"
            )

            return recalculated_count

        except Exception as e:
            logger.error(f"Batch recalculation failed: {str(e)}")
            raise PayrollProcessingError(
                "Failed to recalculate all drafts",
                details={"error": str(e)}
            )
