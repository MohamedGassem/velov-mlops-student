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
import math
import os
from contextlib import asynccontextmanager
from datetime import UTC, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from velov.api.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    PredictionRequest,
    PredictionResponse,
)
from velov.features import FEATURES, RAW_COLUMNS, add_features
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


def json_safe(value):
    """Remplace NaN / Infinity (non représentables en JSON) par leur texte, récursivement."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 identique à celui de FastAPI, mais qui ne plante pas sur NaN / Infinity (EX-01).

    Le parseur JSON de Python accepte NaN et Infinity. Pydantic les refuse bien, mais le
    handler par défaut renvoie la valeur fautive dans la réponse, que json.dumps ne sait
    pas sérialiser : la réponse 422 elle-même partait alors en 500.
    """
    return JSONResponse(status_code=422, content={"detail": json_safe(jsonable_encoder(exc.errors()))})


def require_model() -> tuple[object, dict]:
    """Le modèle et ses métadonnées, ou 503 s'il n'a pas pu être chargé au démarrage."""
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé (voir les logs de démarrage)")
    return STATE["model"], STATE["metadata"]


def predict_many(requests: list[PredictionRequest]) -> list[PredictionResponse]:
    """Prédiction vectorisée, partagée par /v1/predict et /v1/predict/batch."""
    model, metadata = require_model()
    raw = pd.DataFrame([{col: getattr(r, col) for col in RAW_COLUMNS} for r in requests])
    # utc=True : un lot peut mélanger les fuseaux (+02:00, Z...), pandas exige un fuseau unique.
    # Le contrat garantit que chaque instant porte un fuseau, rien n'est donc deviné ici.
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
    # add_features est importé, jamais réécrit ici : le modèle reçoit exactement les features
    # calculées comme à l'entraînement (sinon training-serving skew, silencieux).
    X = add_features(raw)[FEATURES]
    predictions = np.clip(model.predict(X), 0, raw["capacity"].to_numpy())
    return [
        PredictionResponse(
            station_id=r.station_id,
            # Passage en UTC AVANT d'ajouter 1 h : l'arithmétique est alors exacte, même
            # lors d'un changement d'heure.
            target_timestamp=r.timestamp.astimezone(UTC) + timedelta(hours=1),
            predicted_bikes=float(p),
            model_version=metadata["model_version"],
        )
        for r, p in zip(requests, predictions, strict=True)
    ]


# TODO 5 [Should] : GET /health -> {"status": "ok"}
@app.get("/health")
def health() -> dict:
    """Liveness : le process répond, indépendamment du modèle."""
    return {"status": "ok"}


# TODO 6 [Should] : GET /ready -> 200 + version du modèle si chargé, sinon HTTPException 503
@app.get("/ready")
def ready() -> dict:
    """Readiness : 200 seulement si le modèle est chargé (empreinte vérifiée), sinon 503."""
    _, metadata = require_model()
    return {"status": "ready", "model_version": metadata["model_version"]}


# TODO 7 [Must] : POST /v1/predict
#   - entrée : PredictionRequest ; sortie : PredictionResponse
#   - construire un DataFrame d'une ligne, appliquer add_features, sélectionner FEATURES
#   - prédire, borner entre 0 et capacity, target_timestamp = timestamp + 1 h
#     (l'instant porte son fuseau : le contrat l'a validé)
#   - 503 si le modèle n'est pas chargé
#   Question : pourquoi importer add_features plutôt que recalculer les features ici ?
@app.post("/v1/predict")
def predict(request: PredictionRequest) -> PredictionResponse:
    return predict_many([request])[0]


@app.get("/v1/model")
def model_info() -> dict:
    """Métadonnées du modèle servi : version, métriques, features, versions des librairies."""
    _, metadata = require_model()
    return metadata


@app.post("/v1/predict/batch")
def predict_batch(batch: BatchPredictionRequest) -> BatchPredictionResponse:
    return BatchPredictionResponse(predictions=predict_many(batch.instances))
