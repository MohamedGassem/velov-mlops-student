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

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from velov.api.schemas import (  # noqa: F401
    BatchPredictionRequest,
    BatchPredictionResponse,
    PredictionRequest,
    PredictionResponse,
)
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


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
    """Return a JSON-safe 422 response even when the rejected input contains NaN."""
    errors = [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})


# TODO 5 [Should] : GET /health -> {"status": "ok"}
@app.get("/health")
def health():
    return {"status": "ok"}


# TODO 6 [Should] : GET /ready -> 200 + version du modèle si chargé, sinon HTTPException 503
@app.get("/ready")
def ready():
    if STATE["model"] is not None:
        return {"model_version": STATE["metadata"]["model_version"]}
    else:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
        

# TODO 7 [Must] : POST /v1/predict
#   - entrée : PredictionRequest ; sortie : PredictionResponse
#   - construire un DataFrame d'une ligne, appliquer add_features, sélectionner FEATURES
#   - prédire, borner entre 0 et capacity, target_timestamp = timestamp + 1 h
#     (l'instant porte son fuseau : le contrat l'a validé)
#   - 503 si le modèle n'est pas chargé
#   Question : pourquoi importer add_features plutôt que recalculer les features ici ?

@app.post("/v1/predict", response_model=PredictionResponse)
def predict(payload: PredictionRequest):
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")

    raw = pd.DataFrame([payload.model_dump()])
    X = add_features(raw)[FEATURES]
    y = min(max(STATE["model"].predict(X)[0], 0), payload.capacity)
    return PredictionResponse(
        station_id=payload.station_id,
        target_timestamp=payload.timestamp + timedelta(hours=1),
        predicted_bikes=float(round(y,2)),
        model_version=STATE["metadata"]["model_version"],
    )
# tp1 p5 STRETCH
@app.post("/v1/predict/batch", response_model=BatchPredictionResponse)
def predict_batch(payload: BatchPredictionRequest):
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    
    raw = pd.DataFrame([item.model_dump() for item in payload.items])
    X = add_features(raw)[FEATURES]
    ys = STATE["model"].predict(X)

    predictions = []

    for item, y in zip(payload.items, ys, strict=True):
        y = min(max(y, 0), item.capacity)

        predictions.append(
            PredictionResponse(
                station_id=item.station_id,
                target_timestamp=item.timestamp + timedelta(hours=1),
                predicted_bikes=float(round(y, 2)),
                model_version=STATE["metadata"]["model_version"],
            )
        )

    return BatchPredictionResponse(predictions=predictions)

# tp1 p5 STRETCH
@app.get("/v1/model")
def model():
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return {"model_version": STATE["metadata"]["model_version"]}
