"""Export service for generating PDF payslips and CSV audit reports.

Provides functionality to export payroll data in various formats for reporting.
"""

from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from models.attendance import Attendance
from models.payroll import PayrollRun
from models.user import User
from utils.formatters import format_currency, format_date, format_hours
from utils.logger import get_logger

logger = get_logger(__name__)


class ExportService:
    """Export service for generating reports and documents."""

    @staticmethod
    def generate_payslip_pdf(payroll_run: PayrollRun) -> BytesIO:
        """
        Generate PDF payslip for a payroll run.

        Args:
            payroll_run: PayrollRun object with user relationship loaded

        Returns:
            BytesIO buffer containing PDF document
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Title
        title = Paragraph(
            "<b>PAYSLIP</b>",
            styles['Title']
        )
        elements.append(title)
        elements.append(Spacer(1, 0.3 * inch))

        # Employee Information
        employee_info = [
            ["Employee Name:", payroll_run.user.full_name],
            ["Employee ID:", payroll_run.user_id],
            ["Email:", payroll_run.user.email],
            ["Pay Period:", f"{format_date(payroll_run.pay_period_start)} to {format_date(payroll_run.pay_period_end)}"],
        ]

        info_table = Table(employee_info, colWidths=[2 * inch, 4 * inch])
        info_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.4 * inch))

        # Earnings Section
        earnings_header = Paragraph("<b>EARNINGS</b>", styles['Heading2'])
        elements.append(earnings_header)
        elements.append(Spacer(1, 0.1 * inch))

        earnings_data = [
            ["Description", "Amount"],
            ["Base Salary", format_currency(payroll_run.base_salary)],
            ["Overtime Pay", format_currency(payroll_run.overtime_pay)],
            ["<b>Gross Pay</b>", f"<b>{format_currency(payroll_run.gross_pay)}</b>"],
        ]

        earnings_table = Table(earnings_data, colWidths=[4 * inch, 2 * inch])
        earnings_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(earnings_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Deductions Section
        deductions_header = Paragraph("<b>DEDUCTIONS</b>", styles['Heading2'])
        elements.append(deductions_header)
        elements.append(Spacer(1, 0.1 * inch))

        deductions_data = [
            ["Description", "Amount"],
            ["Total Deductions", format_currency(payroll_run.deductions)],
        ]

        deductions_table = Table(deductions_data, colWidths=[4 * inch, 2 * inch])
        deductions_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(deductions_table)
        elements.append(Spacer(1, 0.3 * inch))

        # Net Pay Section
        net_pay_data = [
            ["<b>NET PAY</b>", f"<b>{format_currency(payroll_run.net_pay)}</b>"],
        ]

        net_pay_table = Table(net_pay_data, colWidths=[4 * inch, 2 * inch])
        net_pay_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, -1), 'Helvetica-Bold', 12),
            ('BACKGROUND', (0, 0), (-1, -1), colors.lightgreen),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(net_pay_table)
        elements.append(Spacer(1, 0.5 * inch))

        # Footer
        footer = Paragraph(
            "<i>This is a computer-generated payslip. No signature required.</i>",
            styles['Normal']
        )
        elements.append(footer)

        # Build PDF
        doc.build(elements)
        buffer.seek(0)

        logger.info(f"PDF payslip generated for payroll_id={payroll_run.id}")
        return buffer

    @staticmethod
    def generate_attendance_csv(
        attendance_records: List[Attendance],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> BytesIO:
        """
        Generate CSV export of attendance records.

        Args:
            attendance_records: List of Attendance objects
            start_date: Optional start date for report title
            end_date: Optional end date for report title

        Returns:
            BytesIO buffer containing CSV data
        """
        # Prepare data for DataFrame
        data = []
        for record in attendance_records:
            data.append({
                "Attendance ID": record.id,
                "Employee ID": record.user_id,
                "Employee Name": record.user.full_name,
                "Email": record.user.email,
                "Date": format_date(record.date),
                "Check In": record.check_in.strftime("%Y-%m-%d %H:%M:%S"),
                "Check Out": record.check_out.strftime("%Y-%m-%d %H:%M:%S") if record.check_out else "Open",
                "Regular Hours": float(record.regular_hours),
                "Overtime Hours": float(record.overtime_hours),
                "Total Hours": float(record.total_hours),
                "Status": record.status.value.upper()
            })

        # Create DataFrame
        df = pd.DataFrame(data)

        # Export to CSV buffer
        buffer = BytesIO()
        df.to_csv(buffer, index=False, encoding='utf-8')
        buffer.seek(0)

        logger.info(f"CSV attendance report generated: {len(attendance_records)} records")
        return buffer

    @staticmethod
    def generate_payroll_csv(
        payroll_runs: List[PayrollRun],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> BytesIO:
        """
        Generate CSV export of payroll runs.

        Args:
            payroll_runs: List of PayrollRun objects
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering

        Returns:
            BytesIO buffer containing CSV data
        """
        # Prepare data for DataFrame
        data = []
        for payroll in payroll_runs:
            data.append({
                "Payroll ID": payroll.id,
                "Employee ID": payroll.user_id,
                "Employee Name": payroll.user.full_name,
                "Email": payroll.user.email,
                "Pay Period Start": format_date(payroll.pay_period_start),
                "Pay Period End": format_date(payroll.pay_period_end),
                "Base Salary": float(payroll.base_salary),
                "Overtime Pay": float(payroll.overtime_pay),
                "Gross Pay": float(payroll.gross_pay),
                "Deductions": float(payroll.deductions),
                "Net Pay": float(payroll.net_pay),
                "Status": payroll.status.value.upper()
            })

        # Create DataFrame
        df = pd.DataFrame(data)

        # Export to CSV buffer
        buffer = BytesIO()
        df.to_csv(buffer, index=False, encoding='utf-8')
        buffer.seek(0)

        logger.info(f"CSV payroll report generated: {len(payroll_runs)} records")
        return buffer

    @staticmethod
    def generate_employee_summary_csv(users: List[User]) -> BytesIO:
        """
        Generate CSV summary of all employees.

        Args:
            users: List of User objects

        Returns:
            BytesIO buffer containing CSV data
        """
        # Prepare data for DataFrame
        data = []
        for user in users:
            data.append({
                "Employee ID": user.id,
                "Full Name": user.full_name,
                "Email": user.email,
                "Role": user.role.value.upper(),
                "Hourly Rate": float(user.hourly_rate),
                "Is Active": "Yes" if user.is_active else "No",
                "Created At": user.created_at.strftime("%Y-%m-%d")
            })

        # Create DataFrame
        df = pd.DataFrame(data)

        # Export to CSV buffer
        buffer = BytesIO()
        df.to_csv(buffer, index=False, encoding='utf-8')
        buffer.seek(0)

        logger.info(f"CSV employee summary generated: {len(users)} employees")
        return buffer
