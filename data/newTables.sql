-- 43 new tables for PostgreSQL (extends existing employees + hr_survey schemas).
-- Requires: employees.employee(id), employees.department(id).

CREATE SCHEMA IF NOT EXISTS payroll;
CREATE SCHEMA IF NOT EXISTS recruitment;
CREATE SCHEMA IF NOT EXISTS training;
CREATE SCHEMA IF NOT EXISTS benefits;
CREATE SCHEMA IF NOT EXISTS assets;
CREATE SCHEMA IF NOT EXISTS compliance;
CREATE SCHEMA IF NOT EXISTS timekeeping;
CREATE SCHEMA IF NOT EXISTS org;
CREATE SCHEMA IF NOT EXISTS projects;
CREATE SCHEMA IF NOT EXISTS expenses;
CREATE SCHEMA IF NOT EXISTS performance;
CREATE SCHEMA IF NOT EXISTS leave_mgmt;
CREATE SCHEMA IF NOT EXISTS vendors;
CREATE SCHEMA IF NOT EXISTS skills;
CREATE SCHEMA IF NOT EXISTS documents;
CREATE SCHEMA IF NOT EXISTS onboarding;
CREATE SCHEMA IF NOT EXISTS announcements;

-- 1–5: payroll
CREATE TABLE IF NOT EXISTS payroll.pay_period (
    id SERIAL PRIMARY KEY,
    period_code VARCHAR(32) NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    pay_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS payroll.pay_run (
    id SERIAL PRIMARY KEY,
    pay_period_id INTEGER NOT NULL REFERENCES payroll.pay_period (id),
    run_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(32) NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS payroll.deduction_type (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    is_pre_tax BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS payroll.employee_deduction (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    deduction_type_id INTEGER NOT NULL REFERENCES payroll.deduction_type (id),
    amount NUMERIC(12, 2) NOT NULL,
    effective_from DATE NOT NULL,
    effective_to DATE
);

CREATE TABLE IF NOT EXISTS payroll.pay_stub (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    pay_run_id INTEGER NOT NULL REFERENCES payroll.pay_run (id),
    gross_pay NUMERIC(12, 2) NOT NULL,
    net_pay NUMERIC(12, 2) NOT NULL,
    issued_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6–10: recruitment
CREATE TABLE IF NOT EXISTS recruitment.job_requisition (
    id SERIAL PRIMARY KEY,
    department_id CHAR(4) REFERENCES employees.department (id),
    title VARCHAR(255) NOT NULL,
    opened_at DATE NOT NULL DEFAULT CURRENT_DATE,
    closed_at DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS recruitment.candidate (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    phone VARCHAR(50),
    resume_url TEXT
);

CREATE TABLE IF NOT EXISTS recruitment.application (
    id SERIAL PRIMARY KEY,
    requisition_id INTEGER NOT NULL REFERENCES recruitment.job_requisition (id),
    candidate_id INTEGER NOT NULL REFERENCES recruitment.candidate (id),
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(32) NOT NULL DEFAULT 'submitted'
);

CREATE TABLE IF NOT EXISTS recruitment.interview (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES recruitment.application (id),
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    interviewer_employee_id INTEGER REFERENCES employees.employee (id),
    outcome VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS recruitment.offer (
    id SERIAL PRIMARY KEY,
    application_id INTEGER NOT NULL REFERENCES recruitment.application (id),
    salary_offered NUMERIC(12, 2),
    valid_until DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending'
);

-- 11–13: training
CREATE TABLE IF NOT EXISTS training.course (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    duration_hours NUMERIC(6, 2)
);

CREATE TABLE IF NOT EXISTS training.enrollment (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    course_id INTEGER NOT NULL REFERENCES training.course (id),
    enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    score NUMERIC(5, 2)
);

CREATE TABLE IF NOT EXISTS training.certification (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    name VARCHAR(255) NOT NULL,
    issuer VARCHAR(255),
    earned_at DATE NOT NULL,
    expires_at DATE
);

-- 14–16: benefits
CREATE TABLE IF NOT EXISTS benefits.benefit_plan (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    plan_type VARCHAR(64) NOT NULL,
    effective_from DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS benefits.employee_enrollment (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    benefit_plan_id INTEGER NOT NULL REFERENCES benefits.benefit_plan (id),
    enrolled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS benefits.dependent (
    id SERIAL PRIMARY KEY,
    employee_enrollment_id INTEGER NOT NULL REFERENCES benefits.employee_enrollment (id),
    first_name VARCHAR(100) NOT NULL,
    birth_date DATE,
    relationship VARCHAR(64)
);

-- 17–18: assets
CREATE TABLE IF NOT EXISTS assets.asset (
    id SERIAL PRIMARY KEY,
    tag VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    purchase_date DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'in_stock'
);

CREATE TABLE IF NOT EXISTS assets.assignment (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER NOT NULL REFERENCES assets.asset (id),
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    assigned_from DATE NOT NULL DEFAULT CURRENT_DATE,
    assigned_to DATE
);

-- 19–20: compliance
CREATE TABLE IF NOT EXISTS compliance.policy (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    version VARCHAR(32) NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS compliance.acknowledgment (
    id SERIAL PRIMARY KEY,
    policy_id INTEGER NOT NULL REFERENCES compliance.policy (id),
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    acknowledged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (policy_id, employee_id)
);

-- 21–22: timekeeping
CREATE TABLE IF NOT EXISTS timekeeping.timesheet (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    week_start DATE NOT NULL,
    submitted_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS timekeeping.time_entry (
    id SERIAL PRIMARY KEY,
    timesheet_id INTEGER NOT NULL REFERENCES timekeeping.timesheet (id),
    work_date DATE NOT NULL,
    hours NUMERIC(5, 2) NOT NULL,
    project_code VARCHAR(64)
);

-- 23–25: org
CREATE TABLE IF NOT EXISTS org.office_location (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(128),
    country VARCHAR(128)
);

CREATE TABLE IF NOT EXISTS org.team (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    department_id CHAR(4) REFERENCES employees.department (id),
    office_location_id INTEGER REFERENCES org.office_location (id)
);

CREATE TABLE IF NOT EXISTS org.team_member (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES org.team (id),
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    role VARCHAR(64),
    from_date DATE NOT NULL DEFAULT CURRENT_DATE,
    to_date DATE
);

-- 26–27: projects
CREATE TABLE IF NOT EXISTS projects.project (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    department_id CHAR(4) REFERENCES employees.department (id),
    start_date DATE,
    end_date DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS projects.project_member (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects.project (id),
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    role VARCHAR(64),
    allocation_pct NUMERIC(5, 2) CHECK (allocation_pct IS NULL OR (allocation_pct >= 0 AND allocation_pct <= 100))
);

-- 28–29: expenses
CREATE TABLE IF NOT EXISTS expenses.expense_report (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    submitted_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    total_amount NUMERIC(12, 2)
);

CREATE TABLE IF NOT EXISTS expenses.expense_line (
    id SERIAL PRIMARY KEY,
    expense_report_id INTEGER NOT NULL REFERENCES expenses.expense_report (id),
    expense_date DATE NOT NULL,
    category VARCHAR(100),
    amount NUMERIC(12, 2) NOT NULL,
    description TEXT
);

-- 30–32: performance
CREATE TABLE IF NOT EXISTS performance.review_cycle (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS performance.review (
    id SERIAL PRIMARY KEY,
    cycle_id INTEGER NOT NULL REFERENCES performance.review_cycle (id),
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    manager_id INTEGER REFERENCES employees.employee (id),
    overall_rating NUMERIC(3, 1),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS performance.goal (
    id SERIAL PRIMARY KEY,
    review_id INTEGER NOT NULL REFERENCES performance.review (id),
    description TEXT NOT NULL,
    target_date DATE,
    status VARCHAR(32) NOT NULL DEFAULT 'open'
);

-- 33–34: leave (schema leave_mgmt — "leave" is reserved keyword concerns avoided)
CREATE TABLE IF NOT EXISTS leave_mgmt.leave_type (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    paid BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS leave_mgmt.leave_request (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    leave_type_id INTEGER NOT NULL REFERENCES leave_mgmt.leave_type (id),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending'
);

-- 35–36: vendors
CREATE TABLE IF NOT EXISTS vendors.vendor (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    contact_email VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS vendors.contract (
    id SERIAL PRIMARY KEY,
    vendor_id INTEGER NOT NULL REFERENCES vendors.vendor (id),
    title VARCHAR(255) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    amount NUMERIC(14, 2)
);

-- 37–38: skills
CREATE TABLE IF NOT EXISTS skills.skill (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS skills.employee_skill (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    skill_id INTEGER NOT NULL REFERENCES skills.skill (id),
    proficiency VARCHAR(32),
    UNIQUE (employee_id, skill_id)
);

-- 39–40: documents
CREATE TABLE IF NOT EXISTS documents.document (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    storage_key TEXT NOT NULL,
    mime_type VARCHAR(128),
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    uploaded_by_employee_id INTEGER REFERENCES employees.employee (id)
);

CREATE TABLE IF NOT EXISTS documents.document_access (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents.document (id),
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_id, employee_id)
);

-- 41–42: onboarding
CREATE TABLE IF NOT EXISTS onboarding.checklist_template (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    role_hint VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS onboarding.onboarding_task (
    id SERIAL PRIMARY KEY,
    employee_id INTEGER NOT NULL REFERENCES employees.employee (id),
    checklist_template_id INTEGER REFERENCES onboarding.checklist_template (id),
    title VARCHAR(255) NOT NULL,
    due_date DATE,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(32) NOT NULL DEFAULT 'pending'
);

-- 43: announcements
CREATE TABLE IF NOT EXISTS announcements.announcement (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    body TEXT,
    published_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    author_employee_id INTEGER REFERENCES employees.employee (id)
);
