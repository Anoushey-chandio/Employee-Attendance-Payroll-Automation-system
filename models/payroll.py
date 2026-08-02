"""Payroll model for salary calculation and payment processing.

Defines the payroll_runs table for tracking pay periods and calculated compensation.
"""

from datetime import date
from decimal import Decimal
from enum import Enum as PyEnum

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class PayrollStatus(PyEnum):
    """Payroll processing status enumeration."""

    DRAFT = "draft"
    APPROVED = "approved"
    PAID = "paid"


class PayrollRun(Base):
    """Payroll run model for tracking calculated employee compensation."""

    __tablename__ = "payroll_runs"

    # Primary Key
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="Payroll record ID"
    )

    # Foreign Key
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Employee reference"
    )

    # Pay Period
    pay_period_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Start date of pay cycle"
    )

    pay_period_end: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="End date of pay cycle"
    )

    # Compensation Breakdown
    base_salary: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Calculated base earnings from regular hours"
    )

    overtime_pay: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Overtime earnings (1.5x rate)"
    )

    deductions: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Tax and policy deductions"
    )

    net_pay: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Total payout after deductions"
    )

    # Processing Status
    status: Mapped[PayrollStatus] = mapped_column(
        Enum(PayrollStatus, native_enum=False, length=20),
        nullable=False,
        default=PayrollStatus.DRAFT,
        comment="Payroll processing state"
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="payroll_runs",
        lazy="joined"
    )

    def __repr__(self) -> str:
        return (
            f"<PayrollRun(id={self.id}, user_id={self.user_id}, "
            f"period={self.pay_period_start} to {self.pay_period_end}, "
            f"status={self.status.value})>"
        )

    @property
    def gross_pay(self) -> Decimal:
        """
        Calculate gross pay (base + overtime).

        Returns:
            Gross pay as Decimal
        """
        return self.base_salary + self.overtime_pay

    @property
    def period_duration_days(self) -> int:
        """
        Calculate the number of days in the pay period.

        Returns:
            Number of days in period
        """
        return (self.pay_period_end - self.pay_period_start).days + 1

    def is_approved(self) -> bool:
        """
        Check if payroll is approved or paid.

        Returns:
            True if status is approved or paid
        """
        return self.status in [PayrollStatus.APPROVED, PayrollStatus.PAID]

    def can_modify(self) -> bool:
        """
        Check if payroll can be modified.

        Returns:
            True if status is draft (not yet approved/paid)
        """
        return self.status == PayrollStatus.DRAFT
