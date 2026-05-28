from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class PredictRequest(BaseModel):
    comentario: str
    categoria: str | None = None
    subcategoria: str | None = None
    sentimiento: str | None = None
    producto: str | None = None
    detalle: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None


class PredictionResponse(BaseModel):
    predicted_classification: str
    prediction_confidence: float | None
    recommendation: str
    alert_sent: bool = False
    alert_error: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EmployeeCreate(BaseModel):
    name: str
    email: str
    password: str
    role: str = "analyst"


class EmployeeUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class MessageResponse(BaseModel):
    message: str


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    created_at: datetime


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    year: int | None
    quarter: str | None
    date: date | None
    month: str | None
    source: str | None
    external_id: str | None
    comment: str | None
    sentiment: str | None
    category: str | None
    subcategory: str | None
    product: str | None
    detail: str | None
    original_classification: str | None
    predicted_classification: str | None
    prediction_confidence: float | None
    employee_id: int | None
    employee_name: str | None = None
    alert_sent: bool
    alert_sent_at: datetime | None
    created_at: datetime
