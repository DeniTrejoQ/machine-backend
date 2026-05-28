from pathlib import Path
from typing import Any
import re

import numpy as np
import tensorflow as tf
from tensorflow import keras


MODEL_PATHS = [Path("bilstm.keras"), Path(__file__).with_name("bilstm.keras")]

URL_RE = re.compile(r"http\S+|www\.\S+")
NUM_RE = re.compile(r"\b\d+\b")
SPACE_RE = re.compile(r"\s+")

lstm: keras.Model | None = None
model_warning: str | None = None


class ModelCompatibilityError(RuntimeError):
    pass


def load_artifacts() -> None:
    global lstm, model_warning

    model_path = next((path for path in MODEL_PATHS if path.exists()), None)
    if model_path is None:
        expected = ", ".join(str(path) for path in MODEL_PATHS)
        lstm = None
        model_warning = f"No se encontro el modelo Keras bilstm.keras. Rutas revisadas: {expected}"
        return

    try:
        lstm = keras.models.load_model(model_path)
        model_warning = None
    except Exception as exc:
        lstm = None
        model_warning = f"No se pudo cargar bilstm.keras: {exc}"


def get_model_warning() -> str | None:
    return model_warning


def assert_model_ready() -> None:
    if lstm is None:
        raise ModelCompatibilityError(model_warning or "El modelo bilstm.keras no ha sido cargado.")


def normaliza(txt: str) -> str:
    txt = str(txt).lower().strip()
    txt = URL_RE.sub(" URL ", txt)
    txt = NUM_RE.sub(" NUM ", txt)
    txt = re.sub(r"([!?¡¿])\1+", r" \1 ", txt)
    txt = re.sub(r"[^\wáéíóúüñ¡!¿?., ]+", " ", txt, flags=re.UNICODE)
    return SPACE_RE.sub(" ", txt).strip()


def predecir(comentarios: list[str]) -> list[tuple[str, float]]:
    assert_model_ready()
    textos = [normaliza(c) for c in comentarios]
    t = tf.constant(np.array(textos).reshape(-1, 1), dtype=tf.string)
    p = lstm.predict(t, verbose=0).ravel()
    return [("Abandono" if pi >= 0.5 else "Retención", float(pi)) for pi in p]


def predict(payload: dict[str, Any]) -> tuple[str, float | None]:
    comment = payload.get("comentario") or payload.get("comment") or ""
    if not str(comment).strip():
        raise ModelCompatibilityError("El campo Comentario es obligatorio para generar la prediccion.")
    return predecir([str(comment)])[0]


def recommendation_for(classification: str, confidence: float | None) -> str:
    normalized = classification.lower()
    if "abandono" in normalized or (confidence is not None and confidence >= 0.5):
        return (
            "Contactar al cliente de forma prioritaria, identificar la causa del riesgo "
            "y activar un plan de retencion con seguimiento comercial."
        )
    return (
        "Mantener seguimiento preventivo, reforzar los puntos positivos detectados "
        "y programar comunicacion de continuidad con el cliente."
    )
