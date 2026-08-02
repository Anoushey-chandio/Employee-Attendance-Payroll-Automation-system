"""Streamlit UI views for the Enterprise Payroll System."""

from .admin_dashboard import render_admin_dashboard
from .auth_view import render_auth_view
from .employee_dashboard import render_employee_dashboard

__all__ = [
    "render_auth_view",
    "render_admin_dashboard",
    "render_employee_dashboard",
]
