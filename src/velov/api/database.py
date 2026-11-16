import os

from sqlalchemy import create_engine, text


def initialise_database() -> None:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        return

    engine = create_engine(database_url)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS predictions (
                    id BIGSERIAL PRIMARY KEY,
                    station_id INTEGER NOT NULL,
                    input_timestamp TIMESTAMPTZ NOT NULL,
                    target_timestamp TIMESTAMPTZ NOT NULL,
                    capacity INTEGER NOT NULL,
                    bikes_available INTEGER NOT NULL,
                    temperature DOUBLE PRECISION NOT NULL,
                    is_raining BOOLEAN NOT NULL,
                    predicted_bikes DOUBLE PRECISION NOT NULL,
                    model_version TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def save_prediction(payload, target_timestamp, predicted_bikes, model_version) -> None:
    """Enregistre une prédiction réussie et les données qui l'ont produite."""
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        # Le mode local du TP1 n'utilise pas PostgreSQL. En Docker Compose,
        # DATABASE_URL est toujours définie et la prédiction est tracée.
        return

    engine = create_engine(database_url)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO predictions (
                    station_id,
                    input_timestamp,
                    target_timestamp,
                    capacity,
                    bikes_available,
                    temperature,
                    is_raining,
                    predicted_bikes,
                    model_version
                )
                VALUES (
                    :station_id,
                    :input_timestamp,
                    :target_timestamp,
                    :capacity,
                    :bikes_available,
                    :temperature,
                    :is_raining,
                    :predicted_bikes,
                    :model_version
                )
                """
            ),
            {
                "station_id": payload.station_id,
                "input_timestamp": payload.timestamp,
                "target_timestamp": target_timestamp,
                "capacity": payload.capacity,
                "bikes_available": payload.bikes_available,
                "temperature": payload.temperature,
                "is_raining": payload.is_raining,
                "predicted_bikes": predicted_bikes,
                "model_version": model_version,
            },
        )
