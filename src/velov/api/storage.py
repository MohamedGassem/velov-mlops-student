"""Journalisation des prédictions en base (introduite en S2 avec docker compose).

Pourquoi journaliser ? Sans trace des entrées et sorties, impossible de mesurer
la performance réelle quand la vérité terrain arrive (H+1), ni de détecter une
dérive des données (S6). PostgreSQL dans le compose, SQLite dans les tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
)

metadata = MetaData()

predictions = Table(
    "predictions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("station_id", Integer, nullable=False),
    Column("observed_at", DateTime(timezone=True), nullable=False),  # UTC, comme tout le système
    Column("capacity", Integer, nullable=False),
    Column("bikes_available", Integer, nullable=False),
    Column("temperature", Float, nullable=False),
    Column("is_raining", Boolean, nullable=False),
    Column("predicted_bikes", Float, nullable=False),
    Column("model_version", String(32), nullable=False),
)


def init(database_url: str) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True)
    metadata.create_all(engine)  # S2 : suffisant. En production : migrations (Alembic).
    return engine


def log_predictions(engine: Engine, items, responses) -> None:
    now = datetime.now(UTC)
    rows = [
        {
            "created_at": now,
            "station_id": item.station_id,
            "observed_at": item.timestamp,
            "capacity": item.capacity,
            "bikes_available": item.bikes_available,
            "temperature": item.temperature,
            "is_raining": item.is_raining,
            "predicted_bikes": resp.predicted_bikes,
            "model_version": resp.model_version,
        }
        for item, resp in zip(items, responses, strict=True)
    ]
    with engine.begin() as conn:
        conn.execute(insert(predictions), rows)
