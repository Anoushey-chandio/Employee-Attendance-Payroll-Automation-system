"""Centralized logging setup for the Enterprise Payroll System.

Provides structured logging with appropriate levels and formatting.
"""

import logging
import sys
from typing import Optional


def get_logger(
    name: str,
    level: int = logging.INFO,
    log_format: Optional[str] = None
) -> logging.Logger:
    """
    Get or create a configured logger instance.

    Args:
        name: Logger name (typically __name__ from calling module)
        level: Logging level (default: INFO)
        log_format: Custom format string (optional)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if no handlers exist (prevent duplicate handlers)
    if not logger.handlers:
        logger.setLevel(level)

        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)

        # Set format
        if log_format is None:
            log_format = (
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )

        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger


def configure_root_logger(level: int = logging.INFO) -> None:
    """
    Configure the root logger for the entire application.

    Args:
        level: Logging level to apply globally
    """
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )
