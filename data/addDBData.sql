CREATE SCHEMA IF NOT EXISTS hr_survey;

DROP TABLE IF EXISTS hr_survey.satisfaction_survey;

CREATE TABLE hr_survey.satisfaction_survey (
    -- Unique ID for each response
    response_id SERIAL PRIMARY KEY,
    employee_email VARCHAR(255) NOT NULL,

    -- Satisfaction Ratings (Enforced 1-5 scale)
    recruitment_score INTEGER CHECK (recruitment_score BETWEEN 1 AND 5),
    benefits_score INTEGER CHECK (benefits_score BETWEEN 1 AND 5),
    communication_score INTEGER CHECK (communication_score BETWEEN 1 AND 5),
    support_score INTEGER CHECK (support_score BETWEEN 1 AND 5),
    development_score INTEGER CHECK (development_score BETWEEN 1 AND 5),
    payroll_score INTEGER CHECK (payroll_score BETWEEN 1 AND 5),
    
    -- Qualitative Feedback
    top_strength TEXT,
    improvement_area TEXT,
    additional_comments TEXT,
    
    -- Metadata
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexing the email for faster lookups if you need to query an employee's history
CREATE INDEX idx_employee_email ON hr_survey.satisfaction_survey(employee_email);

INSERT INTO hr_survey.satisfaction_survey (
    employee_email, 
    recruitment_score, 
    benefits_score, 
    communication_score, 
    support_score, 
    development_score, 
    payroll_score, 
    top_strength, 
    improvement_area, 
    submitted_at
)
SELECT 
    -- Picks a random email from the actual employee table
    e.email,
    
    -- Random scores (1-5)
    floor(random() * 5 + 1)::int,
    floor(random() * 5 + 1)::int,
    floor(random() * 5 + 1)::int,
    floor(random() * 5 + 1)::int,
    floor(random() * 5 + 1)::int,
    floor(random() * 5 + 1)::int,
    
    'Auto-generated positive feedback for ' || e.email,
    'Auto-generated improvement area for ' || e.email,
    
    -- Random date within the last 30 days
    NOW() - (random() * (interval '30 days'))
FROM (
    -- This subquery gets 200 random emails from your existing table
    SELECT email 
    FROM employees.employee 
    ORDER BY random() 
    LIMIT 1000
) AS e;