"""Tests de modèle : ils échouent si le modèle se dégrade, pas seulement si le code plante (S4)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from velov.data import simulate
from velov.promote import decide
from velov.train import train


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("quality")
    data_path = workdir / "history.csv"
    simulate(days=30, n_stations=5, seed=1).to_csv(data_path, index=False)
    return data_path, train(data_path, workdir / "models", version="0.0.0-ci", test_days=7)


def test_model_beats_persistence_baseline(trained):
    """EX-05, automatisée : le modèle doit battre la persistance sur le test temporel."""
    _, metadata = trained
    m = metadata["metrics"]
    assert m["mae_model"] < m["mae_baseline_persistence"], m


def test_same_seed_same_artifact(trained, tmp_path):
    """Reproductibilité : mêmes données, même code, même graine => même artefact, octet pour octet."""
    data_path, first = trained
    again = train(data_path, tmp_path / "again", version="0.0.0-ci", test_days=7)
    assert again["artifact"]["sha256"] == first["artifact"]["sha256"]


def test_metadata_traces_data_and_params(trained):
    _, metadata = trained
    assert len(metadata["data"]["sha256"]) == 64
    assert {"seed", "learning_rate", "max_iter", "test_days"} <= set(metadata["params"])
    json.dumps(metadata)  # sérialisable tel quel


def test_metadata_is_utf8(trained, tmp_path):
    """metadata.json entraîné sous Windows doit rester lisible dans l'image Linux (UTF-8)."""
    data_path, _ = trained
    train(data_path, tmp_path, version="0.0.0-ci", test_days=7)
    json.loads((tmp_path / "metadata.json").read_bytes().decode("utf-8"))


def test_training_refuses_naive_timestamps(tmp_path):
    df = simulate(days=5, n_stations=2, seed=0)
    df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    path = tmp_path / "naive.csv"
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="fuseau"):
        train(path, tmp_path / "m", test_days=1)


@pytest.mark.parametrize(
    ("challenger", "champion", "expected"),
    [
        ({"mae_model": 1.40, "mae_baseline_persistence": 1.30}, None, False),  # pire que la baseline
        ({"mae_model": 1.20, "mae_baseline_persistence": 1.80}, None, True),  # premier champion
        ({"mae_model": 1.33, "mae_baseline_persistence": 1.80}, {"mae_model": 1.34}, False),  # bruit
        ({"mae_model": 1.20, "mae_baseline_persistence": 1.80}, {"mae_model": 1.34}, True),  # vrai gain
    ],
)
def test_promotion_rule(challenger, champion, expected):
    promote, _ = decide(challenger, champion)
    assert promote is expected


def test_simulated_history_is_utc():
    ts = simulate(days=2, n_stations=1)["timestamp"]
    assert isinstance(ts.dtype, pd.DatetimeTZDtype) and str(ts.dt.tz) == "UTC"
