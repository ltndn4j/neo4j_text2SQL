# Database schema

> PostgreSQL catalog: 50 tables across 18 schemas (employees + hr_survey + extensions).
> Aligns with data/addDBData.sql, data/newTables.sql, and the classic employees dataset.
> employees.* DDL may vary by install; types/PKs below match typical ports and FKs in newTables.sql.

**Engine:** `postgresql`  
**Version note:** Column types reflect project SQL; verify INTEGER vs BIGINT for employees.employee.id on your instance.

## Schemas

### `announcements`

Company-wide or HR announcements.

##### `announcements.announcement`

Published message with optional author employee.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `title` | VARCHAR(255) | no | Headline. |
| `body` | TEXT | yes | Full text. |
| `published_at` | TIMESTAMP WITH TIME ZONE | yes | Publish time. |
| `author_employee_id` | INTEGER | yes | Author if internal. |

**Foreign keys**

- `author_employee_id` → `employees.employee` (id)

### `assets`

Physical or logical assets assigned to employees.

##### `assets.asset`

Asset registry.

- **Primary key:** `id`
- **Unique constraints:** (tag)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `tag` | VARCHAR(64) | no | Asset tag / serial. |
| `name` | VARCHAR(255) | no | Description. |
| `category` | VARCHAR(100) | yes | Asset class. |
| `purchase_date` | DATE | yes | Purchase date. |
| `status` | VARCHAR(32) | no | in_stock, assigned, retired, etc. |

**Foreign keys**

—

##### `assets.assignment`

Asset checked out to an employee for a date range.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `asset_id` | INTEGER | no | Asset. |
| `employee_id` | INTEGER | no | Custodian. |
| `assigned_from` | DATE | no | Assignment start. |
| `assigned_to` | DATE | yes | Assignment end. |

**Foreign keys**

- `asset_id` → `assets.asset` (id)
- `employee_id` → `employees.employee` (id)

### `benefits`

Benefit plans, enrollments, and dependents.

##### `benefits.benefit_plan`

Plan master (medical, dental, etc.).

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `name` | VARCHAR(255) | no | Plan display name. |
| `plan_type` | VARCHAR(64) | no | Category of benefit. |
| `effective_from` | DATE | no | Plan effective date. |

**Foreign keys**

—

##### `benefits.dependent`

Dependent covered under an enrollment.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_enrollment_id` | INTEGER | no | Parent enrollment row. |
| `first_name` | VARCHAR(100) | no | Dependent first name. |
| `birth_date` | DATE | yes | DOB. |
| `relationship` | VARCHAR(64) | yes | Relationship to employee. |

**Foreign keys**

- `employee_enrollment_id` → `benefits.employee_enrollment` (id)

##### `benefits.employee_enrollment`

Employee opted into a plan.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Enrollee. |
| `benefit_plan_id` | INTEGER | no | Plan. |
| `enrolled_at` | TIMESTAMP WITH TIME ZONE | yes | Enrollment timestamp. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `benefit_plan_id` → `benefits.benefit_plan` (id)

### `compliance`

Policies and employee acknowledgments.

##### `compliance.acknowledgment`

Record that an employee acknowledged a policy (unique per policy+employee).

- **Primary key:** `id`
- **Unique constraints:** (policy_id, employee_id)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `policy_id` | INTEGER | no | Policy acknowledged. |
| `employee_id` | INTEGER | no | Acknowledger. |
| `acknowledged_at` | TIMESTAMP WITH TIME ZONE | yes | When signed. |

**Foreign keys**

- `policy_id` → `compliance.policy` (id)
- `employee_id` → `employees.employee` (id)

##### `compliance.policy`

Compliance or HR policy document version.

- **Primary key:** `id`
- **Unique constraints:** (code)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `code` | VARCHAR(64) | no | Stable policy code. |
| `title` | VARCHAR(255) | no | Policy title. |
| `version` | VARCHAR(32) | no | Version label. |
| `published_at` | TIMESTAMP WITH TIME ZONE | yes | Publication time. |

**Foreign keys**

—

### `documents`

Stored files and per-employee access grants.

##### `documents.document`

Metadata for an uploaded file.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `title` | VARCHAR(255) | no | Document title. |
| `storage_key` | TEXT | no | Object store or path key. |
| `mime_type` | VARCHAR(128) | yes | MIME type. |
| `uploaded_at` | TIMESTAMP WITH TIME ZONE | yes | Upload time. |
| `uploaded_by_employee_id` | INTEGER | yes | Uploader. |

**Foreign keys**

- `uploaded_by_employee_id` → `employees.employee` (id)

##### `documents.document_access`

Employee granted access to a document (unique pair).

- **Primary key:** `id`
- **Unique constraints:** (document_id, employee_id)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `document_id` | INTEGER | no | Document. |
| `employee_id` | INTEGER | no | Grantee. |
| `granted_at` | TIMESTAMP WITH TIME ZONE | yes | Grant time. |

**Foreign keys**

- `document_id` → `documents.document` (id)
- `employee_id` → `employees.employee` (id)

### `employees`

Core workforce dimensions—people, departments, history of dept assignments, titles, salaries, and managers.

##### `employees.department`

Organizational units (departments).

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | CHAR(4) | no | Department code (dept_no); referenced by department_employee, department_manager, and extension tables. |
| `dept_name` | VARCHAR | yes | Human-readable department name. |

**Foreign keys**

—

##### `employees.department_employee`

History of which department an employee belonged to over time.
If you need to know the active value, filter the column to_date with '9999-01-01'

- **Primary key:** `employee_id, department_id, from_date`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `employee_id` | INTEGER | no | Employee in the assignment. |
| `department_id` | CHAR(4) | no | Department for this interval. |
| `from_date` | DATE | no | Start of this department membership. |
| `to_date` | DATE | yes | End of membership; null or future date if current. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `department_id` → `employees.department` (id)

##### `employees.department_manager`

History of department managers (which employee managed which department over time).
If you need to know the active value, filter the column to_date with '9999-01-01'

- **Primary key:** `employee_id, department_id, from_date`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `department_id` | CHAR(4) | no | Managed department. |
| `employee_id` | INTEGER | no | Manager’s employee id. |
| `from_date` | DATE | no | Start of management assignment. |
| `to_date` | DATE | yes | End of management assignment. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `department_id` → `employees.department` (id)

##### `employees.employee`

One row per person employed; anchor for most HR and operational facts.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | Surrogate employee identifier (often emp_no in sample databases). |
| `birth_date` | DATE | yes | Date of birth. |
| `first_name` | VARCHAR | yes | Given name. |
| `last_name` | VARCHAR | yes | Family name. |
| `gender` | CHAR(1) | yes | Gender code (dataset-specific). |
| `hire_date` | DATE | yes | Employment start date. |
| `email` | VARCHAR(255) | yes | Work email; join to hr_survey.satisfaction_survey on email when survey rows exist. |

**Foreign keys**

—

##### `employees.salary`

Pay amount history per employee (effective-dated).
If you need to know the active value, filter the column to_date with '9999-01-01'

- **Primary key:** `employee_id, from_date`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `employee_id` | INTEGER | no | Employee receiving the salary. |
| `amount` | INTEGER | yes | Salary for the period (integer units in classic dataset; may be NUMERIC elsewhere). |
| `from_date` | DATE | no | Effective start of this salary row. |
| `to_date` | DATE | yes | Effective end of this salary row. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)

##### `employees.title`

Job title history per employee (effective-dated).
If you need to know the active value, filter the column to_date with '9999-01-01'

- **Primary key:** `employee_id, from_date, title`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `employee_id` | INTEGER | no | Employee holding the title. |
| `title` | VARCHAR | no | Job title text. |
| `from_date` | DATE | no | Title effective from. |
| `to_date` | DATE | yes | Title effective to. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)

### `expenses`

Expense reports and line items.

##### `expenses.expense_line`

Individual expense line on a report.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `expense_report_id` | INTEGER | no | Parent report. |
| `expense_date` | DATE | no | Transaction date. |
| `category` | VARCHAR(100) | yes | Expense category. |
| `amount` | NUMERIC(12,2) | no | Line amount. |
| `description` | TEXT | yes | Notes. |

**Foreign keys**

- `expense_report_id` → `expenses.expense_report` (id)

##### `expenses.expense_report`

Header for submitted employee expenses.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Submitter. |
| `submitted_at` | TIMESTAMP WITH TIME ZONE | yes | Submission time. |
| `status` | VARCHAR(32) | no | Workflow state. |
| `total_amount` | NUMERIC(12,2) | yes | Report total if stored. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)

### `hr_survey`

Employee engagement survey responses (not keyed to employee id; use email to join).

##### `hr_survey.satisfaction_survey`

One row per survey submission with Likert scores and free-text feedback.

- **Primary key:** `response_id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `response_id` | INTEGER | no | SERIAL primary key for each response. |
| `employee_email` | VARCHAR(255) | no | Submitter email; join to employees.employee.email for person-level analytics. |
| `recruitment_score` | INTEGER | yes | Rating 1–5 (CHECK in database). |
| `benefits_score` | INTEGER | yes | Rating 1–5. |
| `communication_score` | INTEGER | yes | Rating 1–5. |
| `support_score` | INTEGER | yes | Rating 1–5. |
| `development_score` | INTEGER | yes | Rating 1–5. |
| `payroll_score` | INTEGER | yes | Rating 1–5. |
| `top_strength` | TEXT | yes | Free-text strength. |
| `improvement_area` | TEXT | yes | Free-text improvement theme. |
| `additional_comments` | TEXT | yes | Optional comments. |
| `submitted_at` | TIMESTAMP WITH TIME ZONE | yes | Submission timestamp; default CURRENT_TIMESTAMP in DDL. |

**Foreign keys**

—

**Logical joins** (not enforced as database FKs)

- Link survey to core HR employee row when emails match.
  - `employee_email` → `employees.employee` (email)
  - *Note:* Not enforced as a database FK; use for query design only.

### `leave_mgmt`

Leave types and employee leave requests (schema leave_mgmt).

##### `leave_mgmt.leave_request`

Employee request for time off.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Requestor. |
| `leave_type_id` | INTEGER | no | Leave kind. |
| `start_date` | DATE | no | Absence start. |
| `end_date` | DATE | no | Absence end. |
| `status` | VARCHAR(32) | no | pending, approved, denied. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `leave_type_id` → `leave_mgmt.leave_type` (id)

##### `leave_mgmt.leave_type`

Catalog of PTO, sick, unpaid, etc.

- **Primary key:** `id`
- **Unique constraints:** (code)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `code` | VARCHAR(32) | no | Short code. |
| `name` | VARCHAR(128) | no | Display name. |
| `paid` | BOOLEAN | no | Paid vs unpaid. |

**Foreign keys**

—

### `onboarding`

Checklist templates and per-employee onboarding tasks.

##### `onboarding.checklist_template`

Reusable onboarding checklist definition.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `name` | VARCHAR(255) | no | Template name. |
| `role_hint` | VARCHAR(100) | yes | Optional targeting hint. |

**Foreign keys**

—

##### `onboarding.onboarding_task`

Concrete task for an employee’s onboarding.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | New hire or transferee. |
| `checklist_template_id` | INTEGER | yes | Source template. |
| `title` | VARCHAR(255) | no | Task title. |
| `due_date` | DATE | yes | Due date. |
| `completed_at` | TIMESTAMP WITH TIME ZONE | yes | Completion time. |
| `status` | VARCHAR(32) | no | pending, done, etc. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `checklist_template_id` → `onboarding.checklist_template` (id)

### `org`

Offices, teams, and team membership.

##### `org.office_location`

Physical or logical office site.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `name` | VARCHAR(255) | no | Site name. |
| `city` | VARCHAR(128) | yes | City. |
| `country` | VARCHAR(128) | yes | Country. |

**Foreign keys**

—

##### `org.team`

Team optionally tied to department and office.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `name` | VARCHAR(255) | no | Team name. |
| `department_id` | CHAR(4) | yes | Owning department. |
| `office_location_id` | INTEGER | yes | Primary office. |

**Foreign keys**

- `department_id` → `employees.department` (id)
- `office_location_id` → `org.office_location` (id)

##### `org.team_member`

Employee membership in a team over time.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `team_id` | INTEGER | no | Team. |
| `employee_id` | INTEGER | no | Member. |
| `role` | VARCHAR(64) | yes | Role on team. |
| `from_date` | DATE | no | Membership start. |
| `to_date` | DATE | yes | Membership end. |

**Foreign keys**

- `team_id` → `org.team` (id)
- `employee_id` → `employees.employee` (id)

### `payroll`

Pay periods, runs, deductions, and pay stubs.

##### `payroll.deduction_type`

Catalog of deduction codes (tax, benefits, etc.).

- **Primary key:** `id`
- **Unique constraints:** (code)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `code` | VARCHAR(64) | no | Stable deduction code. |
| `name` | VARCHAR(255) | no | Display name. |
| `is_pre_tax` | BOOLEAN | no | Whether applied before tax. |

**Foreign keys**

—

##### `payroll.employee_deduction`

Per-employee recurring or fixed deductions.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Employee. |
| `deduction_type_id` | INTEGER | no | Deduction kind. |
| `amount` | NUMERIC(12,2) | no | Deduction amount. |
| `effective_from` | DATE | no | Start date. |
| `effective_to` | DATE | yes | End date if ended. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `deduction_type_id` → `payroll.deduction_type` (id)

##### `payroll.pay_period`

A closed or open payroll calendar window and pay date.

- **Primary key:** `id`
- **Unique constraints:** (period_code)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL surrogate key. |
| `period_code` | VARCHAR(32) | no | Unique business code for the period. |
| `start_date` | DATE | no | Period start. |
| `end_date` | DATE | no | Period end. |
| `pay_date` | DATE | no | Payment date. |
| `status` | VARCHAR(32) | no | e.g. open, closed. |

**Foreign keys**

—

##### `payroll.pay_run`

Execution of payroll for a given pay period.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `pay_period_id` | INTEGER | no | Parent pay period. |
| `run_at` | TIMESTAMP WITH TIME ZONE | yes | When the run was created. |
| `status` | VARCHAR(32) | no | Run lifecycle state. |

**Foreign keys**

- `pay_period_id` → `payroll.pay_period` (id)

##### `payroll.pay_stub`

Individual pay outcome for an employee in a pay run.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Payee. |
| `pay_run_id` | INTEGER | no | Pay run this stub belongs to. |
| `gross_pay` | NUMERIC(12,2) | no | Gross amount. |
| `net_pay` | NUMERIC(12,2) | no | Net pay. |
| `issued_at` | TIMESTAMP WITH TIME ZONE | yes | Issue timestamp. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `pay_run_id` → `payroll.pay_run` (id)

### `performance`

Review cycles, reviews, and goals (schema name performance in PostgreSQL).

##### `performance.goal`

Goal attached to a performance review.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `review_id` | INTEGER | no | Parent review. |
| `description` | TEXT | no | Goal text. |
| `target_date` | DATE | yes | Target completion. |
| `status` | VARCHAR(32) | no | open, done, etc. |

**Foreign keys**

- `review_id` → `performance.review` (id)

##### `performance.review`

One employee review in a cycle; manager is another employee.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `cycle_id` | INTEGER | no | Review cycle. |
| `employee_id` | INTEGER | no | Reviewee. |
| `manager_id` | INTEGER | yes | Reviewer (manager). |
| `overall_rating` | NUMERIC(3,1) | yes | Summary rating. |
| `completed_at` | TIMESTAMP WITH TIME ZONE | yes | Completion time. |

**Foreign keys**

- `cycle_id` → `performance.review_cycle` (id)
- `employee_id` → `employees.employee` (id)
- `manager_id` → `employees.employee` (id)

##### `performance.review_cycle`

Named performance period (e.g. annual cycle).

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `name` | VARCHAR(255) | no | Cycle label. |
| `period_start` | DATE | no | Cycle start. |
| `period_end` | DATE | no | Cycle end. |

**Foreign keys**

—

### `projects`

Internal projects and staffing.

##### `projects.project`

Project master with optional department owner.

- **Primary key:** `id`
- **Unique constraints:** (code)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `code` | VARCHAR(64) | no | Unique project code. |
| `name` | VARCHAR(255) | no | Project name. |
| `department_id` | CHAR(4) | yes | Sponsoring department. |
| `start_date` | DATE | yes | Planned or actual start. |
| `end_date` | DATE | yes | Planned or actual end. |
| `status` | VARCHAR(32) | no | active, closed, etc. |

**Foreign keys**

- `department_id` → `employees.department` (id)

##### `projects.project_member`

Employee allocation to a project.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `project_id` | INTEGER | no | Project. |
| `employee_id` | INTEGER | no | Contributor. |
| `role` | VARCHAR(64) | yes | Project role. |
| `allocation_pct` | NUMERIC(5,2) | yes | FTE percent 0–100. |

**Foreign keys**

- `project_id` → `projects.project` (id)
- `employee_id` → `employees.employee` (id)

### `recruitment`

Requisitions, candidates, applications, interviews, and offers.

##### `recruitment.application`

Candidate applied to a specific requisition.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `requisition_id` | INTEGER | no | Target job. |
| `candidate_id` | INTEGER | no | Applicant. |
| `applied_at` | TIMESTAMP WITH TIME ZONE | yes | Application time. |
| `status` | VARCHAR(32) | no | Application state. |

**Foreign keys**

- `requisition_id` → `recruitment.job_requisition` (id)
- `candidate_id` → `recruitment.candidate` (id)

##### `recruitment.candidate`

Person in the talent pipeline (may not be an employee).

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `email` | VARCHAR(255) | no | Contact email. |
| `first_name` | VARCHAR(100) | yes | Given name. |
| `last_name` | VARCHAR(100) | yes | Family name. |
| `phone` | VARCHAR(50) | yes | Phone. |
| `resume_url` | TEXT | yes | Link or path to resume. |

**Foreign keys**

—

##### `recruitment.interview`

Scheduled interview for an application.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `application_id` | INTEGER | no | Application being interviewed. |
| `scheduled_at` | TIMESTAMP WITH TIME ZONE | no | Interview slot. |
| `interviewer_employee_id` | INTEGER | yes | Internal interviewer. |
| `outcome` | VARCHAR(64) | yes | Result summary. |

**Foreign keys**

- `application_id` → `recruitment.application` (id)
- `interviewer_employee_id` → `employees.employee` (id)

##### `recruitment.job_requisition`

Open or closed role tied to a department.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `department_id` | CHAR(4) | yes | Hiring department. |
| `title` | VARCHAR(255) | no | Role title. |
| `opened_at` | DATE | no | Requisition open date. |
| `closed_at` | DATE | yes | Close date if closed. |
| `status` | VARCHAR(32) | no | Pipeline state. |

**Foreign keys**

- `department_id` → `employees.department` (id)

##### `recruitment.offer`

Offer extended from an application.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `application_id` | INTEGER | no | Source application. |
| `salary_offered` | NUMERIC(12,2) | yes | Proposed compensation. |
| `valid_until` | DATE | yes | Offer expiry. |
| `status` | VARCHAR(32) | no | accepted, declined, pending, etc. |

**Foreign keys**

- `application_id` → `recruitment.application` (id)

### `skills`

Skill dictionary and employee proficiency.

##### `skills.employee_skill`

Proficiency of an employee in a skill (unique pair).

- **Primary key:** `id`
- **Unique constraints:** (employee_id, skill_id)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Employee. |
| `skill_id` | INTEGER | no | Skill. |
| `proficiency` | VARCHAR(32) | yes | e.g. beginner, expert. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `skill_id` → `skills.skill` (id)

##### `skills.skill`

Canonical skill or competency.

- **Primary key:** `id`
- **Unique constraints:** (code)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `code` | VARCHAR(64) | no | Skill code. |
| `name` | VARCHAR(255) | no | Skill name. |

**Foreign keys**

—

### `timekeeping`

Weekly timesheets and daily entries.

##### `timekeeping.time_entry`

Hours booked on a given day within a timesheet.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `timesheet_id` | INTEGER | no | Parent timesheet. |
| `work_date` | DATE | no | Worked date. |
| `hours` | NUMERIC(5,2) | no | Hours worked. |
| `project_code` | VARCHAR(64) | yes | Optional project or cost code. |

**Foreign keys**

- `timesheet_id` → `timekeeping.timesheet` (id)

##### `timekeeping.timesheet`

Employee timesheet for a week.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Submitter. |
| `week_start` | DATE | no | Week anchor date. |
| `submitted_at` | TIMESTAMP WITH TIME ZONE | yes | Submission time. |
| `status` | VARCHAR(32) | no | draft, submitted, approved. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)

### `training`

Courses, enrollments, and certifications.

##### `training.certification`

Credential earned by an employee.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Holder. |
| `name` | VARCHAR(255) | no | Certification name. |
| `issuer` | VARCHAR(255) | yes | Issuing body. |
| `earned_at` | DATE | no | Award date. |
| `expires_at` | DATE | yes | Expiry if applicable. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)

##### `training.course`

Training catalog entry.

- **Primary key:** `id`
- **Unique constraints:** (code)

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `code` | VARCHAR(64) | no | Unique course code. |
| `title` | VARCHAR(255) | no | Course name. |
| `duration_hours` | NUMERIC(6,2) | yes | Estimated duration. |

**Foreign keys**

—

##### `training.enrollment`

Employee registered for a course.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `employee_id` | INTEGER | no | Learner. |
| `course_id` | INTEGER | no | Course. |
| `enrolled_at` | TIMESTAMP WITH TIME ZONE | yes | Sign-up time. |
| `completed_at` | TIMESTAMP WITH TIME ZONE | yes | Completion time. |
| `score` | NUMERIC(5,2) | yes | Assessment score if any. |

**Foreign keys**

- `employee_id` → `employees.employee` (id)
- `course_id` → `training.course` (id)

### `vendors`

Third-party vendors and contracts.

##### `vendors.contract`

Agreement with a vendor.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `vendor_id` | INTEGER | no | Vendor. |
| `title` | VARCHAR(255) | no | Contract title. |
| `start_date` | DATE | no | Effective start. |
| `end_date` | DATE | yes | Expiry. |
| `amount` | NUMERIC(14,2) | yes | Contract value. |

**Foreign keys**

- `vendor_id` → `vendors.vendor` (id)

##### `vendors.vendor`

Supplier or partner master.

- **Primary key:** `id`
- **Unique constraints:** —

| Column | Type | Nullable | Description |
| --- | --- | --- | --- |
| `id` | INTEGER | no | SERIAL primary key. |
| `name` | VARCHAR(255) | no | Vendor legal or trade name. |
| `category` | VARCHAR(100) | yes | Vendor segment. |
| `contact_email` | VARCHAR(255) | yes | Primary contact email. |

**Foreign keys**

—

## Join cheatsheet

_Quick join reference (same information as foreign keys above; useful for LLM prompts)._  

- employees.department_employee → employees.employee ON employee_id = employee.id
- employees.department_employee → employees.department ON department_id = department.id
- employees.department_manager → employees.employee ON employee_id = employee.id
- employees.department_manager → employees.department ON department_id = department.id
- employees.salary → employees.employee ON employee_id = employee.id
- employees.title → employees.employee ON employee_id = employee.id
- hr_survey.satisfaction_survey → employees.employee ON employee_email = employee.email (logical)
- payroll.pay_run → payroll.pay_period ON pay_period_id = pay_period.id
- payroll.employee_deduction → employees.employee + payroll.deduction_type
- payroll.pay_stub → employees.employee + payroll.pay_run
- recruitment.application → recruitment.job_requisition + recruitment.candidate
- recruitment.interview → recruitment.application; interviewer_employee_id → employees.employee
- recruitment.offer → recruitment.application
- training.enrollment → employees.employee + training.course
- benefits.dependent → benefits.employee_enrollment → benefits.benefit_plan + employees.employee
- assets.assignment → assets.asset + employees.employee
- compliance.acknowledgment → compliance.policy + employees.employee
- timekeeping.time_entry → timekeeping.timesheet → employees.employee
- org.team → employees.department + org.office_location
- org.team_member → org.team + employees.employee
- projects.project_member → projects.project → employees.department
- expenses.expense_line → expenses.expense_report → employees.employee
- performance.goal → performance.review → performance.review_cycle; review.manager_id → employees.employee
- leave_mgmt.leave_request → leave_mgmt.leave_type + employees.employee
- vendors.contract → vendors.vendor
- skills.employee_skill → skills.skill + employees.employee
- documents.document_access → documents.document + employees.employee
- onboarding.onboarding_task → onboarding.checklist_template + employees.employee
- announcements.announcement.author_employee_id → employees.employee

**Table count:** 50
