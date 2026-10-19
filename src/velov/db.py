"""Journalisation des predictions en Postgres.

Si DATABASE_URL n'est pas defini (tests, dev sans compose), make_engine renvoie None
et log_prediction est un no-op : l'API prédit toujours, meme sans base.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)
from sqlalchemy.engine import Engine

logger = logging.getLogger("velov.db")

metadata = MetaData()

predictions = Table(
    "predictions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("station_id", Integer, nullable=False, index=True),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("bikes_available", Integer, nullable=False),
    Column("temperature", Float, nullable=False),
    Column("is_raining", Boolean, nullable=False),
    Column("target_timestamp", DateTime(timezone=True), nullable=False),
    Column("predicted_bikes", Float, nullable=False),
    Column("model_version", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def make_engine() -> Engine | None:
    """Cree l'engine SQLAlchemy et la table si DATABASE_URL est defini, sinon None."""
    url = os.getenv("DATABASE_URL")
    if not url:
        logger.info("DATABASE_URL non defini : journalisation desactivee")
        return None
    engine = create_engine(url, pool_pre_ping=True, future=True)
    metadata.create_all(engine)
    logger.info("Base de journalisation prete")
    return engine


def log_prediction(engine: Engine | None, row: dict[str, Any]) -> None:
    """Insere une prediction en base. Ne fait rien si pas d'engine.

    En cas d'erreur base (connexion coupee, table verrouillee...), on log et on continue :
    une prediction renvoyee au client ne doit pas echouer parce que la journalisation echoue.
    """
    if engine is None:
        return
    try:
        with engine.begin() as conn:
            conn.execute(predictions.insert().values(**row, created_at=datetime.now(UTC)))
    except Exception:
        logger.exception("Echec journalisation prediction (on continue)")
