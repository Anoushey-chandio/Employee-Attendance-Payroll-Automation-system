"""Authentication service for user management and RBAC.

Handles user registration, login, password hashing, and role-based authorization.
"""

from typing import Optional

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from models.user import User, UserRole
from utils.exceptions import AuthenticationError, AuthorizationError, ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication and authorization service."""

    def __init__(self, db: Session) -> None:
        """
        Initialize authentication service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a plaintext password using bcrypt.

        Args:
            password: Plaintext password

        Returns:
            Hashed password string
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plaintext password against a hash.

        Args:
            plain_password: Plaintext password to verify
            hashed_password: Stored password hash

        Returns:
            True if password matches, False otherwise
        """
        return pwd_context.verify(plain_password, hashed_password)

    def register_user(
        self,
        email: str,
        password: str,
        full_name: str,
        role: UserRole = UserRole.EMPLOYEE,
        hourly_rate: float = 0.0
    ) -> User:
        """
        Register a new user account.

        Args:
            email: User email (must be unique)
            password: Plaintext password
            full_name: Employee full name
            role: User role (default: EMPLOYEE)
            hourly_rate: Hourly pay rate (default: 0.0)

        Returns:
            Created User object

        Raises:
            ValidationError: If email already exists or validation fails
        """
        # Validate email format
        if not email or "@" not in email:
            raise ValidationError("Invalid email format")

        # Validate password strength
        if not password or len(password) < 6:
            raise ValidationError("Password must be at least 6 characters")

        # Check if email already exists
        existing_user = self.db.query(User).filter(User.email == email).first()
        if existing_user:
            raise ValidationError(
                "Email already registered",
                details={"email": email}
            )

        # Create new user
        try:
            from decimal import Decimal

            new_user = User(
                email=email.lower().strip(),
                password_hash=self.hash_password(password),
                full_name=full_name.strip(),
                role=role,
                hourly_rate=Decimal(str(hourly_rate)),
                is_active=True
            )

            self.db.add(new_user)
            self.db.commit()
            self.db.refresh(new_user)

            logger.info(f"User registered successfully: {email}")
            return new_user

        except Exception as e:
            self.db.rollback()
            logger.error(f"User registration failed: {str(e)}")
            raise ValidationError(
                "Failed to register user",
                details={"error": str(e)}
            )

    def authenticate_user(self, email: str, password: str) -> User:
        """
        Authenticate user with email and password.

        Args:
            email: User email
            password: Plaintext password

        Returns:
            Authenticated User object

        Raises:
            AuthenticationError: If credentials are invalid
        """
        user = self.db.query(User).filter(User.email == email.lower().strip()).first()

        if not user:
            logger.warning(f"Login attempt with non-existent email: {email}")
            raise AuthenticationError("Invalid email or password")

        if not self.verify_password(password, user.password_hash):
            logger.warning(f"Failed login attempt for user: {email}")
            raise AuthenticationError("Invalid email or password")

        if not user.is_active:
            logger.warning(f"Login attempt for inactive account: {email}")
            raise AuthenticationError("Account is disabled")

        logger.info(f"User authenticated successfully: {email}")
        return user

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            User object or None if not found
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email.

        Args:
            email: User email

        Returns:
            User object or None if not found
        """
        return self.db.query(User).filter(User.email == email.lower().strip()).first()

    @staticmethod
    def validate_role(user: User, required_role: UserRole) -> None:
        """
        Validate that user has required role.

        Args:
            user: User object to check
            required_role: Minimum required role

        Raises:
            AuthorizationError: If user lacks required role
        """
        if not user.has_role(required_role):
            logger.warning(
                f"Authorization denied: User {user.email} "
                f"(role={user.role.value}) attempted to access "
                f"{required_role.value} resource"
            )
            raise AuthorizationError(
                f"Access denied. Required role: {required_role.value}",
                details={"user_role": user.role.value, "required_role": required_role.value}
            )

    def update_hourly_rate(self, user_id: str, new_rate: float) -> User:
        """
        Update user's hourly rate.

        Args:
            user_id: User UUID
            new_rate: New hourly rate

        Returns:
            Updated User object

        Raises:
            ValidationError: If user not found or rate invalid
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found", details={"user_id": user_id})

        if new_rate < 0:
            raise ValidationError("Hourly rate cannot be negative")

        try:
            from decimal import Decimal

            user.hourly_rate = Decimal(str(new_rate))
            self.db.commit()
            self.db.refresh(user)

            logger.info(f"Updated hourly rate for user {user.email}: {new_rate} PKR")
            return user

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to update hourly rate: {str(e)}")
            raise ValidationError(
                "Failed to update hourly rate",
                details={"error": str(e)}
            )

    def deactivate_user(self, user_id: str) -> User:
        """
        Deactivate user account.

        Args:
            user_id: User UUID

        Returns:
            Updated User object

        Raises:
            ValidationError: If user not found
        """
        user = self.get_user_by_id(user_id)
        if not user:
            raise ValidationError("User not found", details={"user_id": user_id})

        try:
            user.is_active = False
            self.db.commit()
            self.db.refresh(user)

            logger.info(f"User deactivated: {user.email}")
            return user

        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to deactivate user: {str(e)}")
            raise ValidationError(
                "Failed to deactivate user",
                details={"error": str(e)}
            )

    def get_all_users(self, include_inactive: bool = False) -> list[User]:
        """
        Get all users.

        Args:
            include_inactive: Include inactive users (default: False)

        Returns:
            List of User objects
        """
        query = self.db.query(User)
        if not include_inactive:
            query = query.filter(User.is_active == True)

        return query.all()
