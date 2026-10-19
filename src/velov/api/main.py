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
import pandas as pd
from datetime import timedelta
import httpx
import joblib
from fastapi import FastAPI, HTTPException, Query

from velov.api.schemas import PredictionRequest, PredictionResponse  # noqa: F401
from velov.db import log_prediction, make_engine
from velov.features import FEATURES, add_features  # noqa: F401
from velov.gbfs import fetch_station_snapshot
from velov.train import METADATA_FILENAME, sha256_of

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("velov.api")

STATE: dict = {"model": None, "metadata": None, "db_engine": None}


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
    try:
        STATE["db_engine"] = make_engine()
    except Exception:
        logger.exception("Échec de la connexion à la base (journalisation désactivée)")
    yield
    STATE.update(model=None, metadata=None, db_engine=None)


app = FastAPI(title="Vélo'v availability API", version="1.0.0", lifespan=lifespan)


# TODO 5 [Should] : GET /health -> {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# TODO 6 [Should] : GET /ready -> 200 + version du modèle si chargé, sinon HTTPException 503

@app.get("/ready")
async def ready():
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return {"status": "ok", "model_version": STATE["metadata"]["model_version"]}


# TODO 7 [Must] : POST /v1/predict
#   - entrée : PredictionRequest ; sortie : PredictionResponse
#   - construire un DataFrame d'une ligne, appliquer add_features, sélectionner FEATURES
#   - prédire, borner entre 0 et capacity, target_timestamp = timestamp + 1 h
#     (l'instant porte son fuseau : le contrat l'a validé)
#   - 503 si le modèle n'est pas chargé
#   Question : pourquoi importer add_features plutôt que recalculer les features ici ?

@app.post("/v1/predict")
async def predict(request: PredictionRequest) -> PredictionResponse:
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")

    df = pd.DataFrame([request.dict()])
    df = add_features(df)
    X = df[FEATURES]
    y_pred = STATE["model"].predict(X)
    predicted_bikes = max(0, min(request.capacity, y_pred[0]))
    target_timestamp = request.timestamp + timedelta(hours=1)
    response = PredictionResponse(
        station_id=request.station_id,
        target_timestamp=target_timestamp,
        predicted_bikes=predicted_bikes,
        model_version=STATE["metadata"]["model_version"],
    )
    log_prediction(
        STATE["db_engine"],
        {
            "station_id": request.station_id,
            "timestamp": request.timestamp,
            "capacity": request.capacity,
            "bikes_available": request.bikes_available,
            "temperature": request.temperature,
            "is_raining": request.is_raining,
            "target_timestamp": response.target_timestamp,
            "predicted_bikes": response.predicted_bikes,
            "model_version": response.model_version,
        },
    )
    return response


# S3 : prédiction à partir des vrais flux GBFS Vélo'v de la Métropole de Lyon.
# temperature et is_raining ne sont pas dans GBFS : on les passe en query, défauts raisonnables.
@app.get("/v1/predict/live/{station_id}")
async def predict_live(
    station_id: int,
    temperature: float = Query(15.0, ge=-30, le=50),
    is_raining: bool = Query(False),
) -> PredictionResponse:
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    try:
        snapshot = fetch_station_snapshot(station_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Flux GBFS indisponible : {exc}") from exc
    request = PredictionRequest(
        **snapshot,
        temperature=temperature,
        is_raining=is_raining,
    )
    return await predict(request)