"""Employee dashboard view for self-service attendance and payroll access.

Provides employees with check-in/out functionality and personal payroll history.
"""

from datetime import date, datetime
from decimal import Decimal

import pytz
import streamlit as st
from sqlalchemy.orm import Session

from models.attendance import AttendanceStatus
from models.payroll import PayrollStatus
from services.attendance_service import AttendanceService
from services.export_service import ExportService
from services.payroll_engine import PayrollEngine
from utils.exceptions import AttendanceError
from utils.formatters import format_currency, format_datetime, format_date, format_hours
from utils.logger import get_logger

logger = get_logger(__name__)


def render_employee_dashboard(db: Session) -> None:
    """
    Render employee self-service dashboard.

    Args:
        db: SQLAlchemy database session
    """
    user_id = st.session_state.user_id
    user_name = st.session_state.user_name
    user_hourly_rate = st.session_state.get("user_hourly_rate", Decimal("0.00"))

    st.title(f"👤 Employee Dashboard")
    st.markdown(f"**Welcome, {user_name}!**")
    st.markdown("---")

    # Create tabs for different sections
    tab_attendance, tab_payroll, tab_history = st.tabs([
        "⏰ Attendance",
        "💰 Payroll",
        "📊 History"
    ])

    attendance_service = AttendanceService(db)
    payroll_engine = PayrollEngine(db)
    export_service = ExportService()

    # Attendance Tab
    with tab_attendance:
        st.subheader("Time Tracking")

        # Force fresh database query - no caching
        today = date.today()

        # Refresh the database session to get latest data
        db.expire_all()
        db.commit()  # Commit any pending transactions before querying

        today_attendance = attendance_service.get_attendance_by_user(
            user_id=user_id,
            start_date=today,
            end_date=today
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Check In / Check Out")

            # Determine current state
            has_attendance = bool(today_attendance)
            is_checked_in = has_attendance and today_attendance[0].is_open_shift
            is_completed = has_attendance and not today_attendance[0].is_open_shift

            if not has_attendance:
                # No attendance today - show check-in button
                st.info("ℹ️ You haven't checked in today.")
                if st.button("🟢 Check In", use_container_width=True, type="primary", key="btn_check_in"):
                    try:
                        attendance = attendance_service.check_in(user_id=user_id)
                        db.commit()  # Ensure changes are committed
                        db.flush()   # Flush to database immediately
                        logger.info(f"Employee checked in: {user_id} at {attendance.check_in}")
                        # Force immediate UI refresh without showing intermediate message
                        st.rerun()
                    except AttendanceError as e:
                        st.error(f"❌ Check-in failed: {e.message}")
                        logger.error(f"Check-in failed for user {user_id}: {e.message}")
                    except Exception as e:
                        st.error("❌ An unexpected error occurred.")
                        logger.error(f"Check-in error: {str(e)}")

            elif is_checked_in:
                # Already checked in, waiting for check-out
                attendance = today_attendance[0]

                # Ensure check_in has timezone info
                check_in_time = attendance.check_in
                if check_in_time.tzinfo is None:
                    check_in_time = pytz.UTC.localize(check_in_time)

                st.success(
                    f"✅ You are currently Checked In (Shift active since "
                    f"{format_datetime(check_in_time, 'UTC', '%H:%M:%S')})"
                )

                # Calculate current duration
                current_time = datetime.now(pytz.UTC)
                duration_seconds = (current_time - check_in_time).total_seconds()
                current_hours = Decimal(str(duration_seconds / 3600)).quantize(Decimal("0.01"))

                st.metric("Current Duration", format_hours(current_hours))

                if st.button("🔴 Check Out", use_container_width=True, type="secondary", key="btn_check_out"):
                    try:
                        attendance = attendance_service.check_out(user_id=user_id)
                        db.commit()  # Ensure changes are committed
                        db.flush()   # Flush to database immediately
                        logger.info(
                            f"Employee checked out: {user_id} - "
                            f"Regular: {attendance.regular_hours}h, Overtime: {attendance.overtime_hours}h"
                        )
                        # Force immediate UI refresh without showing intermediate message
                        st.rerun()
                    except AttendanceError as e:
                        st.error(f"❌ Check-out failed: {e.message}")
                        logger.error(f"Check-out failed for user {user_id}: {e.message}")
                    except Exception as e:
                        st.error("❌ An unexpected error occurred.")
                        logger.error(f"Check-out error: {str(e)}")

            elif is_completed:
                # Already completed today
                attendance = today_attendance[0]

                st.info("✅ **Your Shift is Off**")
                st.markdown("---")

                # Display shift details
                st.markdown("#### Today's Shift Summary")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("Regular Hours", format_hours(attendance.regular_hours))
                    st.metric("Overtime Hours", format_hours(attendance.overtime_hours))
                with col_b:
                    st.metric("Total Hours", format_hours(attendance.total_hours))
                    st.metric("Status", attendance.status.value.upper())

                # Calculate payroll for this shift
                st.markdown("---")
                st.markdown("#### 💰 Calculated Pay for Today")

                # Get user's hourly rate
                if user_hourly_rate and user_hourly_rate > 0:
                    # Standard pay calculation
                    regular_pay = attendance.regular_hours * user_hourly_rate

                    # Overtime pay (typically 1.5x for overtime hours)
                    overtime_multiplier = Decimal("1.5")
                    overtime_pay = attendance.overtime_hours * user_hourly_rate * overtime_multiplier

                    total_gross_pay = regular_pay + overtime_pay

                    col_x, col_y, col_z = st.columns(3)
                    with col_x:
                        st.metric("Regular Pay", format_currency(regular_pay))
                    with col_y:
                        st.metric("Overtime Pay", format_currency(overtime_pay))
                    with col_z:
                        st.metric("Total Gross Pay", format_currency(total_gross_pay))

                    st.caption(f"💡 Rate: {format_currency(user_hourly_rate)}/hr | Overtime: {format_currency(user_hourly_rate * overtime_multiplier)}/hr (1.5x)")
                else:
                    st.warning("⚠️ Hourly rate not set. Please contact HR to configure your pay rate.")

                st.markdown("---")
                st.caption("📌 This is a preliminary calculation. Official payroll will be processed at the end of the pay period.")

        with col2:
            st.markdown("### Today's Summary")

            if not has_attendance:
                # No attendance record yet
                st.info("🕐 **No Check-In Today**\n\nYou haven't started your shift yet. Click 'Check In' to begin tracking your time.")

            elif is_checked_in:
                # Active shift in progress
                attendance = today_attendance[0]
                check_in_time = attendance.check_in
                if check_in_time.tzinfo is None:
                    check_in_time = pytz.UTC.localize(check_in_time)

                st.success(
                    f"⏱️ **Active Shift**\n\n"
                    f"**Check-in:** {format_datetime(check_in_time, 'UTC', '%H:%M:%S')}\n\n"
                    f"**Status:** WORKING\n\n"
                    f"Your shift is currently active. Don't forget to check out when you're done!"
                )

            elif is_completed:
                # Shift completed
                attendance = today_attendance[0]
                st.info(
                    f"✅ **Shift Completed**\n\n"
                    f"**Check-in:** {format_datetime(attendance.check_in, 'UTC', '%H:%M:%S')}\n\n"
                    f"**Check-out:** {format_datetime(attendance.check_out, 'UTC', '%H:%M:%S')}\n\n"
                    f"**Total Hours:** {format_hours(attendance.total_hours)}\n\n"
                    f"**Status:** {attendance.status.value.upper()}"
                )

    # Payroll Tab
    with tab_payroll:
        st.subheader("💰 Your Earnings")

        # Fetch all completed attendance records (checked-out shifts)
        from datetime import timedelta

        # Get attendance records from the last 30 days
        thirty_days_ago = date.today() - timedelta(days=30)
        all_attendance = attendance_service.get_attendance_by_user(
            user_id=user_id,
            start_date=thirty_days_ago,
            end_date=date.today()
        )

        # Filter only COMPLETED shifts (checked out)
        completed_shifts = [
            att for att in all_attendance
            if att.status == AttendanceStatus.COMPLETED and att.check_out is not None
        ]

        if not completed_shifts:
            st.info("📋 No completed shifts found. Check out after your shift to see earnings here.")
        else:
            # Calculate total earnings from all completed shifts
            total_regular_hours = Decimal("0.00")
            total_overtime_hours = Decimal("0.00")
            total_regular_pay = Decimal("0.00")
            total_overtime_pay = Decimal("0.00")

            for shift in completed_shifts:
                total_regular_hours += shift.regular_hours
                total_overtime_hours += shift.overtime_hours

                if user_hourly_rate and user_hourly_rate > 0:
                    total_regular_pay += shift.regular_hours * user_hourly_rate
                    total_overtime_pay += shift.overtime_hours * user_hourly_rate * Decimal("1.5")

            total_gross_earnings = total_regular_pay + total_overtime_pay

            # Summary Metrics
            st.markdown("### 📊 Last 30 Days Summary")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Completed Shifts", len(completed_shifts))
            with col2:
                st.metric("Total Hours", format_hours(total_regular_hours + total_overtime_hours))
            with col3:
                st.metric("Overtime Hours", format_hours(total_overtime_hours))
            with col4:
                st.metric("Total Earnings", format_currency(total_gross_earnings))

            st.markdown("---")

            # Display each completed shift
            st.markdown("### 📅 Shift-by-Shift Breakdown")

            for shift in completed_shifts:
                with st.expander(
                    f"🗓️ {format_date(shift.date)} - {format_hours(shift.total_hours)} - "
                    f"{format_currency((shift.regular_hours * user_hourly_rate) + (shift.overtime_hours * user_hourly_rate * Decimal('1.5')) if user_hourly_rate else Decimal('0.00'))}"
                ):
                    col_a, col_b = st.columns(2)

                    with col_a:
                        st.write(f"**Date:** {format_date(shift.date)}")
                        st.write(f"**Check-in:** {format_datetime(shift.check_in, 'UTC', '%H:%M:%S')}")
                        st.write(f"**Check-out:** {format_datetime(shift.check_out, 'UTC', '%H:%M:%S')}")
                        st.write(f"**Status:** {shift.status.value.upper()}")

                    with col_b:
                        st.write(f"**Regular Hours:** {format_hours(shift.regular_hours)}")
                        st.write(f"**Overtime Hours:** {format_hours(shift.overtime_hours)}")
                        st.write(f"**Total Hours:** {format_hours(shift.total_hours)}")

                        if user_hourly_rate and user_hourly_rate > 0:
                            shift_regular_pay = shift.regular_hours * user_hourly_rate
                            shift_overtime_pay = shift.overtime_hours * user_hourly_rate * Decimal("1.5")
                            shift_total_pay = shift_regular_pay + shift_overtime_pay

                            st.markdown("---")
                            st.write(f"**Regular Pay:** {format_currency(shift_regular_pay)}")
                            st.write(f"**Overtime Pay:** {format_currency(shift_overtime_pay)}")
                            st.write(f"**💰 Total Pay:** {format_currency(shift_total_pay)}")

            st.markdown("---")
            st.caption(f"💡 Hourly Rate: {format_currency(user_hourly_rate)}/hr | Overtime Rate: {format_currency(user_hourly_rate * Decimal('1.5'))}/hr")

        # Show formal payroll runs if they exist (optional section)
        st.markdown("---")
        st.markdown("### 🧾 Official Payroll Records")

        payroll_runs = payroll_engine.get_payroll_by_user(user_id=user_id)

        if not payroll_runs:
            st.info("No official payroll records yet. These are generated by HR at the end of pay periods.")
        else:
            # Show latest payroll
            latest_payroll = payroll_runs[0]

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Gross Pay", format_currency(latest_payroll.gross_pay))
            with col2:
                st.metric("Deductions", format_currency(latest_payroll.deductions))
            with col3:
                st.metric("Net Pay", format_currency(latest_payroll.net_pay))

            st.markdown("---")

            # Display payroll details
            st.markdown("#### Latest Payslip")
            st.write(f"**Pay Period:** {format_date(latest_payroll.pay_period_start)} to {format_date(latest_payroll.pay_period_end)}")
            st.write(f"**Status:** {latest_payroll.status.value.upper()}")

            # Breakdown table
            st.markdown("##### Earnings Breakdown")
            breakdown_data = {
                "Component": ["Base Salary", "Overtime Pay", "Gross Pay", "Deductions", "Net Pay"],
                "Amount": [
                    format_currency(latest_payroll.base_salary),
                    format_currency(latest_payroll.overtime_pay),
                    format_currency(latest_payroll.gross_pay),
                    format_currency(latest_payroll.deductions),
                    format_currency(latest_payroll.net_pay)
                ]
            }
            st.table(breakdown_data)

            # Download PDF button
            if latest_payroll.status in [PayrollStatus.APPROVED, PayrollStatus.PAID]:
                if st.button("📄 Download PDF Payslip", use_container_width=True):
                    try:
                        pdf_buffer = export_service.generate_payslip_pdf(latest_payroll)
                        st.download_button(
                            label="💾 Save PDF",
                            data=pdf_buffer,
                            file_name=f"payslip_{latest_payroll.id}_{latest_payroll.pay_period_end}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                        logger.info(f"PDF payslip downloaded: payroll_id={latest_payroll.id}")
                    except Exception as e:
                        st.error("Failed to generate PDF.")
                        logger.error(f"PDF generation error: {str(e)}")

    # History Tab
    with tab_history:
        st.subheader("Attendance History")

        # Date range selector
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "From Date",
                value=date.today().replace(day=1),
                key="history_start_date"
            )
        with col2:
            end_date = st.date_input(
                "To Date",
                value=date.today(),
                key="history_end_date"
            )

        if st.button("🔍 Load History", use_container_width=True):
            attendance_records = attendance_service.get_attendance_by_user(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date
            )

            if not attendance_records:
                st.info("No attendance records found for the selected period.")
            else:
                # Display records
                st.write(f"Found {len(attendance_records)} records")

                for record in attendance_records:
                    with st.expander(
                        f"📅 {format_date(record.date)} - "
                        f"{record.status.value.upper()} - "
                        f"{format_hours(record.total_hours)}"
                    ):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Check-in:** {format_datetime(record.check_in, 'UTC', '%H:%M:%S')}")
                            st.write(f"**Check-out:** {format_datetime(record.check_out, 'UTC', '%H:%M:%S') if record.check_out else 'Open'}")
                        with col2:
                            st.write(f"**Regular Hours:** {format_hours(record.regular_hours)}")
                            st.write(f"**Overtime Hours:** {format_hours(record.overtime_hours)}")
                            st.write(f"**Status:** {record.status.value.upper()}")

                # Calculate summary
                total_regular = sum(
                    r.regular_hours for r in attendance_records
                    if r.status != AttendanceStatus.FLAGGED
                )
                total_overtime = sum(
                    r.overtime_hours for r in attendance_records
                    if r.status != AttendanceStatus.FLAGGED
                )

                st.markdown("---")
                st.markdown("### Period Summary")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Days", len(attendance_records))
                with col2:
                    st.metric("Total Regular Hours", format_hours(total_regular))
                with col3:
                    st.metric("Total Overtime Hours", format_hours(total_overtime))
