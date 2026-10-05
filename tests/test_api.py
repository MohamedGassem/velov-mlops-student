from fastapi.testclient import TestClient


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_when_model_loaded(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["model_version"] == "0.0.0-test"


def test_ready_returns_503_without_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))  # dossier vide
    from velov.api.main import app

    with TestClient(app) as c:
        assert c.get("/health").status_code == 200  # vivant...
        assert c.get("/ready").status_code == 503  # ...mais pas prêt


def test_predict_valid(client, valid_payload):
    r = client.post("/v1/predict", json=valid_payload)
    assert r.status_code == 200
    body = r.json()
    assert 0 <= body["predicted_bikes"] <= valid_payload["capacity"]
    assert body["target_timestamp"] == "2026-10-06T07:00:00Z"  # t + 1 h, renvoyé en UTC
    assert "X-Process-Time-Ms" in r.headers


def test_predict_rejects_bikes_above_capacity(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "bikes_available": 25})
    assert r.status_code == 422


def test_predict_rejects_unknown_field(client, valid_payload):
    r = client.post("/v1/predict", json={**valid_payload, "foo": 1})
    assert r.status_code == 422


def test_predict_rejects_timestamp_without_timezone(client, valid_payload):
    # "2026-10-06T08:00:00" : 8 h à Lyon ou 8 h UTC ? Le contrat refuse plutôt que deviner.
    r = client.post("/v1/predict", json={**valid_payload, "timestamp": "2026-10-06T08:00:00"})
    assert r.status_code == 422
    assert r.json()["detail"][0]["type"] == "timezone_aware"


def test_same_instant_same_prediction_whatever_the_offset(client, valid_payload):
    local = client.post("/v1/predict", json=valid_payload).json()
    utc = client.post("/v1/predict", json={**valid_payload, "timestamp": "2026-10-06T06:00:00Z"}).json()
    assert local == utc


def test_predict_rejects_missing_field(client, valid_payload):
    payload = {k: v for k, v in valid_payload.items() if k != "temperature"}
    assert client.post("/v1/predict", json=payload).status_code == 422


def test_unknown_station_still_predicts(client, valid_payload):
    # OneHotEncoder(handle_unknown="ignore") : une nouvelle station ne fait pas planter l'API
    r = client.post("/v1/predict", json={**valid_payload, "station_id": 999})
    assert r.status_code == 200


def test_batch(client, valid_payload):
    items = [valid_payload, {**valid_payload, "station_id": 1, "bikes_available": 0}]
    r = client.post("/v1/predict/batch", json={"items": items})
    assert r.status_code == 200
    assert len(r.json()["predictions"]) == 2


def test_batch_rejects_empty(client):
    assert client.post("/v1/predict/batch", json={"items": []}).status_code == 422


def test_tampered_model_is_not_loaded(model_dir, tmp_path, monkeypatch):
    import shutil

    tampered = tmp_path / "models"
    shutil.copytree(model_dir, tampered)
    with (tampered / "model.joblib").open("ab") as f:
        f.write(b"tampered")
    monkeypatch.setenv("MODEL_DIR", str(tampered))
    from velov.api.main import app

    with TestClient(app) as c:
        assert c.get("/ready").status_code == 503
