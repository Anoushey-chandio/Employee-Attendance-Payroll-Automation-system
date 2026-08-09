"""Authentication view for login and registration.

Provides UI for user authentication and new account registration.
"""

import streamlit as st
from sqlalchemy.orm import Session

from models.user import UserRole
from services.auth_service import AuthService
from utils.exceptions import AuthenticationError, ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)


def clear_user_session() -> None:
    """Clear query params, purge session state, and force a rerun."""
    try:
        st.query_params.clear()
    except Exception:
        pass

    st.session_state.clear()
    st.rerun()


def render_auth_view(db: Session) -> None:
    """
    Render authentication interface (login/registration).

    Args:
        db: SQLAlchemy database session
    """
    st.title("🔐 Enterprise Payroll System")
    st.markdown("---")

    # Create tabs for login and registration
    tab_login, tab_register = st.tabs(["Login", "Register"])

    auth_service = AuthService(db)

    # Login Tab
    with tab_login:
        st.subheader("Login to Your Account")

        with st.form("login_form"):
            email = st.text_input(
                "Email",
                placeholder="your.email@company.com",
                key="login_email"
            )
            password = st.text_input(
                "Password",
                type="password",
                key="login_password"
            )

            submit_login = st.form_submit_button("Login", use_container_width=True)

            if submit_login:
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    try:
                        # Authenticate user
                        user = auth_service.authenticate_user(email, password)

                        # Store user in session state
                        st.session_state.user_id = user.id
                        st.session_state.user_email = user.email
                        st.session_state.user_name = user.full_name
                        st.session_state.user_role = user.role
                        st.session_state.user_hourly_rate = user.hourly_rate
                        st.session_state.authenticated = True

                        # Set session token in query params for persistence across refresh
                        st.query_params["sid"] = str(user.id)

                        st.success(f"Welcome back, {user.full_name}!")
                        logger.info(f"User logged in: {user.email}")
                        st.rerun()

                    except AuthenticationError as e:
                        st.error(f"Authentication failed: {e.message}")
                        logger.warning(f"Failed login attempt: {email}")
                    except Exception as e:
                        st.error("An unexpected error occurred. Please try again.")
                        logger.error(f"Login error: {str(e)}")

    # Registration Tab
    with tab_register:
        st.subheader("Create New Account")
        st.info("Register as an employee. Admin accounts must be created by existing admins.")

        with st.form("register_form"):
            reg_full_name = st.text_input(
                "Full Name",
                placeholder="John Doe",
                key="reg_full_name"
            )
            reg_email = st.text_input(
                "Email",
                placeholder="your.email@company.com",
                key="reg_email"
            )
            reg_password = st.text_input(
                "Password",
                type="password",
                help="Minimum 6 characters",
                key="reg_password"
            )
            reg_password_confirm = st.text_input(
                "Confirm Password",
                type="password",
                key="reg_password_confirm"
            )

            submit_register = st.form_submit_button(
                "Register",
                use_container_width=True
            )

            if submit_register:
                # Validate inputs
                if not all([reg_full_name, reg_email, reg_password, reg_password_confirm]):
                    st.error("All fields are required.")
                elif reg_password != reg_password_confirm:
                    st.error("Passwords do not match.")
                elif len(reg_password) < 6:
                    st.error("Password must be at least 6 characters.")
                else:
                    try:
                        # Register new user
                        new_user = auth_service.register_user(
                            email=reg_email,
                            password=reg_password,
                            full_name=reg_full_name,
                            role=UserRole.EMPLOYEE,
                            hourly_rate=0.0
                        )

                        st.success(
                            f"Account created successfully! "
                            f"Please login with your credentials."
                        )
                        logger.info(f"New user registered: {new_user.email}")

                    except ValidationError as e:
                        st.error(f"Registration failed: {e.message}")
                        logger.warning(f"Failed registration: {reg_email}")
                    except Exception as e:
                        st.error("An unexpected error occurred. Please try again.")
                        logger.error(f"Registration error: {str(e)}")


def render_logout_button() -> None:
    """
    Render logout button in sidebar and ensure complete cache/session reset.
    """
    if st.sidebar.button("🚪 Logout", use_container_width=True, type="primary"):
        # 1. Log action before state clean up
        user_email = st.session_state.get("user_email", "Unknown")
        logger.info(f"User logging out: {user_email}")

        # 2. Clear query parameters, purge all cached data, and force a redirect
        clear_user_session()