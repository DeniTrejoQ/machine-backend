from sqlalchemy import inspect, text

from .database import engine


def ensure_schema() -> None:
    inspector = inspect(engine)
    if "reviews" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("reviews")}
    statements = []
    if "employee_id" not in existing:
        statements.append("ALTER TABLE reviews ADD COLUMN employee_id INTEGER NULL")
    if "alert_sent" not in existing:
        statements.append("ALTER TABLE reviews ADD COLUMN alert_sent BOOLEAN NOT NULL DEFAULT FALSE")
    if "alert_sent_at" not in existing:
        statements.append("ALTER TABLE reviews ADD COLUMN alert_sent_at TIMESTAMP NULL")

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        if statements and engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "DO $$ BEGIN "
                    "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_reviews_employee_id') THEN "
                    "ALTER TABLE reviews ADD CONSTRAINT fk_reviews_employee_id FOREIGN KEY (employee_id) REFERENCES employees(id); "
                    "END IF; END $$;"
                )
            )
