"""Orchestration du pipeline avec Prefect (S3) : ingestion -> dbt -> contrat.

Usage (depuis la racine du repo) :
    python -m velov.flow            # rejoue le bronze de démonstration, puis dbt et le contrat
    python -m velov.flow --live     # un instantané du vrai flux, puis dbt et le contrat
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from prefect import flow, task

from velov.contract import StationHourly, load
from velov.ingest import BRONZE, ingest_live, replay

FIXTURES = Path("data/fixtures")


@task(retries=3, retry_delay_seconds=[10, 30, 60])  # le flux public peut répondre en erreur
def ingest_snapshots(live: bool) -> int:
    if live:
        return int(ingest_live(BRONZE)["station_status"])
    written, _ = replay(FIXTURES, BRONZE)
    return written


@task
def dbt_build() -> None:
    # check=True : un test bloquant arrête le flow, la table gold n'est pas utilisée.
    subprocess.run(  # noqa: S603
        ["dbt", "build", "--profiles-dir", ".", "--quiet"],  # noqa: S607
        cwd="velov_dbt",
        check=True,
    )


@task
def check_contract() -> int:
    df = StationHourly.validate(load(), lazy=True)
    return len(df)


@flow(name="velov-pipeline", log_prints=True)
def pipeline(live: bool = False) -> None:
    new = ingest_snapshots(live)
    print(f"{new} nouveaux instantanés en bronze")
    dbt_build()
    print(f"table d'entraînement validée : {check_contract()} lignes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Vélo'v : ingestion, dbt, contrat.")
    parser.add_argument("--live", action="store_true", help="interroger le vrai flux au lieu du bronze de démo")
    pipeline(live=parser.parse_args().live)
