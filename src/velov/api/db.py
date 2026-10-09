"""Journal des prédictions dans PostgreSQL. Actif seulement si DATABASE_URL est défini."""

from __future__ import annotations

import logging
import os

import psycopg

logger = logging.getLogger("velov.api.db")

DDL = """
create table if not exists predictions (
    id bigserial primary key,
    created_at timestamptz not null default now(),
    station_id integer not null,
    observed_at timestamptz not null,
    target_timestamp timestamptz not null,
    capacity integer not null,
    bikes_available integer not null,
    predicted_bikes double precision not null,
    model_version text not null
)
"""

INSERT = """
insert into predictions (station_id, observed_at, target_timestamp, capacity,
                         bikes_available, predicted_bikes, model_version)
values (%s, %s, %s, %s, %s, %s, %s)
"""


def init_db() -> None:
    url = os.getenv("DATABASE_URL")
    if not url:
        return
    with psycopg.connect(url, connect_timeout=5) as conn:
        conn.execute(DDL)


def log_prediction(values: tuple) -> None:
    """Une panne de la base ne doit pas empêcher de répondre : on journalise l'erreur."""
    url = os.getenv("DATABASE_URL")
    if not url:
        return
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.execute(INSERT, values)
    except psycopg.Error:
        logger.exception("Prédiction non enregistrée en base")