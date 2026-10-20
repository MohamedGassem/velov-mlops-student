"""Contrat de la table d'entraînement (S3) : celle du simulateur en S1-S2, puis du pipeline.

Vérifié deux fois : par dbt à la publication (contrat enforced, tests), et ici à la lecture,
juste avant l'entraînement (exigence EX-12).

Usage (depuis la racine du repo, après `dbt build`) :
    python -m velov.contract
"""

from __future__ import annotations

import sys

import duckdb
import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series

GOLD_PATH = "data/velov.duckdb"


class StationHourly(pa.DataFrameModel):
    # coerce uniquement sur les entiers : appliqué au timestamp, il ajoutait un fuseau
    # au lieu de signaler son absence (piège rencontré en préparant le cours).
    station_id: Series[int] = pa.Field(gt=0, coerce=True)
    timestamp: Series[pd.DatetimeTZDtype] = pa.Field(dtype_kwargs={"unit": "us", "tz": "UTC"})
    capacity: Series[int] = pa.Field(ge=1, le=80, coerce=True)
    bikes_available: Series[int] = pa.Field(ge=0, coerce=True)
    temperature: Series[float] = pa.Field(ge=-25, le=50)
    is_raining: Series[bool]

    @pa.dataframe_check
    def bikes_le_capacity(cls, df: pd.DataFrame) -> Series[bool]:
        return df["bikes_available"] <= df["capacity"]

    class Config:
        strict = True  # aucune colonne en trop
        unique = ["station_id", "timestamp"]  # une ligne par station et par heure


def load(path: str = GOLD_PATH) -> pd.DataFrame:
    """Lit la table gold. dbt est le seul écrivain de la base : on l'ouvre en lecture seule."""
    with duckdb.connect(path, read_only=True) as con:
        con.sql("SET TimeZone = 'UTC'")
        return con.sql("select * from station_hourly").df()


def main() -> int:
    df = load()
    try:
        StationHourly.validate(df, lazy=True)
    except pa.errors.SchemaErrors as err:
        print(err.failure_cases[["column", "check", "failure_case"]].head(10).to_string())
        return 1
    print(f"contrat respecté : {len(df)} lignes, {df.station_id.nunique()} stations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
