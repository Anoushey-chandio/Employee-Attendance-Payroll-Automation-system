"""Custom exception hierarchy for the Enterprise Payroll System.

All exceptions inherit from PayrollSystemError for centralized error handling.
"""


class PayrollSystemError(Exception):
    """Base exception for all payroll system errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class DatabaseError(PayrollSystemError):
    """Raised when database operations fail."""

    pass


class AuthenticationError(PayrollSystemError):
    """Raised when user authentication fails."""

    pass


class AuthorizationError(PayrollSystemError):
    """Raised when user lacks required permissions."""

    pass


class ValidationError(PayrollSystemError):
    """Raised when input validation fails."""

    pass


class AttendanceError(PayrollSystemError):
    """Raised when attendance operations encounter business rule violations."""

    pass


class PayrollProcessingError(PayrollSystemError):
    """Raised when payroll calculation or processing fails."""

    pass
