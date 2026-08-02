"""Attendance model for employee time tracking.

Defines the attendance table for check-in/out, hours tracking, and status management.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class AttendanceStatus(PyEnum):
    """Attendance record status enumeration."""

    PRESENT = "present"
    COMPLETED = "completed"
    ABSENT = "absent"
    FLAGGED = "flagged"


class Attendance(Base):
    """Attendance model for tracking employee check-in/out and hours."""

    __tablename__ = "attendance"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Attendance record ID"
    )

    # Foreign Key
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee reference"
    )

    # Date Tracking
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Work date (date only, no time)"
    )

    # Time Tracking
    check_in: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Clock-in timestamp (UTC)"
    )

    check_out: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Clock-out timestamp (UTC), nullable for open shifts"
    )

    # Hours Calculation
    regular_hours: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Standard work hours (capped at 8.00)"
    )

    overtime_hours: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Overtime hours worked (capped at 4.00)"
    )

    # Status
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, native_enum=False, length=20),
        nullable=False,
        default=AttendanceStatus.PRESENT,
        comment="Daily attendance status"
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="attendance_records",
        lazy="joined"
    )

    def __repr__(self) -> str:
        return (
            f"<Attendance(id={self.id}, user_id={self.user_id}, "
            f"date={self.date}, status={self.status.value})>"
        )

    @property
    def total_hours(self) -> Decimal:
        """
        Calculate total hours worked (regular + overtime).

        Returns:
            Total hours as Decimal
        """
        return self.regular_hours + self.overtime_hours

    @property
    def is_open_shift(self) -> bool:
        """
        Check if shift is still open (no check-out).

        Returns:
            True if check_out is None
        """
        return self.check_out is None

    def calculate_duration_hours(self) -> Decimal | None:
        """
        Calculate duration between check_in and check_out in hours.

        Returns:
            Duration in hours as Decimal, or None if shift is open
        """
        if self.check_out is None:
            return None

        duration_seconds = (self.check_out - self.check_in).total_seconds()
        duration_hours = Decimal(str(duration_seconds / 3600))

        # Round to 2 decimal places
        return duration_hours.quantize(Decimal("0.01"))
