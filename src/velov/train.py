"""Entraînement du modèle v0 et production de l'artefact distribuable.

Ce qu'on distribue (S1) n'est pas "un modèle" mais un paquet :
- le pipeline sklearn complet (prétraitement + modèle) -> models/model.joblib
- ses métadonnées (version, features, métriques, empreinte SHA-256, versions des
  librairies, hash des données) -> models/metadata.json

Usage :
    python -m velov.train --data data/velov_history.csv --out models/
    python -m velov.train --data data/velov_history.csv --out models/ --mlflow
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime


from pathlib import Path
import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

from velov.data import simulate
from velov.features import compute_features


def train_model(
    days: int = 90,
    n_stations: int = 20,
    seed: int = 42,
    model_path: Path = Path("models/model.joblib"),
) -> None:
    """Train a Random Forest model on generated Gold features and save the artifact."""
    print("Generating simulation data...")
    raw_df = simulate(days=days, n_stations=n_stations, seed=seed)

    print("Computing Gold layer features...")
    df = compute_features(raw_df)

    # Define features and target variable
    feature_cols = [
        "capacity",
        "temperature",
        "is_raining",
        "hour",
        "day_of_week",
        "is_weekend",
        "bikes_lag_1h",
        "bikes_lag_2h",
        "bikes_rolling_3h",
    ]
    target_col = "bikes_available"

    X = df[feature_cols]
    y = df[target_col]

    # Time-based split (80% train, 20% test)
    split_idx = int(len(df) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    print(f"Training RandomForestRegressor on {len(X_train):,} samples...")
    model = RandomForestRegressor(n_estimators=100, random_state=seed, n_jobs=-1)
    model.fit(X_train, y_train)

    # Evaluate model
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)
    rmse = mean_squared_error(y_test, predictions) ** 0.5

    print(f"Model Evaluation Metrics -> MAE: {mae:.4f} | RMSE: {rmse:.4f}")

    # Save model artifact
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    print(f"Model artifact successfully saved to: {model_path}")


if __name__ == "__main__":
    train_model()