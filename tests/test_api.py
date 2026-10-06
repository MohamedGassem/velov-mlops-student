"""Tests de l'API. Les fixtures (client, valid_payload, model_dir) sont dans conftest.py."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient


def test_predict_valid(client, valid_payload):
    r = client.post("/v1/predict", json=valid_payload)
    assert r.status_code == 200
    # 8 h à Lyon (+02:00) + 1 h = 7 h UTC, quel que soit le fuseau dans lequel l'API répond
    target = datetime.fromisoformat(r.json()["target_timestamp"])
    assert target == datetime(2026, 10, 6, 7, tzinfo=UTC)


def test_predict_rejects_bikes_above_capacity(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "bikes_available": 25})
    assert r.status_code == 422


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_when_model_loaded(client):
    r = client.get("/ready")
    assert r.status_code == 200


def test_ready_without_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    from velov.api.main import app

    with TestClient(app) as c:
        r = c.get("/ready")
    assert r.status_code == 503


def test_unknown_field_rejected(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "unknown_field": 42})
    assert r.status_code == 422


def test_timestamp_without_timezone_rejected(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "timestamp": "2026-10-06T08:00:00"})
    assert r.status_code == 422


def test_prediction_within_bounds(client, valid_payload):
    r = client.post("/v1/predict", json=valid_payload)
    assert r.status_code == 200
    data = r.json()
    assert 0 <= data["predicted_bikes"] <= valid_payload["capacity"]
