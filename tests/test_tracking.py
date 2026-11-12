"""Bout en bout sans serveur : run tracé, version enregistrée, promue, exportée, servie (S4)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mlflow")  # MLflow est une dépendance de dev, absente de l'image de serving

from velov.data import simulate  # noqa: E402
from velov.export import export  # noqa: E402
from velov.tracking import CHALLENGER, CHAMPION, MODEL_NAME, log_training, version_by_alias  # noqa: E402
from velov.train import train  # noqa: E402


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", f"sqlite:///{tmp_path / 'mlflow.db'}")
    monkeypatch.chdir(tmp_path)  # les artefacts locaux atterrissent dans le dossier temporaire
    data_path = tmp_path / "history.csv"
    simulate(days=20, n_stations=3, seed=0).to_csv(data_path, index=False)
    return tmp_path, data_path


def test_register_promote_export_serve(registry, monkeypatch):
    from mlflow import MlflowClient

    workdir, data_path = registry
    metadata = train(data_path, workdir / "models", version="0.0.0-test", test_days=3)
    info = log_training(metadata, workdir / "models", register=True)

    assert str(version_by_alias(CHALLENGER).version) == info["version"] == "1"
    run = MlflowClient().get_run(info["run_id"])
    assert run.data.params["seed"] == "42"
    assert run.data.tags["data_sha256"] == metadata["data"]["sha256"]

    MlflowClient().set_registered_model_alias(MODEL_NAME, CHAMPION, info["version"])
    exported = export(CHAMPION, workdir / "release")
    assert exported["registry"]["version"] == "1"
    assert json.loads((workdir / "release" / "metadata.json").read_text())["registry"]["alias"] == CHAMPION

    monkeypatch.setenv("MODEL_DIR", str(workdir / "release"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from velov.api.main import app

    with TestClient(app) as client:
        assert client.get("/ready").status_code == 200
        assert client.get("/v1/model").json()["registry"]["run_id"] == info["run_id"]


def test_export_without_champion_fails(registry):
    with pytest.raises(LookupError):
        export(CHAMPION, registry[0] / "release")
