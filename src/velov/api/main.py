"""API de serving du modèle Vélo'v.

TP1, partie 3 : exposez le modèle. Mode : IA déclarée autorisée pour cette partie.

Endpoints attendus (niveaux du TP1 : Must, Should, Stretch) :
    POST /v1/predict        [Must]    une prédiction
    GET  /health            [Should]  liveness : le process répond (ne dépend pas du modèle)
    GET  /ready             [Should]  readiness : 200 si le modèle est chargé, 503 sinon
    GET  /v1/model, POST /v1/predict/batch   [Stretch]

Lancement :
    uvicorn velov.api.main:app --reload
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pandas as pd

import joblib
from fastapi import FastAPI, HTTPException

from velov.api.schemas import PredictionRequest, PredictionResponse  # noqa: F401
from velov.features import FEATURES, add_features  # noqa: F401
from velov.train import METADATA_FILENAME, sha256_of

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("velov.api")

STATE: dict = {"model": None, "metadata": None}


def load_model(model_dir: Path) -> tuple[object, dict]:
    """Fourni : charge le modèle APRÈS avoir vérifié son empreinte SHA-256."""
    metadata_path = model_dir / METADATA_FILENAME
    if not metadata_path.exists():
        raise FileNotFoundError(f"{metadata_path} introuvable")
    metadata = json.loads(metadata_path.read_text())
    model_path = model_dir / metadata["artifact"]["file"]
    if sha256_of(model_path) != metadata["artifact"]["sha256"]:
        raise RuntimeError(f"Empreinte invalide pour {model_path}")
    return joblib.load(model_path), metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Fourni : exécuté une fois au démarrage (avant yield) et à l'arrêt (après yield)."""
    model_dir = Path(os.getenv("MODEL_DIR", "models"))
    try:
        STATE["model"], STATE["metadata"] = load_model(model_dir)
        logger.info("Modèle %s chargé", STATE["metadata"]["model_version"])
    except Exception:
        logger.exception("Échec du chargement du modèle depuis %s", model_dir)
    yield
    STATE.update(model=None, metadata=None)


app = FastAPI(title="Vélo'v availability API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready", "model_version": STATE["metadata"]["model_version"]}


@app.post("/v1/predict")
def predict(req: PredictionRequest) -> PredictionResponse:
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    df = pd.DataFrame([{
        "station_id": req.station_id,
        "timestamp": pd.Timestamp(req.timestamp),
        "capacity": req.capacity,
        "bikes_available": req.bikes_available,
        "temperature": req.temperature,
        "is_raining": req.is_raining,
    }])

    df = add_features(df)
    prediction = STATE["model"].predict(df[FEATURES])[0]
    predicted_bikes = float(max(0, min(prediction, req.capacity)))
    target_timestamp = req.timestamp + timedelta(hours=1)

    return PredictionResponse(
        station_id=req.station_id,
        target_timestamp=target_timestamp,
        predicted_bikes=predicted_bikes,
        model_version=STATE["metadata"]["model_version"],
    )
