"""Main entrypoint for the Enterprise Payroll & Overtime Auditor System.

This module initializes the Streamlit application, manages session state,
and routes users to appropriate dashboards based on RBAC roles.
"""

import streamlit as st
from sqlalchemy.orm import Session

from config.database import SessionLocal, check_db_connection, init_db
from config.settings import get_settings
from models.user import UserRole
from utils.logger import configure_root_logger, get_logger
from views.admin_dashboard import render_admin_dashboard
from views.auth_view import render_auth_view, render_logout_button
from views.employee_dashboard import render_employee_dashboard

# Configure logging
configure_root_logger()
logger = get_logger(__name__)
settings = get_settings()

# Page configuration
st.set_page_config(
    page_title="Enterprise Payroll System",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)


def initialize_session_state() -> None:
    """
    Initialize session state variables if they don't exist.
    Restores session from query parameters if available.
    """
    # Check if we have a session token in query params (for persistence across refresh)
    query_params = st.query_params
    session_user_id = query_params.get("sid", None)

    # If we have a session token but no active session, restore it
    if session_user_id and not st.session_state.get("authenticated", False):
        # Restore session from query param
        db = SessionLocal()
        try:
            from services.auth_service import AuthService
            auth_service = AuthService(db)
            user = auth_service.get_user_by_id(session_user_id)

            if user and user.is_active:
                st.session_state.authenticated = True
                st.session_state.user_id = user.id
                st.session_state.user_email = user.email
                st.session_state.user_name = user.full_name
                st.session_state.user_role = user.role
                st.session_state.user_hourly_rate = user.hourly_rate
                logger.info(f"Session restored from query params: {user.email}")
            else:
                # Invalid or inactive user, clear query params
                st.query_params.clear()
        except Exception as e:
            logger.error(f"Failed to restore session: {str(e)}")
            st.query_params.clear()
        finally:
            db.close()

    # Initialize default values if not set
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if "user_id" not in st.session_state:
        st.session_state.user_id = None

    if "user_email" not in st.session_state:
        st.session_state.user_email = None

    if "user_name" not in st.session_state:
        st.session_state.user_name = None

    if "user_role" not in st.session_state:
        st.session_state.user_role = None

    if "user_hourly_rate" not in st.session_state:
        st.session_state.user_hourly_rate = None


def check_database_health() -> bool:
    """
    Check database connection health.

    Returns:
        True if database is accessible, False otherwise
    """
    try:
        return check_db_connection()
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return False


def get_db_session() -> Session:
    """
    Get database session for the current request.

    Returns:
        SQLAlchemy Session instance
    """
    return SessionLocal()


def render_sidebar() -> None:
    """
    Render sidebar with user information and navigation.
    """
    with st.sidebar:
        st.title("💼 Payroll System")
        st.markdown("---")

        if st.session_state.authenticated:
            # User information
            st.markdown("### 👤 User Profile")
            st.write(f"**Name:** {st.session_state.user_name}")
            st.write(f"**Email:** {st.session_state.user_email}")
            st.write(f"**Role:** {st.session_state.user_role.value.upper()}")
            st.markdown("---")

            # Navigation
            st.markdown("### 📍 Navigation")

            # Role-based navigation options
            if st.session_state.user_role in [UserRole.ADMIN, UserRole.HR]:
                st.info("🔧 Admin/HR Dashboard Active")
            else:
                st.info("👤 Employee Dashboard Active")

            st.markdown("---")

            # System information
            st.markdown("### ℹ️ System Info")
            st.caption(f"Environment: {settings.app_env.upper()}")
            st.caption(f"Database: {'SQLite' if settings.use_local_sqlite else 'PostgreSQL'}")

            st.markdown("---")

            # Logout button - prominent placement
            st.markdown("### 🚪 Account")
            render_logout_button()

        else:
            st.info("Please log in to access the system.")
            st.markdown("---")
            st.markdown("### 🔐 Features")
            st.markdown("""
            - ⏰ Time Tracking
            - 💰 Payroll Management
            - 📊 Reports & Analytics
            - 👥 User Management
            - 🔒 Role-Based Access
            """)


def route_user_dashboard(db: Session) -> None:
    """
    Route authenticated users to appropriate dashboard based on role.

    Args:
        db: SQLAlchemy database session
    """
    user_role = st.session_state.user_role

    # Admin and HR users get admin dashboard
    if user_role in [UserRole.ADMIN, UserRole.HR]:
        render_admin_dashboard(db)
    # Employee users get employee dashboard
    elif user_role == UserRole.EMPLOYEE:
        render_employee_dashboard(db)
    else:
        st.error("Invalid user role. Please contact administrator.")
        logger.error(f"Invalid user role detected: {user_role}")


def main() -> None:
    """
    Main application entry point.
    """
    # Initialize session state
    initialize_session_state()

    # Check database health
    if not check_database_health():
        st.error(
            "⚠️ Database connection failed. "
            "Please check your database configuration and try again."
        )
        st.stop()

    # Initialize database tables
    try:
        init_db()
    except Exception as e:
        st.error(f"⚠️ Database initialization failed: {str(e)}")
        logger.error(f"Database initialization error: {str(e)}")
        st.stop()

    # Render sidebar
    render_sidebar()

    # Create database session with proper context management
    db = SessionLocal()

    try:
        # Route based on authentication status
        if not st.session_state.authenticated:
            # Show login/registration view
            render_auth_view(db)
        else:
            # Route to appropriate dashboard based on role
            route_user_dashboard(db)

    except Exception as e:
        st.error(
            "⚠️ An unexpected error occurred. "
            "Please try refreshing the page or contact support."
        )
        logger.error(f"Application error: {str(e)}", exc_info=True)

    finally:
        # Always close database session
        try:
            db.close()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.critical(f"Critical application error: {str(e)}", exc_info=True)
        st.error("⚠️ Critical system error. Please contact administrator.")
