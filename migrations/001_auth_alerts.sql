CREATE TABLE IF NOT EXISTS employees (
    id SERIAL PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'analyst',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE reviews ADD COLUMN IF NOT EXISTS employee_id INTEGER NULL;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS alert_sent BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE reviews ADD COLUMN IF NOT EXISTS alert_sent_at TIMESTAMP NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_reviews_employee_id') THEN
        ALTER TABLE reviews
        ADD CONSTRAINT fk_reviews_employee_id
        FOREIGN KEY (employee_id) REFERENCES employees(id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_reviews_employee_id ON reviews(employee_id);
CREATE INDEX IF NOT EXISTS ix_employees_email ON employees(email);
