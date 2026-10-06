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
from pathlib import Path

import joblib
from datetime import timedelta

import pandas as pd
from fastapi import FastAPI, HTTPException, status

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


# TODO 5 [Should] : GET /health -> {"status": "ok"}



# TODO 6 [Should] : GET /ready -> 200 + version du modèle si chargé, sinon HTTPException 503


# TODO 7 [Must] : POST /v1/predict
#   - entrée : PredictionRequest ; sortie : PredictionResponse
#   - construire un DataFrame d'une ligne, appliquer add_features, sélectionner FEATURES
#   - prédire, borner entre 0 et capacity, target_timestamp = timestamp + 1 h
#     (l'instant porte son fuseau : le contrat l'a validé)
#   - 503 si le modèle n'est pas chargé
#   Question : pourquoi importer add_features plutôt que recalculer les features ici ?

# Partie réalisée avec de l'IA (copilot) pour gagner du temps

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if STATE["model"] is None or STATE["metadata"] is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="model not loaded")
    return {"model_version": STATE["metadata"]["model_version"]}


@app.post("/v1/predict", response_model=PredictionResponse)
def predict(req: PredictionRequest):
    if STATE["model"] is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="model not loaded")

    row = {
        "station_id": req.station_id,
        "timestamp": req.timestamp,
        "capacity": req.capacity,
        "bikes_available": req.bikes_available,
        "temperature": req.temperature,
        "is_raining": req.is_raining,
    }
    df = pd.DataFrame([row])

    feats = add_features(df)[FEATURES]

    pred = STATE["model"].predict(feats)
    predicted = float(pred[0])

    predicted = max(0.0, min(predicted, float(req.capacity)))

    target_ts = req.timestamp + timedelta(hours=1)

    return PredictionResponse(
        station_id=req.station_id,
        target_timestamp=target_ts,
        predicted_bikes=predicted,
        model_version=STATE["metadata"]["model_version"],
    )