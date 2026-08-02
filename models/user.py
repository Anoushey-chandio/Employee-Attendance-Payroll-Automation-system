"""User model for authentication and employee management.

Defines the users table with RBAC roles and employee profile data.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import List

from sqlalchemy import Boolean, DateTime, Enum, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class UserRole(PyEnum):
    """User role enumeration for RBAC."""

    ADMIN = "admin"
    HR = "hr"
    EMPLOYEE = "employee"


class User(Base):
    """User model for authentication and employee profiles."""

    __tablename__ = "users"

    # Primary Key
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="Unique user identifier (UUID)"
    )

    # Authentication Fields
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="User login email"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Bcrypt password hash"
    )

    # Profile Information
    full_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Employee legal full name"
    )

    # RBAC Role
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20),
        nullable=False,
        default=UserRole.EMPLOYEE,
        comment="System access role"
    )

    # Compensation
    hourly_rate: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        comment="Base hourly pay rate"
    )

    # Account Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Account activation status"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Account creation timestamp (UTC)"
    )

    # Relationships
    attendance_records: Mapped[List["Attendance"]] = relationship(
        "Attendance",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )

    payroll_runs: Mapped[List["PayrollRun"]] = relationship(
        "PayrollRun",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role.value})>"

    def has_role(self, required_role: UserRole) -> bool:
        """
        Check if user has the required role.

        Args:
            required_role: Required role to check

        Returns:
            True if user has the required role or higher privilege
        """
        role_hierarchy = {
            UserRole.EMPLOYEE: 1,
            UserRole.HR: 2,
            UserRole.ADMIN: 3
        }
        return role_hierarchy[self.role] >= role_hierarchy[required_role]
