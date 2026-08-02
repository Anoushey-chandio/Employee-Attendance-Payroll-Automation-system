```markdown
# Technical Specification Document: Enterprise Payroll & Overtime Auditor System

## 1. Executive Summary & Architecture Overview
This document outlines the architectural and implementation specifications for the **Enterprise Payroll & Attendance Automation System**. Built using Python, Streamlit, Supabase PostgreSQL, and SQLAlchemy 2.0, the platform enforces a clean layered architecture, Object-Oriented Service patterns, strict Role-Based Access Control (RBAC), and automated testing suites.

### Core System Principles
* **Separation of Concerns:** UI Layer (Streamlit Views) -> Service Layer (Business Logic) -> Data Access Layer (SQLAlchemy ORM).
* **Production Resilience:** Strict type-hinting, custom error exceptions, atomic DB transactions, and financial accuracy using `decimal.Decimal`.
* **Zero Sycophancy & Clean Code:** Self-documenting code, zero raw tracebacks in UI, robust validation rules, and reusable OOP services.

---

## 2. Technical Stack Definition
* **Language:** Python 3.10+
* **Frontend Framework:** Streamlit
* **Database:** Supabase PostgreSQL (via Direct `DATABASE_URL` Pooling)
* **ORM & Database Abstraction:** SQLAlchemy 2.0
* **Authentication & Hashing:** Secure Hashing (`passlib` + `bcrypt`) & Supabase Auth integration
* **Financial Calculations:** `decimal.Decimal` (No floating-point arithmetic for currency)
* **Reporting & Exports:** ReportLab (PDF Generation), Pandas (CSV/Excel Audit Exports)
* **Testing Engine:** Pytest, Pytest-Mock

---

## 3. Directory Structure & Modular File Hierarchy

```text
e-payroll-system/
│
├── .env                       # Environment Credentials & Application Flags
├── spec.md                    # Technical Specification Blueprint
├── requirements.txt           # Verified Production Dependencies
├── main.py                    # Streamlit Entrypoint & Router
│
├── config/
│   ├── __init__.py
│   ├── settings.py            # Base Configuration & Env Var Loader
│   └── database.py            # SQLAlchemy Engine & SessionLocal Factory
│
├── models/
│   ├── __init__.py
│   ├── base.py                # Declarative Base Class
│   ├── user.py                # User & Profile DB Models
│   ├── attendance.py          # Attendance & Overtime Log Models
│   └── payroll.py             # Monthly Payroll Run & Payslip Models
│
├── services/
│   ├── __init__.py
│   ├── auth_service.py        # RBAC, Auth Engine & Session Validation
│   ├── attendance_service.py  # Check-in/out, Shifts & Anomaly Detection
│   ├── payroll_engine.py      # Salary Calculation Engine & Tax/Deductions
│   └── export_service.py      # PDF Payslip & Audit CSV Export Generators
│
├── views/
│   ├── __init__.py
│   ├── auth_view.py           # Login / Registration Interface
│   ├── admin_dashboard.py     # Admin Management & Payroll Processing UI
│   └── employee_dashboard.py  # Employee Self-Service & Attendance UI
│
├── utils/
│   ├── __init__.py
│   ├── exceptions.py          # Custom System Exception Hierarchy
│   ├── formatters.py          # Currency, Date & Time Formatting Utilities
│   └── logger.py              # Centralized Application Logging Setup
│
└── tests/
    ├── __init__.py
    ├── conftest.py            # Pytest Fixtures, Mock DB & Client Setup
    ├── test_payroll_engine.py # Financial Calculation Unit Tests
    ├── test_attendance.py     # Attendance & Anomaly Validation Tests
    └── test_auth.py           # Authentication & RBAC Security Tests

```

---

## 4. Database Schema Specifications

### `users` Table

| Column Name | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | String / UUID | Primary Key, Default UUID | Unique user identifier |
| `email` | String(255) | Unique, Not Null | Account login email |
| `password_hash` | String(255) | Not Null | Bcrypted password hash |
| `full_name` | String(100) | Not Null | Employee legal name |
| `role` | Enum | `admin`, `hr`, `employee` | System access role |
| `hourly_rate` | Numeric(10, 2) | Default 0.00 | Base pay rate per hour |
| `is_active` | Boolean | Default True | Account activation state |
| `created_at` | DateTime | Default UTC Now | System registration timestamp |

### `attendance` Table

| Column Name | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | Integer | Primary Key, Auto-Increment | Record ID |
| `user_id` | String / UUID | Foreign Key -> `users.id` | Employee reference |
| `date` | Date | Not Null | Workday date |
| `check_in` | DateTime | Not Null | Clock-in time |
| `check_out` | DateTime | Nullable | Clock-out time |
| `regular_hours` | Numeric(5, 2) | Default 0.00 | Standard hours worked |
| `overtime_hours` | Numeric(5, 2) | Default 0.00 | Overtime hours validated |
| `status` | Enum | `present`, `absent`, `flagged` | Daily attendance status |

### `payroll_runs` Table

| Column Name | Type | Constraints | Description |
| --- | --- | --- | --- |
| `id` | Integer | Primary Key, Auto-Increment | Payroll Record ID |
| `user_id` | String / UUID | Foreign Key -> `users.id` | Employee reference |
| `pay_period_start` | Date | Not Null | Start date of cycle |
| `pay_period_end` | Date | Not Null | End date of cycle |
| `base_salary` | Numeric(12, 2) | Not Null | Calculated base earnings |
| `overtime_pay` | Numeric(12, 2) | Not Null | Overtime earnings |
| `deductions` | Numeric(12, 2) | Default 0.00 | Tax / Policy deductions |
| `net_pay` | Numeric(12, 2) | Not Null | Total payout |
| `status` | Enum | `draft`, `approved`, `paid` | Processing state |

---

## 5. Business Logic, Edge Cases & Error Handling

### A. Financial Calculation Engine (`PayrollEngine`)

1. **Precision Standard:** Floating-point operations for currency are strictly forbidden. All operations must convert floats to `decimal.Decimal('0.00')` before evaluation.
2. **Gross Pay Calculation:**

$$\text{Gross Pay} = (\text{Regular Hours} \times \text{Hourly Rate}) + (\text{Overtime Hours} \times \text{Hourly Rate} \times 1.5)$$


3. **Overtime Rule Engine:**
* Daily regular hours are capped at 8.00 hours.
* Work duration $> 8.00$ hours automatically allocates remaining duration to `overtime_hours`.
* Daily overtime hours are capped at 4.00 hours per day. Any excess duration triggers an anomaly flag (`status='flagged'`) requiring explicit HR override.


4. **Deductions & Net Pay:**

$$\text{Net Pay} = \text{Gross Pay} - \text{Deductions}$$



### B. Attendance Edge Cases & Anomaly Rules

1. **Double Check-In Guard:** The service must reject any check-in request if an unclosed attendance record or existing record already exists for the same `date` and `user_id`.
2. **Unclosed Shift Recovery (Auto-Close):** Attendance logs left unclosed past midnight UTC must be automatically marked as `status='flagged'` with $0.00$ overtime credited until HR review.
3. **Timezone Normalization:** All timestamp data must be converted and saved in UTC in the database, and formatted into local client display time on the UI layer.

### C. Atomic Transactions & Connection Resilience

1. **Atomic Payroll Operations:** Salary calculation, audit logging, and payment status updates must execute within a single atomic database transaction block (`session.begin()`). Any failure forces an immediate `session.rollback()`.
2. **Connection Failure Retry:** The database layer must implement connection retries with exponential backoff if Supabase network pooling temporarily drops.
3. **UI Safe Errors:** Raw database exceptions (e.g., `psycopg2.OperationalError`) must be caught at the service layer and rendered as clean, actionable warnings in Streamlit (`st.error()`).

---

## 6. Security, RBAC & Session Management

1. **Role Access Control:**
* **Employee:** Allowed to access personal check-in/out, view personal attendance logs, and download personal PDF payslips.
* **Admin / HR:** Allowed to access global workforce metrics, update hourly rates, process monthly payroll, review flagged attendance logs, and export CSV audit reports.


2. **Session Security:** User authentication tokens and roles are stored in `st.session_state`. Navigation routes check permissions dynamically via `AuthService.validate_role(required_role)` before rendering page views.

---

## 7. Automated Testing Strategy (Pytest Suite)

The platform includes an automated testing suite under `tests/` covering unit, integration, and mock scenarios:

* **`test_payroll_engine.py`:**
* Exact `Decimal` precision and rounding checks.
* Correct multiplier logic (1.5x) for overtime.
* Deduction and net pay boundary conditions.


* **`test_attendance.py`:**
* Double check-in prevention enforcement.
* Auto-flagging logic for unclosed shifts.
* Overtime daily capping rules ($> 4.00$ hours).


* **`test_auth.py`:**
* Password hashing and verification routines.
* RBAC permission enforcement (blocking non-admin access to HR routes).



---



```

```

```