import logging
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage


logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    sent: bool
    error: str | None = None


def _smtp_config() -> dict[str, str | int | None]:
    return {
        "host": os.getenv("SMTP_HOST"),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER"),
        "password": os.getenv("SMTP_PASSWORD"),
        "from_email": os.getenv("SMTP_FROM_EMAIL"),
    }


def send_churn_alert_email(
    *,
    to_email: str,
    employee_name: str,
    customer_reference: str | None,
    comment: str | None,
    category: str | None,
    subcategory: str | None,
    classification: str,
    confidence: float | None,
    recommendation: str,
    detected_at: datetime,
) -> EmailResult:
    config = _smtp_config()
    if not config["host"] or not config["from_email"]:
        return EmailResult(sent=False, error="SMTP no configurado")

    confidence_text = "N/D" if confidence is None else f"{confidence:.0%}"
    customer_text = customer_reference or "No especificado"
    body = f"""Hola {employee_name},

ELEMENT ELITE FLEET detecto que un cliente podria estar por irse.

Cliente o ID: {customer_text}
Comentario analizado: {comment or "N/D"}
Categoria: {category or "N/D"}
Subcategoria: {subcategory or "N/D"}
Clasificacion predicha: {classification}
Probabilidad/confianza: {confidence_text}
Recomendacion de accion: {recommendation}
Fecha de deteccion: {detected_at.isoformat(sep=" ", timespec="seconds")}

Este caso requiere seguimiento comercial prioritario.
"""

    message = EmailMessage()
    message["Subject"] = "Alerta de abandono de cliente - ELEMENT ELITE FLEET"
    message["From"] = str(config["from_email"])
    message["To"] = to_email
    message.set_content(body)

    try:
        with smtplib.SMTP(str(config["host"]), int(config["port"]), timeout=20) as smtp:
            smtp.starttls()
            if config["user"] and config["password"]:
                smtp.login(str(config["user"]), str(config["password"]))
            smtp.send_message(message)
        return EmailResult(sent=True)
    except Exception as exc:
        logger.warning("No se pudo enviar alerta SMTP: %s", exc)
        return EmailResult(sent=False, error="No se pudo enviar el email de alerta")
