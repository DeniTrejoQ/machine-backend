from datetime import date, datetime
from io import BytesIO

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .database import Base, engine, get_db
from .email_service import send_churn_alert_email
from .migrations import ensure_schema
from .ml import ModelCompatibilityError, get_model_warning, load_artifacts, predict, recommendation_for
from .models import Employee, Review
from .schemas import (
    ChangePasswordRequest,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    LoginRequest,
    MessageResponse,
    PredictRequest,
    PredictionResponse,
    ReviewOut,
    TokenResponse,
)
from .security import VALID_ROLES, create_access_token, get_current_employee, hash_password, require_admin, verify_password
from .seed_admin import create_initial_admin


REQUIRED_COLUMNS = [
    "Año",
    "Trimestre",
    "Fecha",
    "Mes",
    "Fuente",
    "ID",
    "Comentario",
    "Sentimiento",
    "Categoria",
    "Subcategoria",
    "Producto",
    "Detalle",
    "Clasificacion",
]

app = FastAPI(title="ELEMENT ELITE FLEET API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    create_initial_admin()
    load_artifacts()


def parse_date(value: object) -> date | None:
    if pd.isna(value) or value == "":
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.date()


def clean_value(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def review_from_row(
    row: pd.Series,
    allow_prediction_fallback: bool = False,
    employee: Employee | None = None,
) -> tuple[Review, str | None]:
    payload = {
        "comment": clean_value(row.get("Comentario")),
        "category": clean_value(row.get("Categoria")),
        "subcategory": clean_value(row.get("Subcategoria")),
        "sentiment": clean_value(row.get("Sentimiento")),
        "product": clean_value(row.get("Producto")),
        "detail": clean_value(row.get("Detalle")),
    }
    prediction_warning = None
    try:
        predicted, confidence = predict(payload)
    except ModelCompatibilityError as exc:
        if not allow_prediction_fallback:
            raise
        predicted = clean_value(row.get("Clasificacion")) or "Pendiente de prediccion"
        confidence = None
        prediction_warning = str(exc)

    review = Review(
        year=int(row["Año"]) if not pd.isna(row.get("Año")) else None,
        quarter=clean_value(row.get("Trimestre")),
        date=parse_date(row.get("Fecha")),
        month=clean_value(row.get("Mes")),
        source=clean_value(row.get("Fuente")),
        external_id=clean_value(row.get("ID")),
        comment=payload["comment"],
        sentiment=payload["sentiment"],
        category=payload["category"],
        subcategory=payload["subcategory"],
        product=payload["product"],
        detail=payload["detail"],
        original_classification=clean_value(row.get("Clasificacion")),
        predicted_classification=predicted,
        prediction_confidence=confidence,
        employee_id=employee.id if employee else None,
    )
    return review, prediction_warning


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    employee = db.scalar(select(Employee).where(Employee.email == payload.email.lower()))
    if employee is None or not verify_password(payload.password, employee.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales invalidas")
    return TokenResponse(access_token=create_access_token(employee))


@app.get("/auth/me", response_model=EmployeeOut)
def me(employee: Employee = Depends(get_current_employee)) -> Employee:
    return employee


@app.post("/auth/register-employee", response_model=EmployeeOut)
def register_employee(
    payload: EmployeeCreate,
    _: Employee = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Employee:
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Rol invalido. Roles permitidos: {', '.join(sorted(VALID_ROLES))}")
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="La contrasena debe tener al menos 8 caracteres")
    exists = db.scalar(select(Employee.id).where(Employee.email == payload.email.lower()))
    if exists:
        raise HTTPException(status_code=409, detail="Ya existe un empleado con ese email")

    employee = Employee(
        name=payload.name.strip(),
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


@app.post("/auth/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> MessageResponse:
    if not verify_password(payload.current_password, employee.password_hash):
        raise HTTPException(status_code=400, detail="La contrasena actual no es correcta")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="La nueva contrasena y la confirmacion no coinciden")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nueva contrasena debe tener al menos 8 caracteres")

    employee.password_hash = hash_password(payload.new_password)
    db.add(employee)
    db.commit()
    return MessageResponse(message="Contrasena actualizada correctamente")


@app.get("/employees", response_model=list[EmployeeOut])
def list_employees(
    _: Employee = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[Employee]:
    return list(db.scalars(select(Employee).order_by(Employee.created_at.desc())))


@app.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    _: Employee = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    if payload.email is not None:
        email = payload.email.lower().strip()
        exists = db.scalar(select(Employee.id).where(Employee.email == email, Employee.id != employee_id))
        if exists:
            raise HTTPException(status_code=409, detail="Ya existe un empleado con ese email")
        employee.email = email
    if payload.name is not None:
        employee.name = payload.name.strip()
    if payload.role is not None:
        if payload.role not in VALID_ROLES:
            raise HTTPException(status_code=400, detail=f"Rol invalido. Roles permitidos: {', '.join(sorted(VALID_ROLES))}")
        employee.role = payload.role

    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


@app.delete("/employees/{employee_id}", response_model=MessageResponse)
def delete_employee(
    employee_id: int,
    current_employee: Employee = Depends(require_admin),
    db: Session = Depends(get_db),
) -> MessageResponse:
    if employee_id == current_employee.id:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propio usuario")
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    for review in db.scalars(select(Review).where(Review.employee_id == employee_id)):
        review.employee_id = None
        db.add(review)
    db.delete(employee)
    db.commit()
    return MessageResponse(message="Empleado eliminado correctamente")


def is_high_risk(classification: str, confidence: float | None) -> bool:
    normalized = classification.lower()
    return "abandono" in normalized or "alto riesgo" in normalized or (confidence is not None and confidence >= 0.5)


@app.post("/predict", response_model=PredictionResponse)
def predict_review(
    payload: PredictRequest,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> PredictionResponse:
    try:
        predicted, confidence = predict(payload.model_dump())
    except ModelCompatibilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    recommendation = recommendation_for(predicted, confidence)
    detected_at = datetime.utcnow()
    alert_sent = False
    alert_error = None

    if is_high_risk(predicted, confidence):
        customer_reference = payload.customer_name or payload.customer_id
        email_result = send_churn_alert_email(
            to_email=employee.email,
            employee_name=employee.name,
            customer_reference=customer_reference,
            comment=payload.comentario,
            category=payload.categoria,
            subcategory=payload.subcategoria,
            classification=predicted,
            confidence=confidence,
            recommendation=recommendation,
            detected_at=detected_at,
        )
        alert_sent = email_result.sent
        alert_error = email_result.error

    review = Review(
        year=detected_at.year,
        quarter=f"Q{((detected_at.month - 1) // 3) + 1}",
        date=detected_at.date(),
        month=detected_at.strftime("%B"),
        source="Prediccion individual",
        external_id=f"manual-{employee.id}-{int(detected_at.timestamp() * 1000)}",
        comment=payload.comentario,
        sentiment=payload.sentimiento,
        category=payload.categoria,
        subcategory=payload.subcategoria,
        product=payload.producto,
        detail=payload.detalle,
        predicted_classification=predicted,
        prediction_confidence=confidence,
        employee_id=employee.id,
        alert_sent=alert_sent,
        alert_sent_at=detected_at if alert_sent else None,
    )
    db.add(review)
    db.commit()

    return PredictionResponse(
        predicted_classification=predicted,
        prediction_confidence=confidence,
        recommendation=recommendation,
        alert_sent=alert_sent,
        alert_error=alert_error,
    )


@app.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, int | list[str]]:
    content = await file.read()
    try:
        dataframe = pd.read_csv(BytesIO(content))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el CSV: {exc}") from exc

    missing = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        raise HTTPException(status_code=400, detail={"missing_columns": missing})

    inserted = 0
    skipped = 0
    errors = 0
    error_details: list[str] = []
    prediction_warnings: set[str] = set()

    for _, row in dataframe.iterrows():
        external_id = clean_value(row.get("ID"))
        if external_id:
            exists = db.scalar(select(Review.id).where(Review.external_id == external_id))
            if exists:
                skipped += 1
                continue
        try:
            review, prediction_warning = review_from_row(row, allow_prediction_fallback=True, employee=employee)
            if prediction_warning:
                prediction_warnings.add(prediction_warning)
            db.add(review)
            db.commit()
            inserted += 1
        except IntegrityError:
            db.rollback()
            skipped += 1
        except Exception as exc:
            db.rollback()
            errors += 1
            if len(error_details) < 5:
                error_details.append(f"ID {external_id or 'sin ID'}: {exc}")

    return {
        "inserted": inserted,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details,
        "prediction_warnings": sorted(prediction_warnings),
    }


@app.get("/reviews", response_model=list[ReviewOut])
def get_reviews(
    _: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
    category: str | None = None,
    subcategory: str | None = None,
    sentiment: str | None = None,
    product: str | None = None,
    classification: str | None = None,
    search: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[Review]:
    query = select(Review).options(selectinload(Review.employee)).order_by(Review.created_at.desc()).limit(limit).offset(offset)
    if category:
        query = query.where(Review.category == category)
    if subcategory:
        query = query.where(Review.subcategory == subcategory)
    if sentiment:
        query = query.where(Review.sentiment == sentiment)
    if product:
        query = query.where(Review.product == product)
    if classification:
        query = query.where(Review.predicted_classification == classification)
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Review.comment.ilike(pattern), Review.detail.ilike(pattern)))
    return list(db.scalars(query))


@app.get("/dashboard-summary")
def dashboard_summary(
    _: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    total = db.scalar(select(func.count(Review.id))) or 0
    churn_total = db.scalar(
        select(func.count(Review.id)).where(Review.predicted_classification.ilike("%abandono%"))
    ) or 0
    retention_total = db.scalar(
        select(func.count(Review.id)).where(Review.predicted_classification.ilike("%retenc%"))
    ) or 0
    if retention_total == 0 and total:
        retention_total = total - churn_total

    by_category = [
        {"name": name or "Sin categoria", "value": count}
        for name, count in db.execute(select(Review.category, func.count()).group_by(Review.category))
    ]
    by_subcategory = [
        {"name": name or "Sin subcategoria", "value": count}
        for name, count in db.execute(select(Review.subcategory, func.count()).group_by(Review.subcategory))
    ]
    trend = [
        {"name": name or "Sin mes", "value": count}
        for name, count in db.execute(select(Review.month, func.count()).group_by(Review.month).order_by(Review.month))
    ]

    return {
        "total_reviews": total,
        "high_churn_intent": churn_total,
        "likely_retention": retention_total,
        "by_category": by_category,
        "by_subcategory": by_subcategory,
        "trend": trend,
    }


@app.get("/categories")
def categories(
    _: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
) -> dict[str, list[str]]:
    def distinct(column):
        rows = db.execute(select(column).where(column.is_not(None)).distinct().order_by(column)).scalars()
        return [value for value in rows if value]

    return {
        "categories": distinct(Review.category),
        "subcategories": distinct(Review.subcategory),
        "sentiments": distinct(Review.sentiment),
        "products": distinct(Review.product),
        "classifications": distinct(Review.predicted_classification),
    }


@app.get("/model-status")
def model_status() -> dict[str, str | bool | None]:
    warning = get_model_warning()
    return {"ready": warning is None, "warning": warning}
