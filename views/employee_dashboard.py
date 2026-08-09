"""Employee dashboard view for self-service attendance and payroll access.

Provides employees with check-in/out functionality and personal payroll history.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytz
import streamlit as st
from sqlalchemy.orm import Session

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

if ZoneInfo is not None:
    PKT_TZ = ZoneInfo("Asia/Karachi")
else:
    PKT_TZ = pytz.timezone("Asia/Karachi")

from models.attendance import AttendanceStatus
from models.payroll import PayrollStatus
from services.attendance_service import AttendanceService
from services.export_service import ExportService
from services.payroll_engine import PayrollEngine
from utils.exceptions import AttendanceError
from utils.formatters import format_currency, format_datetime, format_date, format_hours, calculate_shift_metrics, format_attendance_status
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

        # Auto-close legacy shifts older than 24 hours
        try:
            attendance_service.auto_close_legacy_shifts()
        except Exception as e:
            logger.warning(f"Auto-close legacy shifts failed: {str(e)}")

        # Force fresh database query on every render
        db.expire_all()
        db.commit()

        # Check for ACTIVE (open) shift - this determines the button state
        active_attendance = attendance_service.get_active_attendance(user_id)
        today_attendance = attendance_service.get_today_attendance(user_id)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Check In / Check Out")

            # Determine current state based on ACTIVE shift (open shift with no check_out)
            is_checked_in = active_attendance is not None

            if not is_checked_in:
                # NO ACTIVE SHIFT -> Show check-in button
                # This covers: (1) No shift today, (2) Previous shift completed
                if today_attendance and today_attendance.check_out is not None:
                    st.info("✅ Previous shift completed. Ready for next shift!")
                else:
                    st.info("ℹ️ You haven't checked in today.")

                if st.button("🟢 Check In", use_container_width=True, type="primary", key="btn_check_in"):
                    try:
                        attendance = attendance_service.check_in(user_id=user_id)
                        db.commit()
                        db.flush()
                        logger.info(f"Employee checked in: {user_id} at {attendance.check_in}")
                        st.rerun()
                    except AttendanceError as e:
                        st.error(f"❌ Check-in failed: {e.message}")
                        logger.error(f"Check-in failed for user {user_id}: {e.message}")
                    except Exception as e:
                        st.error("❌ An unexpected error occurred.")
                        logger.error(f"Check-in error: {str(e)}")

            else:
                # ACTIVE SHIFT -> Show check-out button
                attendance = active_attendance
                check_in_time = None

                if attendance is not None and getattr(attendance, "check_in", None) is not None:
                    check_in_time = attendance.check_in
                    try:
                        if check_in_time.tzinfo is None:
                            if hasattr(PKT_TZ, "localize"):
                                check_in_time = PKT_TZ.localize(check_in_time)
                            else:
                                check_in_time = check_in_time.replace(tzinfo=PKT_TZ)
                        else:
                            check_in_time = check_in_time.astimezone(PKT_TZ)
                    except Exception:
                        pass

                # Working badge
                st.success("⏳ **Working** - Shift active")
                st.markdown("---")

                # Display check-in time
                if check_in_time is not None:
                    st.write(f"**Check-in Time:** {format_datetime(check_in_time, 'Asia/Karachi', '%H:%M:%S')}")

                    # Calculate current duration using centralized function
                    metrics = calculate_shift_metrics(check_in_time, None)
                    st.metric("⏱️ Current Duration", metrics["display_duration"])
                else:
                    st.warning("⚠️ Check-in time is unavailable for this active shift.")

                st.markdown("---")

                # Dynamic Check-Out button
                if st.button("🔴 Check Out", use_container_width=True, type="primary", key="btn_check_out"):
                    try:
                        attendance = attendance_service.check_out(user_id=user_id)
                        db.commit()
                        db.flush()
                        logger.info(
                            f"Employee checked out: {user_id} - "
                            f"Regular: {attendance.regular_hours}h, Overtime: {attendance.overtime_hours}h"
                        )
                        st.rerun()
                    except AttendanceError as e:
                        st.error(f"❌ Check-out failed: {e.message}")
                        logger.error(f"Check-out failed for user {user_id}: {e.message}")
                    except Exception as e:
                        st.error("❌ An unexpected error occurred.")
                        logger.error(f"Check-out error: {str(e)}")

        with col2:
            st.markdown("### Today's Summary")

            if not is_checked_in:
                # Show last completed shift if exists
                if today_attendance and today_attendance.check_out is not None:
                    attendance = today_attendance
                    check_in_time = None
                    if attendance is not None and getattr(attendance, "check_in", None) is not None:
                        check_in_time = attendance.check_in
                        try:
                            if check_in_time.tzinfo is None:
                                if hasattr(PKT_TZ, "localize"):
                                    check_in_time = PKT_TZ.localize(check_in_time)
                                else:
                                    check_in_time = check_in_time.replace(tzinfo=PKT_TZ)
                            else:
                                check_in_time = check_in_time.astimezone(PKT_TZ)
                        except Exception:
                            pass

                    check_out_time = None
                    if attendance is not None and getattr(attendance, "check_out", None) is not None:
                        check_out_time = attendance.check_out
                        try:
                            if check_out_time.tzinfo is None:
                                if hasattr(PKT_TZ, "localize"):
                                    check_out_time = PKT_TZ.localize(check_out_time)
                                else:
                                    check_out_time = check_out_time.replace(tzinfo=PKT_TZ)
                            else:
                                check_out_time = check_out_time.astimezone(PKT_TZ)
                        except Exception:
                            pass

                    st.info(
                        f"✅ **Last Shift Completed**\n\n"
                        f"**Check-in:** {format_datetime(check_in_time, 'Asia/Karachi', '%H:%M:%S')}\n\n"
                        f"**Check-out:** {format_datetime(check_out_time, 'Asia/Karachi', '%H:%M:%S')}\n\n"
                        f"**Total Hours:** {format_hours(attendance.total_hours)}\n\n"
                        f"**Status:** {format_attendance_status(attendance)}\n\n"
                        f"💡 Ready to start next shift!"
                    )
                else:
                    st.info("🕐 **No Check-In Today**\n\nYou haven't started your shift yet. Click 'Check In' to begin tracking your time.")

            else:
                # Active shift in progress
                attendance = active_attendance
                check_in_time = None
                if attendance is not None and getattr(attendance, "check_in", None) is not None:
                    check_in_time = attendance.check_in
                    try:
                        if check_in_time.tzinfo is None:
                            if hasattr(PKT_TZ, "localize"):
                                check_in_time = PKT_TZ.localize(check_in_time)
                            else:
                                check_in_time = check_in_time.replace(tzinfo=PKT_TZ)
                        else:
                            check_in_time = check_in_time.astimezone(PKT_TZ)
                    except Exception:
                        pass

                # Calculate current duration
                if check_in_time is not None:
                    metrics = calculate_shift_metrics(check_in_time, None)

                    st.success(
                        f"⏳ **Working**\n\n"
                        f"**Check-in:** {format_datetime(check_in_time, 'Asia/Karachi', '%H:%M:%S')}\n\n"
                        f"**Duration:** {metrics['display_duration']}\n\n"
                        f"**Status:** {metrics['status_label']}\n\n"
                        f"Your shift is currently in progress. Remember to check out when you're done!"
                    )
                else:
                    st.warning("⚠️ Check-in time is unavailable for this active shift.")

    # Payroll Tab
    with tab_payroll:
        st.subheader("💰 Your Earnings")

        # Fetch all completed attendance records (checked-out shifts)
        # Get attendance records from the last 30 days in PKT
        today_pkt = datetime.now(PKT_TZ).date()
        thirty_days_ago = today_pkt - timedelta(days=30)
        all_attendance = attendance_service.get_attendance_by_user(
            user_id=user_id,
            start_date=thirty_days_ago,
            end_date=today_pkt
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
                        st.write(f"**Check-in:** {format_datetime(shift.check_in, 'Asia/Karachi', '%H:%M:%S')}")
                        st.write(f"**Check-out:** {format_datetime(shift.check_out, 'Asia/Karachi', '%H:%M:%S')}")
                        st.write(f"**Status:** {format_attendance_status(shift)}")

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
                value=datetime.now(PKT_TZ).date().replace(day=1),
                key="history_start_date"
            )
        with col2:
            end_date = st.date_input(
                "To Date",
                value=datetime.now(PKT_TZ).date(),
                key="history_end_date"
            )

        if st.button("🔍 Load History", use_container_width=True):
            attendance_records = attendance_service.get_attendance_by_user(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date
            )

            # Generate full date range for the selected period
            date_range = []
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date)
                current_date += timedelta(days=1)

            # Create a mapping of existing attendance records by date
            # Ensure we normalize date objects for reliable comparison
            attendance_by_date = {}
            for record in attendance_records:
                # Normalize to date object if it's a datetime
                record_date = record.date
                if isinstance(record_date, datetime):
                    record_date = record_date.date()
                attendance_by_date[record_date] = record

            # Merge existing records with missing dates (marked as ABSENT)
            full_attendance_list = []
            for check_date in date_range:
                if check_date in attendance_by_date:
                    # Existing record
                    full_attendance_list.append({
                        "date": check_date,
                        "record": attendance_by_date[check_date],
                        "is_absent": False
                    })
                else:
                    # Missing date - inject virtual ABSENT entry
                    full_attendance_list.append({
                        "date": check_date,
                        "record": None,
                        "is_absent": True
                    })

            if not full_attendance_list:
                st.info("No date range selected.")
            else:
                # Display records
                st.write(f"Showing {len(full_attendance_list)} days (including absent days)")

                for item in full_attendance_list:
                    if item["is_absent"]:
                        # Display ABSENT entry
                        with st.expander(
                            f"📅 {format_date(item['date'])} - "
                            f"ABSENT - "
                            f"0.00 hrs"
                        ):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Date:** {format_date(item['date'])}")
                                st.write(f"**Status:** ABSENT")
                            with col2:
                                st.write(f"**Hours:** 0.00 hrs")
                                st.write(f"**Reason:** No attendance record found")
                    else:
                        # Display actual attendance record
                        record = item["record"]
                        with st.expander(
                            f"📅 {format_date(record.date)} - "
                            f"{format_attendance_status(record)} - "
                            f"{format_hours(record.total_hours)}"
                        ):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"**Check-in:** {format_datetime(record.check_in, 'Asia/Karachi', '%H:%M:%S')}")
                                st.write(f"**Check-out:** {format_datetime(record.check_out, 'Asia/Karachi', '%H:%M:%S') if record.check_out else 'Open'}")
                            with col2:
                                st.write(f"**Regular Hours:** {format_hours(record.regular_hours)}")
                                st.write(f"**Overtime Hours:** {format_hours(record.overtime_hours)}")
                                st.write(f"**Status:** {format_attendance_status(record)}")

                # Calculate summary (only from actual records, not ABSENT days)
                actual_records = [item["record"] for item in full_attendance_list if not item["is_absent"]]

                total_regular = sum(
                    r.regular_hours for r in actual_records
                    if r.status != AttendanceStatus.FLAGGED
                )
                total_overtime = sum(
                    r.overtime_hours for r in actual_records
                    if r.status != AttendanceStatus.FLAGGED
                )

                present_days = len(actual_records)
                absent_days = len([item for item in full_attendance_list if item["is_absent"]])

                st.markdown("---")
                st.markdown("### Period Summary")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Days", len(full_attendance_list))
                with col2:
                    st.metric("Present Days", present_days)
                with col3:
                    st.metric("Absent Days", absent_days)
                with col4:
                    st.metric("Total Hours Worked", format_hours(total_regular + total_overtime))
