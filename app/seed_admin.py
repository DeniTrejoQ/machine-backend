import os

from sqlalchemy import select

from .database import SessionLocal
from .models import Employee
from .security import hash_password


def create_initial_admin() -> bool:
    email = os.getenv("INITIAL_ADMIN_EMAIL")
    password = os.getenv("INITIAL_ADMIN_PASSWORD")
    name = os.getenv("INITIAL_ADMIN_NAME", "Administrador")
    if not email or not password:
        return False

    with SessionLocal() as db:
        exists = db.scalar(select(Employee).where(Employee.email == email.lower()))
        if exists:
            return False
        db.add(Employee(name=name, email=email.lower(), password_hash=hash_password(password), role="admin"))
        db.commit()
        return True
