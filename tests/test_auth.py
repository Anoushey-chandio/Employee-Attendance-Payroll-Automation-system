"""Tests for authentication service and RBAC.

Tests user registration, login, password hashing, and role-based authorization.
"""

import pytest
from sqlalchemy.orm import Session

from models.user import User, UserRole
from services.auth_service import AuthService
from utils.exceptions import AuthenticationError, AuthorizationError, ValidationError


class TestUserRegistration:
    """Test cases for user registration."""

    def test_register_user_success(self, test_db: Session):
        """Test successful user registration."""
        auth_service = AuthService(test_db)

        user = auth_service.register_user(
            email="newuser@test.com",
            password="password123",
            full_name="New User",
            role=UserRole.EMPLOYEE,
            hourly_rate=15.0
        )

        assert user.email == "newuser@test.com"
        assert user.full_name == "New User"
        assert user.role == UserRole.EMPLOYEE
        assert user.hourly_rate == 15.0
        assert user.is_active is True
        assert user.password_hash != "password123"  # Should be hashed

    def test_register_user_duplicate_email(self, test_db: Session, sample_user: User):
        """Test that duplicate email registration fails."""
        auth_service = AuthService(test_db)

        with pytest.raises(ValidationError) as exc_info:
            auth_service.register_user(
                email=sample_user.email,
                password="password123",
                full_name="Another User",
                role=UserRole.EMPLOYEE,
                hourly_rate=15.0
            )

        assert "already registered" in exc_info.value.message.lower()

    def test_register_user_invalid_email(self, test_db: Session):
        """Test registration with invalid email format."""
        auth_service = AuthService(test_db)

        with pytest.raises(ValidationError) as exc_info:
            auth_service.register_user(
                email="invalid-email",
                password="password123",
                full_name="Test User",
                role=UserRole.EMPLOYEE,
                hourly_rate=15.0
            )

        assert "invalid email" in exc_info.value.message.lower()

    def test_register_user_short_password(self, test_db: Session):
        """Test registration with password too short."""
        auth_service = AuthService(test_db)

        with pytest.raises(ValidationError) as exc_info:
            auth_service.register_user(
                email="test@test.com",
                password="123",
                full_name="Test User",
                role=UserRole.EMPLOYEE,
                hourly_rate=15.0
            )

        assert "at least 6 characters" in exc_info.value.message.lower()

    def test_email_case_insensitive(self, test_db: Session):
        """Test that email is stored in lowercase."""
        auth_service = AuthService(test_db)

        user = auth_service.register_user(
            email="TestUser@TEST.COM",
            password="password123",
            full_name="Test User",
            role=UserRole.EMPLOYEE,
            hourly_rate=15.0
        )

        assert user.email == "testuser@test.com"


class TestUserAuthentication:
    """Test cases for user authentication."""

    def test_authenticate_user_success(self, test_db: Session, sample_user: User):
        """Test successful authentication."""
        auth_service = AuthService(test_db)

        authenticated_user = auth_service.authenticate_user(
            email="employee@test.com",
            password="password123"
        )

        assert authenticated_user.id == sample_user.id
        assert authenticated_user.email == sample_user.email

    def test_authenticate_invalid_password(self, test_db: Session, sample_user: User):
        """Test authentication with wrong password."""
        auth_service = AuthService(test_db)

        with pytest.raises(AuthenticationError) as exc_info:
            auth_service.authenticate_user(
                email="employee@test.com",
                password="wrongpassword"
            )

        assert "invalid" in exc_info.value.message.lower()

    def test_authenticate_nonexistent_user(self, test_db: Session):
        """Test authentication with non-existent email."""
        auth_service = AuthService(test_db)

        with pytest.raises(AuthenticationError) as exc_info:
            auth_service.authenticate_user(
                email="nonexistent@test.com",
                password="password123"
            )

        assert "invalid" in exc_info.value.message.lower()

    def test_authenticate_inactive_user(self, test_db: Session, sample_user: User):
        """Test authentication fails for inactive users."""
        auth_service = AuthService(test_db)

        # Deactivate user
        sample_user.is_active = False
        test_db.commit()

        with pytest.raises(AuthenticationError) as exc_info:
            auth_service.authenticate_user(
                email="employee@test.com",
                password="password123"
            )

        assert "disabled" in exc_info.value.message.lower()

    def test_password_hashing_verification(self, test_db: Session):
        """Test that password hashing and verification works correctly."""
        auth_service = AuthService(test_db)

        plain_password = "mySecurePassword123"
        hashed = auth_service.hash_password(plain_password)

        # Hash should be different from plaintext
        assert hashed != plain_password
        assert len(hashed) > 20  # Bcrypt hashes are long

        # Verification should succeed
        assert auth_service.verify_password(plain_password, hashed) is True

        # Wrong password should fail
        assert auth_service.verify_password("wrongpassword", hashed) is False


class TestRoleBasedAccessControl:
    """Test cases for RBAC validation."""

    def test_employee_role_hierarchy(self, test_db: Session, sample_user: User):
        """Test employee role has lowest privilege."""
        auth_service = AuthService(test_db)

        # Employee should have employee access
        assert sample_user.has_role(UserRole.EMPLOYEE) is True

        # Employee should NOT have HR access
        assert sample_user.has_role(UserRole.HR) is False

        # Employee should NOT have admin access
        assert sample_user.has_role(UserRole.ADMIN) is False

    def test_admin_role_hierarchy(self, test_db: Session, sample_admin: User):
        """Test admin role has highest privilege."""
        auth_service = AuthService(test_db)

        # Admin should have all access levels
        assert sample_admin.has_role(UserRole.EMPLOYEE) is True
        assert sample_admin.has_role(UserRole.HR) is True
        assert sample_admin.has_role(UserRole.ADMIN) is True

    def test_validate_role_success(self, test_db: Session, sample_admin: User):
        """Test role validation passes for authorized user."""
        auth_service = AuthService(test_db)

        # Should not raise exception
        auth_service.validate_role(sample_admin, UserRole.ADMIN)

    def test_validate_role_failure(self, test_db: Session, sample_user: User):
        """Test role validation fails for unauthorized user."""
        auth_service = AuthService(test_db)

        with pytest.raises(AuthorizationError) as exc_info:
            auth_service.validate_role(sample_user, UserRole.ADMIN)

        assert "access denied" in exc_info.value.message.lower()


class TestUserManagement:
    """Test cases for user management operations."""

    def test_get_user_by_id(self, test_db: Session, sample_user: User):
        """Test retrieving user by ID."""
        auth_service = AuthService(test_db)

        user = auth_service.get_user_by_id(sample_user.id)

        assert user is not None
        assert user.id == sample_user.id
        assert user.email == sample_user.email

    def test_get_user_by_id_not_found(self, test_db: Session):
        """Test retrieving non-existent user returns None."""
        auth_service = AuthService(test_db)

        user = auth_service.get_user_by_id("nonexistent-id")

        assert user is None

    def test_get_user_by_email(self, test_db: Session, sample_user: User):
        """Test retrieving user by email."""
        auth_service = AuthService(test_db)

        user = auth_service.get_user_by_email("employee@test.com")

        assert user is not None
        assert user.email == sample_user.email

    def test_update_hourly_rate(self, test_db: Session, sample_user: User):
        """Test updating user hourly rate."""
        auth_service = AuthService(test_db)

        updated_user = auth_service.update_hourly_rate(sample_user.id, 25.0)

        assert updated_user.hourly_rate == 25.0

    def test_update_hourly_rate_negative(self, test_db: Session, sample_user: User):
        """Test that negative hourly rate is rejected."""
        auth_service = AuthService(test_db)

        with pytest.raises(ValidationError) as exc_info:
            auth_service.update_hourly_rate(sample_user.id, -10.0)

        assert "negative" in exc_info.value.message.lower()

    def test_deactivate_user(self, test_db: Session, sample_user: User):
        """Test deactivating a user."""
        auth_service = AuthService(test_db)

        assert sample_user.is_active is True

        deactivated_user = auth_service.deactivate_user(sample_user.id)

        assert deactivated_user.is_active is False

    def test_get_all_users(self, test_db: Session, sample_user: User, sample_admin: User):
        """Test retrieving all active users."""
        auth_service = AuthService(test_db)

        users = auth_service.get_all_users(include_inactive=False)

        assert len(users) == 2
        assert all(user.is_active for user in users)

    def test_get_all_users_include_inactive(self, test_db: Session, sample_user: User):
        """Test retrieving all users including inactive."""
        auth_service = AuthService(test_db)

        # Deactivate one user
        auth_service.deactivate_user(sample_user.id)

        users = auth_service.get_all_users(include_inactive=True)

        assert len(users) >= 1
        assert any(not user.is_active for user in users)
