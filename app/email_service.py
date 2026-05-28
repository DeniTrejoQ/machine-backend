import html
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime

import resend

from . import config  # noqa: F401


logger = logging.getLogger(__name__)
SECRET_RE = re.compile(r"re_[A-Za-z0-9_\-]+")


@dataclass
class EmailResult:
    sent: bool
    error: str | None = None


def _resend_config() -> tuple[str | None, str | None]:
    return os.getenv("RESEND_API_KEY"), os.getenv("RESEND_FROM_EMAIL")


def _safe_error_message(exc: Exception) -> str:
    raw_message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
    message = SECRET_RE.sub("re_***", raw_message)
    lower = message.lower()

    if "domain is not verified" in lower or "verify your domain" in lower:
        return (
            "Resend rechazo el remitente: el dominio de RESEND_FROM_EMAIL no esta verificado "
            "en Resend."
        )
    if "invalid `from`" in lower or "invalid from" in lower:
        return "Resend rechazo RESEND_FROM_EMAIL: usa un remitente valido de un dominio verificado."
    if "invalid `to`" in lower or "invalid to" in lower:
        return "Resend rechazo el correo del empleado: revisa que el email del usuario sea valido."
    if "api key" in lower or "unauthorized" in lower or "authentication" in lower:
        return "Resend rechazo la solicitud: revisa que RESEND_API_KEY sea valida."
    return f"Resend no pudo enviar el correo: {message}"


def _value(value: str | None) -> str:
    return html.escape(value or "N/D")


def send_alert_email(to_email: str, subject: str, html_content: str) -> object:
    api_key, from_email = _resend_config()
    missing = []
    if not api_key:
        missing.append("RESEND_API_KEY")
    if not from_email:
        missing.append("RESEND_FROM_EMAIL")
    if missing:
        raise RuntimeError(f"Resend no configurado: falta {', '.join(missing)}")

    resend.api_key = api_key
    return resend.Emails.send(
        {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
        }
    )


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
    confidence_text = "N/D" if confidence is None else f"{confidence:.0%}"
    detected_text = detected_at.isoformat(sep=" ", timespec="seconds")
    subject = "Alerta de abandono de cliente - ELEMENT ELITE FLEET"
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #172033; line-height: 1.55;">
        <h2 style="color: #0f4c81; margin-bottom: 8px;">ELEMENT ELITE FLEET</h2>
        <p>Hola {_value(employee_name)},</p>
        <p><strong>El sistema detecto que este cliente podria estar por irse.</strong></p>
        <table cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; max-width: 720px;">
          <tr><td><strong>Cliente o ID</strong></td><td>{_value(customer_reference or "No especificado")}</td></tr>
          <tr><td><strong>Comentario analizado</strong></td><td>{_value(comment)}</td></tr>
          <tr><td><strong>Categoria</strong></td><td>{_value(category)}</td></tr>
          <tr><td><strong>Subcategoria</strong></td><td>{_value(subcategory)}</td></tr>
          <tr><td><strong>Clasificacion predicha</strong></td><td>{_value(classification)}</td></tr>
          <tr><td><strong>Probabilidad/confianza</strong></td><td>{html.escape(confidence_text)}</td></tr>
          <tr><td><strong>Recomendacion de accion</strong></td><td>{_value(recommendation)}</td></tr>
          <tr><td><strong>Fecha de deteccion</strong></td><td>{html.escape(detected_text)}</td></tr>
          <tr><td><strong>Empleado que genero la prediccion</strong></td><td>{_value(employee_name)}</td></tr>
        </table>
        <p style="margin-top: 18px;">Este caso requiere seguimiento comercial prioritario.</p>
      </body>
    </html>
    """

    try:
        send_alert_email(to_email=to_email, subject=subject, html_content=html_content)
        return EmailResult(sent=True)
    except Exception as exc:
        error = _safe_error_message(exc)
        logger.warning("No se pudo enviar alerta con Resend: %s", error)
        return EmailResult(sent=False, error=error)
