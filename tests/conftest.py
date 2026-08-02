"""Pytest configuration and fixtures for the test suite.

Provides test database setup, mock clients, and reusable fixtures.
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings
from models.base import Base
from models.user import User, UserRole
from models.attendance import Attendance, AttendanceStatus
from models.payroll import PayrollRun, PayrollStatus
from services.auth_service import AuthService


@pytest.fixture(scope="function")
def test_settings() -> Settings:
    """
    Create test settings with SQLite in-memory database.

    Returns:
        Test Settings instance
    """
    settings = Settings(
        database_url="sqlite:///:memory:",
        supabase_url="http://test.supabase.co",
        supabase_key="test_key",
        secret_key="test_secret_key",
        app_env="development",
        use_local_sqlite=True,
        regular_hours_cap=8.0,
        overtime_hours_cap=4.0,
        overtime_multiplier=1.5
    )
    return settings


@pytest.fixture(scope="function")
def test_engine(test_settings):
    """
    Create test database engine.

    Args:
        test_settings: Test settings fixture

    Returns:
        SQLAlchemy engine
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    return engine


@pytest.fixture(scope="function")
def test_db(test_engine) -> Session:
    """
    Create test database session with tables.

    Args:
        test_engine: Test database engine

    Yields:
        SQLAlchemy session for testing
    """
    # Create all tables
    Base.metadata.create_all(bind=test_engine)

    # Create session factory
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine
    )

    # Create session
    db = TestSessionLocal()

    try:
        yield db
    finally:
        db.close()
        # Drop all tables after test
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def sample_user(test_db: Session) -> User:
    """
    Create a sample employee user for testing.

    Args:
        test_db: Test database session

    Returns:
        Sample User object
    """
    auth_service = AuthService(test_db)
    user = auth_service.register_user(
        email="employee@test.com",
        password="password123",
        full_name="John Doe",
        role=UserRole.EMPLOYEE,
        hourly_rate=20.0
    )
    return user


@pytest.fixture
def sample_admin(test_db: Session) -> User:
    """
    Create a sample admin user for testing.

    Args:
        test_db: Test database session

    Returns:
        Sample admin User object
    """
    auth_service = AuthService(test_db)
    admin = auth_service.register_user(
        email="admin@test.com",
        password="admin123",
        full_name="Admin User",
        role=UserRole.ADMIN,
        hourly_rate=0.0
    )
    return admin


@pytest.fixture
def sample_attendance(test_db: Session, sample_user: User) -> Attendance:
    """
    Create a sample attendance record for testing.

    Args:
        test_db: Test database session
        sample_user: Sample user fixture

    Returns:
        Sample Attendance object
    """
    import pytz

    attendance = Attendance(
        user_id=sample_user.id,
        date=date.today(),
        check_in=datetime.now(pytz.UTC),
        check_out=None,
        regular_hours=Decimal("0.00"),
        overtime_hours=Decimal("0.00"),
        status=AttendanceStatus.PRESENT
    )

    test_db.add(attendance)
    test_db.commit()
    test_db.refresh(attendance)

    return attendance


@pytest.fixture
def sample_payroll(test_db: Session, sample_user: User) -> PayrollRun:
    """
    Create a sample payroll run for testing.

    Args:
        test_db: Test database session
        sample_user: Sample user fixture

    Returns:
        Sample PayrollRun object
    """
    payroll = PayrollRun(
        user_id=sample_user.id,
        pay_period_start=date(2024, 1, 1),
        pay_period_end=date(2024, 1, 31),
        base_salary=Decimal("3200.00"),
        overtime_pay=Decimal("450.00"),
        deductions=Decimal("650.00"),
        net_pay=Decimal("3000.00"),
        status=PayrollStatus.DRAFT
    )

    test_db.add(payroll)
    test_db.commit()
    test_db.refresh(payroll)

    return payroll


@pytest.fixture
def mock_datetime(monkeypatch):
    """
    Mock datetime for predictable testing.

    Args:
        monkeypatch: Pytest monkeypatch fixture

    Returns:
        Mock datetime class
    """
    import pytz
    from datetime import datetime as dt

    class MockDatetime:
        @staticmethod
        def now(tz=None):
            return dt(2024, 1, 15, 10, 0, 0, tzinfo=pytz.UTC)

        @staticmethod
        def today():
            return date(2024, 1, 15)

    return MockDatetime
