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
@app.get("/health")
def health() -> dict:
    """Liveness : le process répond. Ne dépend volontairement pas du modèle."""
    return {"status": "ok"}


# TODO 6 [Should] : GET /ready -> 200 + version du modèle si chargé, sinon HTTPException 503
@app.get("/ready")
def ready() -> dict:
    """Readiness : prêt à servir des prédictions uniquement si le modèle est chargé."""
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")
    return {"status": "ready", "model_version": STATE["metadata"]["model_version"]}


# TODO 7 [Must] : POST /v1/predict
#   Question : pourquoi importer add_features plutôt que recalculer les features ici ?
#   Réponse : pour éviter le training/serving skew. Une seule fonction partagée garantit
#   que l'entraînement et l'API calculent exactement les mêmes features.
@app.post("/v1/predict", response_model=PredictionResponse)
def predict(req: PredictionRequest) -> PredictionResponse:
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="Modèle non chargé")

    # 1. Une ligne de DataFrame à partir de la requête validée
    df = pd.DataFrame([req.model_dump()])

    # 2. Mêmes features qu'à l'entraînement, puis sélection des colonnes du modèle
    X = add_features(df)[FEATURES]

    # 3. Prédiction, bornée entre 0 et la capacité de la station
    raw = float(STATE["model"].predict(X)[0])
    predicted = max(0.0, min(raw, float(req.capacity)))

    # 4. Horizon : t + 1 h (le timestamp porte son fuseau, déjà normalisé en UTC)
    return PredictionResponse(
        station_id=req.station_id,
        target_timestamp=req.timestamp + timedelta(hours=1),
        predicted_bikes=predicted,
        model_version=STATE["metadata"]["model_version"],
    )