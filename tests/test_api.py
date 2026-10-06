"""Tests de l'API. Les fixtures (client, valid_payload, model_dir) sont dans conftest.py.

TODO 8 [Must] : faire passer les deux tests ci-dessous (une prédiction valide, une entrée invalide).
TODO 9 [Should] : en ajouter d'autres, par exemple :
  - /health renvoie 200 et /ready 503 quand MODEL_DIR pointe vers un dossier vide
  - un champ inconnu renvoie 422
  - un timestamp sans fuseau ("2026-10-06T08:00:00") renvoie 422
  - la prédiction est comprise entre 0 et capacity
  - (Stretch) une station jamais vue à l'entraînement ne fait pas planter l'API
"""

import json
import shutil
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_without_model(tmp_path, monkeypatch):
    """API démarrée avec un MODEL_DIR vide : le modèle ne peut pas être chargé."""
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    from velov.api.main import app

    with TestClient(app) as c:
        yield c


def test_predict_valid(client, valid_payload):
    r = client.post("/v1/predict", json=valid_payload)
    assert r.status_code == 200
    # 8 h à Lyon (+02:00) + 1 h = 7 h UTC, quel que soit le fuseau dans lequel l'API répond
    target = datetime.fromisoformat(r.json()["target_timestamp"])
    assert target == datetime(2026, 10, 6, 7, tzinfo=UTC)


def test_predict_rejects_bikes_above_capacity(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "bikes_available": 25})
    assert r.status_code == 422


# --- Santé et disponibilité (EX-02, EX-07) ---


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_when_model_loaded(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["model_version"] == "0.0.0-test"


def test_health_ok_but_not_ready_without_model(client_without_model):
    assert client_without_model.get("/health").status_code == 200
    assert client_without_model.get("/ready").status_code == 503


def test_predict_503_without_model(client_without_model, valid_payload):
    r = client_without_model.post("/v1/predict", json=valid_payload)
    assert r.status_code == 503


def test_ready_503_when_checksum_invalid(model_dir, tmp_path, monkeypatch, caplog):
    tampered = tmp_path / "models"
    shutil.copytree(model_dir, tampered)
    with (tampered / "model.joblib").open("ab") as f:
        f.write(b"\x00")  # un octet de plus : l'empreinte SHA-256 ne correspond plus
    monkeypatch.setenv("MODEL_DIR", str(tampered))
    from velov.api.main import app

    with TestClient(app) as c:
        assert c.get("/ready").status_code == 503
    assert "Empreinte invalide" in caplog.text  # la cause est lisible dans les logs


# --- Contrat d'entrée : toute entrée invalide donne 422, jamais 500 (EX-01) ---


def test_predict_rejects_unknown_field(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "foo": 1})
    assert r.status_code == 422


def test_predict_rejects_timestamp_without_timezone(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "timestamp": "2026-10-06T08:00:00"})
    assert r.status_code == 422


@pytest.mark.parametrize(
    "field", ["station_id", "timestamp", "capacity", "bikes_available", "temperature", "is_raining"]
)
def test_predict_rejects_missing_field(client, valid_payload, field):
    payload = {k: v for k, v in valid_payload.items() if k != field}
    assert client.post("/v1/predict", json=payload).status_code == 422


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("station_id", 0),
        ("capacity", 0),
        ("capacity", 101),
        ("bikes_available", -1),
        ("temperature", -31),
        ("temperature", 51),
    ],
)
def test_predict_rejects_out_of_bounds(client, valid_payload, field, value):
    r = client.post("/v1/predict", json={**valid_payload, field: value})
    assert r.status_code == 422


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
@pytest.mark.parametrize("field", ["temperature", "capacity"])
def test_predict_rejects_non_finite_numbers(client, valid_payload, field, value):
    # json= ne sait pas encoder NaN : on envoie le corps brut, comme le ferait un client mal codé
    body = json.dumps({**valid_payload, field: "__X__"}).replace('"__X__"', value)
    r = client.post("/v1/predict", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 422


# --- Contenu de la réponse (EX-03) ---


def test_prediction_between_zero_and_capacity(client, valid_payload):
    body = client.post("/v1/predict", json=valid_payload).json()
    assert 0 <= body["predicted_bikes"] <= valid_payload["capacity"]
    assert body["model_version"] == "0.0.0-test"


def test_target_timestamp_returned_in_utc(client, valid_payload):
    body = client.post("/v1/predict", json=valid_payload).json()
    assert datetime.fromisoformat(body["target_timestamp"]).utcoffset().total_seconds() == 0


def test_unknown_station_does_not_crash(client, valid_payload):
    # station jamais vue à l'entraînement (3 stations simulées) : OneHotEncoder(handle_unknown="ignore")
    r = client.post("/v1/predict", json={**valid_payload, "station_id": 999})
    assert r.status_code == 200


# --- Stretch : /v1/model et prédiction par lot ---


def test_model_info(client):
    r = client.get("/v1/model")
    assert r.status_code == 200
    assert r.json()["model_version"] == "0.0.0-test"
    assert "mae_model" in r.json()["metrics"]


def test_predict_batch_mixed_timezones(client, valid_payload):
    instances = [valid_payload, {**valid_payload, "station_id": 1, "timestamp": "2026-10-06T06:00:00Z"}]
    r = client.post("/v1/predict/batch", json={"instances": instances})
    assert r.status_code == 200
    predictions = r.json()["predictions"]
    assert [p["station_id"] for p in predictions] == [2, 1]
    # 08:00+02:00 et 06:00Z désignent le même instant : même cible, 07:00 UTC
    for p in predictions:
        assert datetime.fromisoformat(p["target_timestamp"]) == datetime(2026, 10, 6, 7, tzinfo=UTC)


@pytest.mark.parametrize("size", [0, 1001])
def test_predict_batch_rejects_bad_size(client, valid_payload, size):
    r = client.post("/v1/predict/batch", json={"instances": [valid_payload] * size})
    assert r.status_code == 422


def test_predict_batch_rejects_invalid_item(client, valid_payload):
    instances = [valid_payload, {**valid_payload, "bikes_available": 25}]
    r = client.post("/v1/predict/batch", json={"instances": instances})
    assert r.status_code == 422
