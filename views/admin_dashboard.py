"""Admin dashboard view for workforce management and payroll processing.

Provides administrators with user management, payroll processing,
attendance oversight, and reporting capabilities.
"""

from datetime import date, timedelta
from decimal import Decimal

import streamlit as st
from sqlalchemy.orm import Session

from models.attendance import AttendanceStatus
from models.payroll import PayrollStatus
from models.user import User, UserRole
from services.attendance_service import AttendanceService
from services.auth_service import AuthService
from services.export_service import ExportService
from services.payroll_engine import PayrollEngine
from utils.exceptions import PayrollProcessingError, ValidationError
from utils.formatters import format_currency, format_date, format_datetime, format_hours
from utils.logger import get_logger

logger = get_logger(__name__)


def render_admin_dashboard(db: Session) -> None:
    """
    Render admin dashboard with management capabilities.

    Args:
        db: SQLAlchemy database session
    """
    st.title("🔧 Admin Dashboard")
    st.markdown("**Workforce Management & Payroll Processing**")
    st.markdown("---")

    # Create tabs for different admin sections
    tabs = st.tabs([
        "👥 Users",
        "💼 Payroll",
        "📋 Attendance",
        "🚩 Flagged Records",
        "📊 Reports"
    ])

    auth_service = AuthService(db)
    attendance_service = AttendanceService(db)
    payroll_engine = PayrollEngine(db)
    export_service = ExportService()

    # Users Tab
    with tabs[0]:
        render_users_management(db, auth_service)

    # Payroll Tab
    with tabs[1]:
        render_payroll_processing(db, payroll_engine)

    # Attendance Tab
    with tabs[2]:
        render_attendance_overview(db, attendance_service)

    # Flagged Records Tab
    with tabs[3]:
        render_flagged_records(db, attendance_service)

    # Reports Tab
    with tabs[4]:
        render_reports(db, auth_service, attendance_service, payroll_engine, export_service)


def render_users_management(db: Session, auth_service: AuthService) -> None:
    """Render user management section."""
    st.subheader("User Management")

    # Create new user section
    with st.expander("➕ Create New User", expanded=False):
        with st.form("create_user_form"):
            col1, col2 = st.columns(2)

            with col1:
                new_full_name = st.text_input("Full Name")
                new_email = st.text_input("Email")
                new_password = st.text_input("Password", type="password")

            with col2:
                new_role = st.selectbox(
                    "Role",
                    options=[UserRole.EMPLOYEE, UserRole.HR, UserRole.ADMIN],
                    format_func=lambda x: x.value.upper()
                )
                new_hourly_rate = st.number_input(
                    "Hourly Rate (PKR)",
                    min_value=0.0,
                    value=500.0,
                    step=50.0
                )

            submit_create = st.form_submit_button("Create User", use_container_width=True)

            if submit_create:
                if not all([new_full_name, new_email, new_password]):
                    st.error("All fields are required.")
                else:
                    try:
                        new_user = auth_service.register_user(
                            email=new_email,
                            password=new_password,
                            full_name=new_full_name,
                            role=new_role,
                            hourly_rate=new_hourly_rate
                        )
                        st.success(f"User created: {new_user.email}")
                        logger.info(f"Admin created user: {new_user.email}")
                        st.rerun()
                    except ValidationError as e:
                        st.error(f"Failed to create user: {e.message}")
                    except Exception as e:
                        st.error("An unexpected error occurred.")
                        logger.error(f"User creation error: {str(e)}")

    st.markdown("---")

    # List all users
    st.markdown("### All Users")
    users = auth_service.get_all_users(include_inactive=True)

    if not users:
        st.info("No users found.")
    else:
        for user in users:
            with st.expander(
                f"{'🟢' if user.is_active else '🔴'} {user.full_name} - "
                f"{user.email} ({user.role.value.upper()})"
            ):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.write(f"**ID:** {user.id}")
                    st.write(f"**Email:** {user.email}")
                    st.write(f"**Role:** {user.role.value.upper()}")
                    st.write(f"**Hourly Rate:** {format_currency(user.hourly_rate)}")
                    st.write(f"**Status:** {'Active' if user.is_active else 'Inactive'}")
                    st.write(f"**Created:** {format_date(user.created_at.date())}")

                with col2:
                    # Update hourly rate
                    new_rate = st.number_input(
                        "Update Rate (PKR)",
                        min_value=0.0,
                        value=float(user.hourly_rate),
                        step=50.0,
                        key=f"rate_{user.id}"
                    )
                    if st.button("💰 Update Rate", key=f"btn_rate_{user.id}"):
                        try:
                            auth_service.update_hourly_rate(user.id, new_rate)
                            st.success("Rate updated!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {str(e)}")

                    # Deactivate user
                    if user.is_active:
                        if st.button("🚫 Deactivate", key=f"btn_deact_{user.id}"):
                            try:
                                auth_service.deactivate_user(user.id)
                                st.success("User deactivated!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed: {str(e)}")


def render_payroll_processing(db: Session, payroll_engine: PayrollEngine) -> None:
    """Render payroll processing section."""
    st.subheader("Payroll Processing")

    # Process new payroll batch
    with st.expander("🆕 Process New Payroll Batch", expanded=False):
        with st.form("process_payroll_form"):
            col1, col2 = st.columns(2)

            with col1:
                pay_start = st.date_input(
                    "Pay Period Start",
                    value=date.today().replace(day=1),
                    key="pay_start"
                )
            with col2:
                pay_end = st.date_input(
                    "Pay Period End",
                    value=date.today(),
                    key="pay_end"
                )

            deductions_input = st.number_input(
                "Default Deductions ($)",
                min_value=0.0,
                value=0.0,
                step=10.0
            )

            submit_process = st.form_submit_button(
                "🔄 Process Payroll for All Active Users",
                use_container_width=True
            )

            if submit_process:
                try:
                    deductions = Decimal(str(deductions_input))
                    payroll_runs = payroll_engine.process_payroll_batch(
                        pay_period_start=pay_start,
                        pay_period_end=pay_end,
                        default_deductions=deductions
                    )
                    st.success(f"Processed {len(payroll_runs)} payroll runs!")
                    logger.info(f"Batch payroll processed: {len(payroll_runs)} runs")
                    st.rerun()
                except PayrollProcessingError as e:
                    st.error(f"Processing failed: {e.message}")
                except Exception as e:
                    st.error("An unexpected error occurred.")
                    logger.error(f"Payroll processing error: {str(e)}")

    st.markdown("---")

    # Display existing payroll runs
    st.markdown("### Payroll Runs")

    # Filter by status
    status_filter = st.selectbox(
        "Filter by Status",
        options=[None, PayrollStatus.DRAFT, PayrollStatus.APPROVED, PayrollStatus.PAID],
        format_func=lambda x: "All" if x is None else x.value.upper()
    )

    payroll_runs = payroll_engine.get_all_payroll_runs(status=status_filter)

    if not payroll_runs:
        st.info("No payroll runs found.")
    else:
        st.write(f"Found {len(payroll_runs)} payroll runs")

        for payroll in payroll_runs:
            status_emoji = {
                PayrollStatus.DRAFT: "📝",
                PayrollStatus.APPROVED: "✅",
                PayrollStatus.PAID: "💵"
            }

            with st.expander(
                f"{status_emoji[payroll.status]} {payroll.user.full_name} - "
                f"{format_date(payroll.pay_period_start)} to {format_date(payroll.pay_period_end)} - "
                f"{format_currency(payroll.net_pay)}"
            ):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("Base Salary", format_currency(payroll.base_salary))
                    st.metric("Overtime Pay", format_currency(payroll.overtime_pay))

                with col2:
                    st.metric("Gross Pay", format_currency(payroll.gross_pay))
                    st.metric("Deductions", format_currency(payroll.deductions))

                with col3:
                    st.metric("Net Pay", format_currency(payroll.net_pay))
                    st.write(f"**Status:** {payroll.status.value.upper()}")

                # Action buttons
                col_actions = st.columns(3)

                with col_actions[0]:
                    if payroll.status == PayrollStatus.DRAFT:
                        if st.button("✅ Approve", key=f"approve_{payroll.id}"):
                            try:
                                payroll_engine.approve_payroll(payroll.id)
                                st.success("Payroll approved!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed: {str(e)}")

                with col_actions[1]:
                    if payroll.status == PayrollStatus.APPROVED:
                        if st.button("💵 Mark as Paid", key=f"paid_{payroll.id}"):
                            try:
                                payroll_engine.mark_as_paid(payroll.id)
                                st.success("Marked as paid!")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed: {str(e)}")


def render_attendance_overview(db: Session, attendance_service: AttendanceService) -> None:
    """Render attendance overview section."""
    st.subheader("Attendance Overview")

    # Auto-flag unclosed shifts
    if st.button("🔄 Auto-Flag Unclosed Shifts", use_container_width=True):
        try:
            count = attendance_service.auto_flag_unclosed_shifts()
            st.success(f"Flagged {count} unclosed shifts.")
            logger.info(f"Auto-flagged {count} unclosed shifts")
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {str(e)}")

    st.markdown("---")

    # Display open shifts
    st.markdown("### Currently Open Shifts")
    open_shifts = attendance_service.get_open_shifts()

    if not open_shifts:
        st.info("No open shifts.")
    else:
        for shift in open_shifts:
            st.write(
                f"👤 **{shift.user.full_name}** - "
                f"Checked in at {format_datetime(shift.check_in, 'UTC', '%Y-%m-%d %H:%M:%S')}"
            )


def render_flagged_records(db: Session, attendance_service: AttendanceService) -> None:
    """Render flagged attendance records section."""
    st.subheader("Flagged Attendance Records")
    st.info("These records require HR review and approval.")

    flagged_records = attendance_service.get_flagged_attendance()

    if not flagged_records:
        st.success("No flagged records.")
    else:
        st.warning(f"Found {len(flagged_records)} flagged records")

        for record in flagged_records:
            with st.expander(
                f"🚩 {record.user.full_name} - {format_date(record.date)}"
            ):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.write(f"**Employee:** {record.user.full_name}")
                    st.write(f"**Date:** {format_date(record.date)}")
                    st.write(f"**Check-in:** {format_datetime(record.check_in, 'UTC', '%H:%M:%S')}")
                    st.write(
                        f"**Check-out:** "
                        f"{format_datetime(record.check_out, 'UTC', '%H:%M:%S') if record.check_out else 'Open'}"
                    )
                    st.write(f"**Regular Hours:** {format_hours(record.regular_hours)}")
                    st.write(f"**Overtime Hours:** {format_hours(record.overtime_hours)}")

                with col2:
                    if st.button("✅ Approve", key=f"approve_flag_{record.id}"):
                        try:
                            attendance_service.approve_flagged_attendance(record.id)
                            st.success("Record approved!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {str(e)}")


def render_reports(
    db: Session,
    auth_service: AuthService,
    attendance_service: AttendanceService,
    payroll_engine: PayrollEngine,
    export_service: ExportService
) -> None:
    """Render reports and export section."""
    st.subheader("Reports & Exports")

    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        report_start = st.date_input(
            "From Date",
            value=date.today().replace(day=1),
            key="report_start"
        )
    with col2:
        report_end = st.date_input(
            "To Date",
            value=date.today(),
            key="report_end"
        )

    st.markdown("---")

    # Export buttons
    col_export = st.columns(3)

    with col_export[0]:
        if st.button("📥 Export Employee List (CSV)", use_container_width=True):
            try:
                users = auth_service.get_all_users(include_inactive=True)
                csv_buffer = export_service.generate_employee_summary_csv(users)
                st.download_button(
                    label="💾 Download CSV",
                    data=csv_buffer,
                    file_name=f"employees_{date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                logger.info("Employee list exported")
            except Exception as e:
                st.error(f"Export failed: {str(e)}")

    with col_export[1]:
        if st.button("📥 Export Attendance (CSV)", use_container_width=True):
            try:
                # Get all users and their attendance
                users = auth_service.get_all_users()
                all_attendance = []
                for user in users:
                    records = attendance_service.get_attendance_by_user(
                        user_id=user.id,
                        start_date=report_start,
                        end_date=report_end
                    )
                    all_attendance.extend(records)

                csv_buffer = export_service.generate_attendance_csv(
                    all_attendance,
                    report_start,
                    report_end
                )
                st.download_button(
                    label="💾 Download CSV",
                    data=csv_buffer,
                    file_name=f"attendance_{report_start}_to_{report_end}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                logger.info("Attendance report exported")
            except Exception as e:
                st.error(f"Export failed: {str(e)}")

    with col_export[2]:
        if st.button("📥 Export Payroll (CSV)", use_container_width=True):
            try:
                payroll_runs = payroll_engine.get_all_payroll_runs()
                # Filter by date range
                filtered_runs = [
                    p for p in payroll_runs
                    if report_start <= p.pay_period_end <= report_end
                ]

                csv_buffer = export_service.generate_payroll_csv(
                    filtered_runs,
                    report_start,
                    report_end
                )
                st.download_button(
                    label="💾 Download CSV",
                    data=csv_buffer,
                    file_name=f"payroll_{report_start}_to_{report_end}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                logger.info("Payroll report exported")
            except Exception as e:
                st.error(f"Export failed: {str(e)}")
