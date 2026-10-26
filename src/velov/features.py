"""Construction des features, partagée entre l'entraînement ET l'API.

Règle d'or : une seule implémentation des features, importée par les deux côtés.
Réécrire ce calcul dans l'API (copier-coller, autre langage, autre équipe) est la
cause n°1 du training-serving skew : le modèle reçoit en production des entrées
calculées différemment de celles vues à l'entraînement, sans aucune erreur visible.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Transform Silver layer data into Gold layer features for ML training.

    Creates time-based features, lag variables, and rolling statistics.
    """
    df = df.copy()

    # Identify the available bikes column dynamically
    target_col = None
    for candidate in ["available_bikes", "bikes_available", "bikes"]:
        if candidate in df.columns:
            target_col = candidate
            break

    if target_col is None:
        raise KeyError(
            f"Could not find bike availability column. Available columns: {list(df.columns)}"
        )

    # Cast timestamp and sort sequentially per station
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)

    # Time-based features
    df["hour"] = df["timestamp"].dt.hour
    df["day_of_week"] = df["timestamp"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)

    # Lag features (available bikes 1 hour and 2 hours ago)
    df["bikes_lag_1h"] = df.groupby("station_id")[target_col].shift(1)
    df["bikes_lag_2h"] = df.groupby("station_id")[target_col].shift(2)

    # Rolling statistics (3-hour moving average)
    df["bikes_rolling_3h"] = (
        df.groupby("station_id")[target_col]
        .transform(lambda x: x.rolling(window=3, min_periods=1).mean())
    )

    # Fill initial NaN values resulting from shifts
    df = df.bfill().ffill()

    return df


if __name__ == "__main__":
    data_path = "data/velov_history.csv"
    try:
        raw_df = pd.read_csv(data_path)
        features_df = compute_features(raw_df)
        print(f"Features computed successfully. Dataset shape: {features_df.shape}")
        print(features_df.head())
    except FileNotFoundError:
        print(f"File {data_path} not found. Run python -m velov.data first.")