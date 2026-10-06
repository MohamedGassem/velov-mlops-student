from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException

from velov.api.schemas import PredictionRequest, PredictionResponse
from velov.features import FEATURES, add_features
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
    """Fourni : exécuté une fois au démarrage et à l'arrêt."""
    model_dir = Path(os.getenv("MODEL_DIR", "models"))

    try:
        STATE["model"], STATE["metadata"] = load_model(model_dir)
        logger.info(
            "Modèle %s chargé",
            STATE["metadata"]["model_version"],
        )
    except Exception:
        logger.exception(
            "Échec du chargement du modèle depuis %s",
            model_dir,
        )

    yield

    STATE.update(model=None, metadata=None)


app = FastAPI(
    title="Vélo'v availability API",
    version="1.0.0",
    lifespan=lifespan,
)


# TODO 5 [Should] : liveness
@app.get("/health")
def health():
    return {"status": "ok"}


# TODO 6 [Should] : readiness
@app.get("/ready")
def ready():
    if STATE["model"] is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded",
        )

    return {
        "status": "ready",
        "model_version": STATE["metadata"]["model_version"],
    }


# TODO 7 [Must] : prédiction
@app.post("/v1/predict", response_model=PredictionResponse)
def predict(request: PredictionRequest):

    if STATE["model"] is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded",
        )

    # 1. Construire un DataFrame d'une ligne
    df = pd.DataFrame(
        [
            {
                "station_id": request.station_id,
                "timestamp": request.timestamp,
                "capacity": request.capacity,
                "bikes_available": request.bikes_available,
                "temperature": request.temperature,
                "is_raining": request.is_raining,
            }
        ]
    )

    # 2. Créer exactement les mêmes features qu'à l'entraînement
    df = add_features(df)

    # 3. Garder seulement les variables attendues par le modèle
    X = df[FEATURES]

    # 4. Prédire
    prediction = float(STATE["model"].predict(X)[0])

    # 5. Borner entre 0 et capacity
    prediction = max(
        0.0,
        min(prediction, float(request.capacity)),
    )

    # 6. Construire la réponse
    return PredictionResponse(
        station_id=request.station_id,
        target_timestamp=request.timestamp + timedelta(hours=1),
        predicted_bikes=prediction,
        model_version=STATE["metadata"]["model_version"],
    )