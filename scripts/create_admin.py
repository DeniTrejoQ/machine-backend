import argparse
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.app.database import Base, SessionLocal, engine
from backend.app.migrations import ensure_schema
from backend.app.models import Employee
from backend.app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Crear el primer usuario admin de ELEMENT ELITE FLEET")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    ensure_schema()

    with SessionLocal() as db:
        exists = db.scalar(select(Employee).where(Employee.email == args.email.lower()))
        if exists:
            raise SystemExit("Ya existe un empleado con ese email.")
        db.add(
            Employee(
                name=args.name,
                email=args.email.lower(),
                password_hash=hash_password(args.password),
                role="admin",
            )
        )
        db.commit()
    print("Admin creado correctamente.")


if __name__ == "__main__":
    main()
