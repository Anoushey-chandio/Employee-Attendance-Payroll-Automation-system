# Enterprise Payroll & Overtime Auditor System

A production-ready, modular Enterprise Payroll & Attendance Automation System built with Python, Streamlit, Supabase PostgreSQL, and SQLAlchemy 2.0.

## Features

- **Role-Based Access Control (RBAC)**: Admin, HR, and Employee roles with hierarchical permissions
- **Time Tracking**: Employee check-in/out with automatic overtime calculation
- **Payroll Processing**: Automated salary calculation with Decimal precision for financial accuracy
- **Anomaly Detection**: Auto-flagging of excessive overtime and unclosed shifts
- **Export Capabilities**: PDF payslips and CSV audit reports
- **Comprehensive Testing**: 71 automated tests with 100% pass rate

## Architecture

```
├── config/              # Configuration & database setup
├── models/              # SQLAlchemy ORM models
├── services/            # Business logic layer
├── views/               # Streamlit UI components
├── utils/               # Utilities (logging, formatting, exceptions)
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
   
   The `.env` file is already configured with Supabase credentials:
   ```
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

### First-Time Setup

1. Launch the application
2. Register a new account on the "Register" tab
3. Initial users are created as Employees

### Admin Users

To create an admin user, you'll need to:
1. Register as an employee first
2. Manually update the user role in the database to "admin", or
3. Have an existing admin create your account through the Admin Dashboard

### Employee Features

- **Attendance Tab**: Check in/out for work shifts
- **Payroll Tab**: View payslips and download PDF
- **History Tab**: Review past attendance records

### Admin Features

- **Users Tab**: Create/manage users, update hourly rates
- **Payroll Tab**: Process payroll batches, approve payments
- **Attendance Tab**: Monitor open shifts
- **Flagged Records Tab**: Review and approve anomalies
- **Reports Tab**: Export CSV reports for auditing

## Business Rules

### Attendance
- Regular hours capped at **8 hours/day**
- Overtime calculated at **1.5x** hourly rate
- Overtime capped at **4 hours/day**
- Exceeding caps triggers auto-flagging for HR review
- Unclosed shifts past midnight are auto-flagged

### Payroll Calculation
- **Gross Pay** = (Regular Hours × Rate) + (OT Hours × Rate × 1.5)
- **Net Pay** = Gross Pay - Deductions
- All calculations use `Decimal` for financial precision
- No floating-point arithmetic

### Security
- Passwords hashed with bcrypt
- Role-based access control enforced at service layer
- Session-based authentication via Streamlit

## Testing

The system includes comprehensive test coverage:

- **Authentication Tests** (22 tests): User registration, login, RBAC
- **Attendance Tests** (20 tests): Check-in/out, overtime logic, anomaly detection
- **Payroll Engine Tests** (29 tests): Financial calculations, batch processing

All tests validate:
- Decimal precision for financial accuracy
- Edge case handling (double check-in, negative pay, etc.)
- Business rule enforcement
- Error handling and validation

## Technology Stack

- **Framework**: Streamlit 1.31.0
- **ORM**: SQLAlchemy 2.0.25
- **Database**: PostgreSQL (via Supabase)
- **Authentication**: Passlib + Bcrypt
- **PDF Generation**: ReportLab 4.0.9
- **Data Export**: Pandas 2.1.4
- **Testing**: Pytest 7.4.4

## Database Schema

### users
- id, email, password_hash, full_name, role, hourly_rate, is_active, created_at

### attendance
- id, user_id, date, check_in, check_out, regular_hours, overtime_hours, status

### payroll_runs
- id, user_id, pay_period_start, pay_period_end, base_salary, overtime_pay, deductions, net_pay, status

## Development

### Code Style
- Strict Python type hints
- PEP 8 compliant
- SQLAlchemy 2.0 OOP patterns
- Clean separation of concerns

### Error Handling
- Custom exception hierarchy
- No raw tracebacks in UI
- Atomic database transactions
- Connection retry with exponential backoff

## License

Enterprise Payroll System - Internal Use

## Support

For issues or questions, contact the development team.
