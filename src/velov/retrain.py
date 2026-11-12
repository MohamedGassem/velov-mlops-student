"""Réentraînement : entraîner, tracer, enregistrer, puis décider (S4).

Appelé à la fin du pipeline de S3 (après `dbt build`), selon un déclencheur choisi :
planifié (chaque lundi), volume de nouvelles données, ou alerte de dérive (S6).

La promotion reste une décision séparée : par défaut, ce script enregistre un challenger
et affiche la décision ; c'est un humain qui lance `velov.promote --apply`.
Avec --auto-promote, la règle de promote.py est appliquée sans validation humaine.

Usage :
    python -m velov.retrain --data data/velov.duckdb --version 0.5.0
    python -m velov.retrain --data data/velov.duckdb --version 0.5.0 --auto-promote
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from velov.tracking import log_training
from velov.train import train


def run(data: Path, version: str, auto_promote: bool = False, test_days: int = 14) -> int:
    with tempfile.TemporaryDirectory() as tmp:  # le paquet part dans le run, pas dans models/
        metadata = train(data, Path(tmp), version=version, test_days=test_days)
        info = log_training(metadata, Path(tmp), register=True)
    print(f"Challenger enregistré : version {info['version']} (run {info['run_id'][:8]})")
    cmd = [sys.executable, "-m", "velov.promote", "--data", str(data), "--test-days", str(test_days)]
    if auto_promote:
        cmd.append("--apply")
    return subprocess.run(cmd, check=False).returncode  # noqa: S603


def main() -> int:
    parser = argparse.ArgumentParser(description="Réentraîne, enregistre un challenger, évalue la promotion.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--version", required=True, help="version sémantique du nouveau modèle")
    parser.add_argument("--auto-promote", action="store_true")
    parser.add_argument("--test-days", type=int, default=14, help="fenêtre de test commune (jours les plus récents)")
    args = parser.parse_args()
    return run(args.data, args.version, args.auto_promote, args.test_days)


if __name__ == "__main__":
    sys.exit(main())
