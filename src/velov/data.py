"""Simulateur de données Vélo'v (disponibilité horaire par station).

Pourquoi un simulateur ?
- Les sessions S1-S2 portent sur l'industrialisation, pas sur l'accès aux données :
  un jeu reproductible (seed fixe) garantit que tout le monde obtient les mêmes chiffres.
- En S3, ce module est remplacé par une ingestion de l'open data de la Métropole de Lyon,
  avec le même schéma de sortie. C'est le "data contract" du projet.

Schéma de sortie (une ligne par station et par heure) :
    station_id:int, timestamp:datetime64 en UTC, capacity:int, bikes_available:int,
    temperature:float (°C), is_raining:bool

Convention horaire du projet : tous les instants sont stockés et échangés en UTC.
Les usages, eux, suivent l'heure locale de Lyon (départs vers 8 h, retours vers 18 h) :
les profils ci-dessous sont donc calculés en heure locale, puis l'instant est converti en UTC.

Usage :
    python -m velov.data --days 90 --stations 20 --out data/velov_history.csv
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

# Profile definitions (occupancy rate 0-1 depending on hour for weekdays).
# residential : empties in the morning, fills in the evening.
# business    : inverse of residential.
# leisure     : less sensitive to office hours, higher load on weekends.
PROFILES = ("residential", "business", "leisure")


def _weekday_occupancy(hour: np.ndarray, profile: str) -> np.ndarray:
    morning = np.exp(-((hour - 8.5) ** 2) / 3.0)
    evening = np.exp(-((hour - 18.0) ** 2) / 4.0)
    if profile == "residential":
        return 0.65 - 0.45 * morning + 0.25 * evening
    if profile == "business":
        return 0.25 + 0.55 * morning - 0.15 * evening
    return 0.45 + 0.10 * np.sin((hour - 6) / 24 * 2 * np.pi)


def _weekend_occupancy(hour: np.ndarray, profile: str) -> np.ndarray:
    afternoon = np.exp(-((hour - 15.0) ** 2) / 8.0)
    if profile == "leisure":
        return 0.40 - 0.30 * afternoon
    return 0.55 - 0.15 * afternoon


def simulate(
    days: int = 90,
    n_stations: int = 20,
    start: str = "2026-06-01",
    seed: int = 42,
) -> pd.DataFrame:
    """Génère un historique horaire synthétique et réaliste.

    Raises:
        ValueError: si les paramètres sont hors bornes.
    """
    if days < 2:
        raise ValueError("days doit être >= 2 (il faut au moins une heure suivante pour la cible)")
    if not 1 <= n_stations <= 500:
        raise ValueError("n_stations doit être compris entre 1 et 500")

    rng = np.random.default_rng(seed)
    # Local time to simulate usage, stored in UTC.
    timestamps = pd.date_range(start=start, periods=days * 24, freq="h", tz="Europe/Paris")
    hour = np.asarray(timestamps.hour)
    is_weekend = np.asarray(timestamps.dayofweek) >= 5

    # Weather shared across all stations (single city).
    daily_temp = 22 + 6 * np.sin(np.arange(days) / days * np.pi) + rng.normal(0, 2, days)
    temperature = np.repeat(daily_temp, 24) + 5 * np.sin((hour - 9) / 24 * 2 * np.pi)
    is_raining = rng.random(len(timestamps)) < 0.08

    frames = []
    for station_id in range(1, n_stations + 1):
        profile = PROFILES[(station_id - 1) % len(PROFILES)]
        capacity = int(rng.integers(15, 41))
        occ = np.where(
            is_weekend,
            _weekend_occupancy(hour, profile),
            _weekday_occupancy(hour, profile),
        )
        # Rain reduces departures: stations stay fuller.
        occ = occ + 0.10 * is_raining
        # Autocorrelated noise (AR(1)): availability depends on previous hour.
        noise = np.zeros(len(timestamps))
        for t in range(1, len(noise)):
            noise[t] = 0.7 * noise[t - 1] + rng.normal(0, 0.05)
        bikes = np.clip(np.rint((occ + noise) * capacity), 0, capacity).astype(int)

        frames.append(
            pd.DataFrame(
                {
                    "station_id": station_id,
                    "timestamp": timestamps.tz_convert("UTC"),
                    "capacity": capacity,
                    "bikes_available": bikes,
                    "temperature": temperature.round(1),
                    "is_raining": is_raining,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def ingest_to_db(df: pd.DataFrame, db_url: str) -> None:

    create_table_sql = """
    CREATE TABLE IF NOT EXISTS raw_station_status (
        station_id INT,
        timestamp TIMESTAMPTZ,
        capacity INT,
        bikes_available INT,
        temperature FLOAT,
        is_raining BOOLEAN,
        PRIMARY KEY (station_id, timestamp)
    );
    """

    insert_sql = """
    INSERT INTO raw_station_status (
        station_id, timestamp, capacity, bikes_available, temperature, is_raining
    ) VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (station_id, timestamp) DO NOTHING;
    """

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(create_table_sql)
            data_to_insert = [
                (
                    int(row.station_id),
                    row.timestamp.to_pydatetime(),
                    int(row.capacity),
                    int(row.bikes_available),
                    float(row.temperature),
                    bool(row.is_raining),
                )
                for row in df.itertuples(index=False)
            ]
            cur.executemany(insert_sql, data_to_insert)
        conn.commit()
    print(f"Successfully processed {len(df):,} rows into PostgreSQL bronze table.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère un historique Vélo'v synthétique.")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--stations", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("data/velov_history.csv"))
    parser.add_argument("--db", action="store_true", help="Ingest into PostgreSQL bronze table")
    args = parser.parse_args()

    df = simulate(days=args.days, n_stations=args.stations, seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"{len(df):,} lines written to {args.out}")

    if args.db:
        # Utilisation explicite du mot de passe 'velov' validé par le conteneur
        db_url = "postgresql://velov:velov-local-2026@localhost:5433/velov"
        ingest_to_db(df, db_url)
    
        print(f"Connecting with database URL: {db_url}")
        ingest_to_db(df, db_url)


if __name__ == "__main__":
    main()