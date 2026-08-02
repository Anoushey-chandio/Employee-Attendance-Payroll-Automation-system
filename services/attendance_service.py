"""Attendance service for time tracking and shift management.

Handles check-in/out operations, overtime calculation, and anomaly detection.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import pytz
from sqlalchemy import and_
from sqlalchemy.orm import Session

from config.settings import get_settings
from models.attendance import Attendance, AttendanceStatus
from models.user import User
from utils.exceptions import AttendanceError, ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()


class AttendanceService:
    """Attendance management and time tracking service."""

    def __init__(self, db: Session) -> None:
        """
        Initialize attendance service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def check_in(self, user_id: str, check_in_time: Optional[datetime] = None) -> Attendance:
        """
        Create a check-in record for an employee.

        Args:
            user_id: User UUID
            check_in_time: Check-in timestamp (default: current UTC time)

        Returns:
            Created Attendance object

        Raises:
            AttendanceError: If double check-in detected or validation fails
        """
        if check_in_time is None:
            check_in_time = datetime.now(pytz.UTC)
        elif check_in_time.tzinfo is None:
            # Ensure timezone-aware
            check_in_time = pytz.UTC.localize(check_in_time)

        work_date = check_in_time.date()

        # Check for existing attendance on the same date
        existing = self.db.query(Attendance).filter(
            and_(
                Attendance.user_id == user_id,
                Attendance.date == work_date
            )
        ).first()

        if existing:
            logger.warning(
                f"Double check-in attempt: user_id={user_id}, date={work_date}"
            )
            raise AttendanceError(
                "Already checked in for today",
                details={"user_id": user_id, "date": str(work_date)}
            )

        try:
            # Create new attendance record
            attendance = Attendance(
                user_id=user_id,
                date=work_date,
                check_in=check_in_time,
                check_out=None,
                regular_hours=Decimal("0.00"),
                overtime_hours=Decimal("0.00"),
                status=AttendanceStatus.PRESENT
            )

            self.db.add(attendance)
            self.db.commit()
            self.db.refresh(attendance)

            logger.info(f"Check-in successful: user_id={user_id}, time={check_in_time}")
            return attendance

        except Exception as e:
            self.db.rollback()
            logger.error(f"Check-in failed: {str(e)}")
            raise AttendanceError(
                "Failed to create check-in record",
                details={"error": str(e)}
            )

    def check_out(
        self,
        user_id: str,
        check_out_time: Optional[datetime] = None
    ) -> Attendance:
        """
        Process check-out and calculate hours worked.

        Args:
            user_id: User UUID
            check_out_time: Check-out timestamp (default: current UTC time)

        Returns:
            Updated Attendance object with calculated hours

        Raises:
            AttendanceError: If no open shift found or validation fails
        """
        if check_out_time is None:
            check_out_time = datetime.now(pytz.UTC)
        elif check_out_time.tzinfo is None:
            # Ensure timezone-aware
            check_out_time = pytz.UTC.localize(check_out_time)

        work_date = check_out_time.date()

        # Find open shift (same date, no check_out)
        attendance = self.db.query(Attendance).filter(
            and_(
                Attendance.user_id == user_id,
                Attendance.date == work_date,
                Attendance.check_out.is_(None)
            )
        ).first()

        if not attendance:
            logger.warning(f"Check-out without check-in: user_id={user_id}, date={work_date}")
            raise AttendanceError(
                "No open shift found for today",
                details={"user_id": user_id, "date": str(work_date)}
            )

        # Ensure check_in is timezone-aware (SQLite may return naive datetime)
        check_in = attendance.check_in
        if check_in.tzinfo is None:
            check_in = pytz.UTC.localize(check_in)

        # Validate check_out is after check_in
        if check_out_time <= check_in:
            raise AttendanceError(
                "Check-out time must be after check-in time",
                details={
                    "check_in": str(check_in),
                    "check_out": str(check_out_time)
                }
            )

        try:
            # Calculate total duration in hours
            duration_seconds = (check_out_time - check_in).total_seconds()
            total_hours = Decimal(str(duration_seconds / 3600)).quantize(Decimal("0.01"))

            # Apply business rules for regular and overtime hours
            regular_cap = Decimal(str(settings.regular_hours_cap))
            overtime_cap = Decimal(str(settings.overtime_hours_cap))

            if total_hours <= regular_cap:
                # All hours are regular
                attendance.regular_hours = total_hours
                attendance.overtime_hours = Decimal("0.00")
                attendance.status = AttendanceStatus.COMPLETED
            elif total_hours <= (regular_cap + overtime_cap):
                # Split into regular and overtime
                attendance.regular_hours = regular_cap
                attendance.overtime_hours = total_hours - regular_cap
                attendance.status = AttendanceStatus.COMPLETED
            else:
                # Exceeds overtime cap - flag for review
                attendance.regular_hours = regular_cap
                attendance.overtime_hours = overtime_cap
                attendance.status = AttendanceStatus.FLAGGED
                logger.warning(
                    f"Attendance flagged: Excessive hours detected "
                    f"(user_id={user_id}, total_hours={total_hours})"
                )

            attendance.check_out = check_out_time
            self.db.commit()
            self.db.refresh(attendance)

            logger.info(
                f"Check-out successful: user_id={user_id}, "
                f"regular={attendance.regular_hours}, overtime={attendance.overtime_hours}"
            )
            return attendance

        except Exception as e:
            self.db.rollback()
            logger.error(f"Check-out failed: {str(e)}")
            raise AttendanceError(
                "Failed to process check-out",
                details={"error": str(e)}
            )

    def get_attendance_by_user(
        self,
        user_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Attendance]:
        """
        Get attendance records for a user within a date range.

        Args:
            user_id: User UUID
            start_date: Start date filter (optional)
            end_date: End date filter (optional)

        Returns:
            List of Attendance objects
        """
        query = self.db.query(Attendance).filter(Attendance.user_id == user_id)

        if start_date:
            query = query.filter(Attendance.date >= start_date)
        if end_date:
            query = query.filter(Attendance.date <= end_date)

        return query.order_by(Attendance.date.desc()).all()

    def get_open_shifts(self) -> List[Attendance]:
        """
        Get all open shifts (no check-out).

        Returns:
            List of Attendance objects with no check_out
        """
        return self.db.query(Attendance).filter(
            Attendance.check_out.is_(None)
        ).all()

    def get_flagged_attendance(self) -> List[Attendance]:
        """
        Get all flagged attendance records requiring review.

        Returns:
            List of flagged Attendance objects
        """
        return self.db.query(Attendance).filter(
            Attendance.status == AttendanceStatus.FLAGGED
        ).order_by(Attendance.date.desc()).all()

    def auto_flag_unclosed_shifts(self) -> int:
        """
        Auto-flag attendance records left open past midnight UTC.

        Returns:
            Number of records flagged

        Raises:
            AttendanceError: If operation fails
        """
        try:
            current_date = datetime.now(pytz.UTC).date()

            # Find open shifts from previous dates
            unclosed_shifts = self.db.query(Attendance).filter(
                and_(
                    Attendance.check_out.is_(None),
                    Attendance.date < current_date
                )
            ).all()

            flagged_count = 0
            for shift in unclosed_shifts:
                shift.status = AttendanceStatus.FLAGGED
                shift.regular_hours = Decimal("0.00")
                shift.overtime_hours = Decimal("0.00")
                flagged_count += 1
                logger.warning(
                    f"Auto-flagged unclosed shift: "
                    f"user_id={shift.user_id}, date={shift.date}"
                )

            self.db.commit()
            logger.info(f"Auto-flagged {flagged_count} unclosed shifts")
            return flagged_count

        except Exception as e:
            self.db.rollback()
            logger.error(f"Auto-flag operation failed: {str(e)}")
            raise AttendanceError(
                "Failed to auto-flag unclosed shifts",
                details={"error": str(e)}
            )

    def calculate_total_hours(
        self,
        user_id: str,
        start_date: date,
        end_date: date
    ) -> dict[str, Decimal]:
        """
        Calculate total regular and overtime hours for a user in a date range.

        Args:
            user_id: User UUID
            start_date: Period start date
            end_date: Period end date

        Returns:
            Dictionary with 'regular_hours' and 'overtime_hours' totals
        """
        attendance_records = self.get_attendance_by_user(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        # Only include completed and present shifts (not flagged, not absent)
        valid_records = [
            r for r in attendance_records
            if r.status in [AttendanceStatus.PRESENT, AttendanceStatus.COMPLETED]
            and r.check_out is not None
        ]

        total_regular = sum(
            (r.regular_hours for r in valid_records),
            start=Decimal("0.00")
        )
        total_overtime = sum(
            (r.overtime_hours for r in valid_records),
            start=Decimal("0.00")
        )

        return {
            "regular_hours": total_regular,
            "overtime_hours": total_overtime
        }

    def approve_flagged_attendance(self, attendance_id: int) -> Attendance:
        """
        Approve a flagged attendance record and change status to present.

        Args:
            attendance_id: Attendance record ID

        Returns:
            Updated Attendance object

        Raises:
            ValidationError: If attendance not found or not flagged
        """
        attendance = self.db.query(Attendance).filter(
            Attendance.id == attendance_id
        ).first()

        if not attendance:
            raise ValidationError(
                "Attendance record not found",
                details={"attendance_id": attendance_id}
            )

        if attendance.status != AttendanceStatus.FLAGGED:
            raise ValidationError(
                "Attendance record is not flagged",
                details={"status": attendance.status.value}
            )

        try:
            attendance.status = AttendanceStatus.PRESENT
            self.db.commit()
            self.db.refresh(attendance)

            logger.info(f"Flagged attendance approved: id={attendance_id}")
            return attendance

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to approve attendance: {str(e)}")
            raise AttendanceError(
                "Failed to approve attendance record",
                details={"error": str(e)}
            )
