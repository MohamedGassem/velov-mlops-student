"""Suivi des entraînements et registre de modèles avec MLflow (S4).

Un run MLflow répond à quatre questions sur un modèle, des mois plus tard :
quel code (commit git), quelles données (empreinte), quels paramètres, quels résultats.

Le serveur se désigne par la variable MLFLOW_TRACKING_URI :
    export MLFLOW_TRACKING_URI=http://127.0.0.1:5000      # serveur du compose S4
    export MLFLOW_TRACKING_URI=sqlite:///mlflow.db         # sans serveur, en local

Registre : chaque nouvelle version reçoit l'alias "challenger". Seul promote.py
déplace l'alias "champion", après comparaison sur les mêmes données.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import joblib
import mlflow
from mlflow import MlflowClient
from mlflow.models import infer_signature

from velov.features import FEATURES, RAW_COLUMNS, make_training_frame
from velov.train import MODEL_FILENAME, load_table

MODEL_NAME = "velov-availability"
EXPERIMENT = "velov-availability"
CHALLENGER, CHAMPION, PREVIOUS = "challenger", "champion", "previous-champion"

# skops refuse de charger un type qu'on ne lui a pas déclaré : la liste est courte et relue.
SKOPS_TRUSTED_TYPES = ["sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor"]


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], capture_output=True, text=True, check=True)  # noqa: S603, S607
    return out.stdout.strip()


def git_state() -> dict:
    """Commit courant et présence de modifications non commitées (un run « dirty » n'est pas rejouable)."""
    try:
        return {
            "git_commit": _git("rev-parse", "HEAD"),
            "git_dirty": str(bool(_git("status", "--porcelain", "--untracked-files=no"))).lower(),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": "unknown", "git_dirty": "unknown"}


def log_training(metadata: dict, out_dir: Path, register: bool = False) -> dict:
    """Trace un entraînement déjà réalisé par velov.train.train().

    Le run contient : paramètres, métriques, tags (commit, données), le jeu de données,
    le modèle au format MLflow (skops) et le paquet de déploiement (joblib + metadata.json).
    """
    pipeline = joblib.load(out_dir / MODEL_FILENAME)
    raw = load_table(Path(metadata["data"]["path"]))
    sample = make_training_frame(raw.head(48))[FEATURES].head(5)

    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run(run_name=f"v{metadata['model_version']}") as run:
        mlflow.log_params(metadata["params"])
        mlflow.log_metrics({k: v for k, v in metadata["metrics"].items() if k.startswith("mae")})
        mlflow.set_tags(
            {
                **git_state(),
                "data_sha256": metadata["data"]["sha256"],
                "data_from": metadata["data"]["from"],
                "data_to": metadata["data"]["to"],
                "model_version": metadata["model_version"],
            }
        )
        dataset = mlflow.data.from_pandas(
            raw[RAW_COLUMNS],
            source=Path(metadata["data"]["path"]).resolve().as_uri(),
            name="station_hourly",
            digest=metadata["data"]["sha256"][:8],
        )
        mlflow.log_input(dataset, context="training")

        info = mlflow.sklearn.log_model(
            pipeline,
            name="model",
            signature=infer_signature(sample, pipeline.predict(sample)),
            input_example=sample,
            serialization_format="skops",  # défaut de MLflow 3 : pas d'exécution de code au chargement
            skops_trusted_types=SKOPS_TRUSTED_TYPES,
            registered_model_name=MODEL_NAME if register else None,
        )
        # Le paquet que l'API sait charger (S1), rangé avec le run qui l'a produit.
        mlflow.log_artifacts(str(out_dir), artifact_path="package")

    result = {"run_id": run.info.run_id, "name": MODEL_NAME, "version": None}
    if register:
        version = str(info.registered_model_version)
        client = MlflowClient()
        client.set_registered_model_alias(MODEL_NAME, CHALLENGER, version)
        for key in ("mae_model", "mae_baseline_persistence"):
            client.set_model_version_tag(MODEL_NAME, version, key, str(metadata["metrics"][key]))
        result["version"] = version
    return result


def load_registered(version: str):
    """Charge une version du registre (format skops, types déclarés)."""
    return mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{version}")


def version_by_alias(alias: str):
    """Version portant cet alias, ou None si l'alias n'existe pas encore."""
    try:
        return MlflowClient().get_model_version_by_alias(MODEL_NAME, alias)
    except mlflow.exceptions.MlflowException:
        return None
