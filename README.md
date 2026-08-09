```markdown
# Enterprise Payroll & Overtime Auditor System

A production-ready, modular Enterprise Payroll & Attendance Automation System built with Python, Streamlit, Supabase PostgreSQL, and SQLAlchemy 2.0.

## Features

- **Role-Based Access Control (RBAC)**: Admin, HR, and Employee roles with hierarchical permissions.
- **Time Tracking**: Employee check-in/out with real-time status updates (`PRESENT (In Progress)`, `PRESENT (Shift Completed)`, `ABSENT`).
- **Monthly Payroll Consolidation**: Clean 1-card per employee view per month with automated duplicate draft handling.
- **Ignored Shift Exclusion**: Attendance marked as `IGNORED` strictly contributes `0.00` hours and `0.00 PKR` to gross/net pay.
- **Anomaly Detection**: Auto-flagging of excessive overtime and unclosed shifts for admin/HR review.
- **Export & Management Capabilities**: PDF payslips, CSV audit reports, and manual draft deletion/purge controls.
- **Comprehensive Testing**: 83 automated tests with a 100% pass rate.

## Architecture


```

├── config/              # Configuration & database setup
├── models/              # SQLAlchemy ORM models
├── services/            # Business logic layer (payroll, attendance, auth)
├── views/               # Streamlit UI components (admin, HR, employee, personal portal)
├── utils/               # Utilities (logging, formatting, custom exceptions)
├── tests/               # Pytest test suite
├── main.py              # Application entrypoint
└── requirements.txt     # Production dependencies

```

## Installation

1. **Clone and navigate to the project:**
   ```bash
   cd Payroll-system

```

2. **Install dependencies:**
```bash
pip install -r requirements.txt

```


3. **Configure environment variables:**
Ensure `.env` contains your database and app configurations:
```env
DATABASE_URL=postgresql://...
SUPABASE_URL=https://...
SUPABASE_KEY=...
SECRET_KEY=...
APP_ENV=production
USE_LOCAL_SQLITE=False

```



## Running the Application

### Start the Streamlit Application

```bash
streamlit run main.py

```

The application will be available at `http://localhost:8501`

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test file
pytest tests/test_payroll_engine.py -v

```

## Usage Guide

### Employee Features

* **Personal Portal**: Continuous daily shift check-in/out.
* **Payroll Tab**: View monthly payslips and download PDF files.
* **History Tab**: Review complete attendance logs with detailed status breakdown.

### Admin & HR Features

* **Users Tab**: Create/manage user roles, activate/deactivate accounts, and update hourly rates.
* **Payroll Tab**: Process monthly batch payrolls, clean up duplicate drafts, recalculate drafts on attendance updates, and purge redundant runs.
* **Attendance Tab**: Monitor real-time shifts and load historical records.
* **Flagged Records Tab**: Audit excessive overtime and explicitly approve or ignore flagged attendance shifts.
* **Reports Tab**: Export aggregated CSV audit reports.

## Business Rules

### Attendance

* Regular hours capped at **8 hours/day**.
* Overtime calculated at **1.5x** hourly rate.
* Overtime capped at **4 hours/day**.
* Exceeding caps triggers auto-flagging for HR/Admin review.
* Attendance marked as **IGNORED** is excluded from payable hours.

### Payroll Calculation

* **Gross Pay** = (Regular Hours × Rate) + (OT Hours × Rate × 1.5)
* **Net Pay** = Gross Pay - Deductions
* All financial logic uses Python's `Decimal` module for precision (no floating-point rounding errors).
* Batch generation overwrites previous draft states for the same month to ensure strict single-card presentation per user.

## Technology Stack

* **Framework**: Streamlit 1.31.0
* **ORM**: SQLAlchemy 2.0.25
* **Database**: PostgreSQL (via Supabase)
* **Authentication**: Passlib + Bcrypt
* **PDF Generation**: ReportLab 4.0.9
* **Data Export**: Pandas 2.1.4
* **Testing**: Pytest 7.4.4

## Testing

The system is validated by **83 unit and integration tests** covering:

* Authentication & RBAC permissions
* Check-in/out continuous shift workflows & status rendering
* Financial accuracy, Decimal rounding, and IGNORED shift exclusions
* Batch re-processing, draft deduplication, and database atomic transactions

## License

Enterprise Payroll System - Internal Use

```

```