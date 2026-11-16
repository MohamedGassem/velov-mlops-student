"""Promotion of a traced model to the MLflow `challenger` alias."""

from __future__ import annotations

import argparse

MODEL_NAME = "velov-availability"


def promotion_failures(status: str, metrics: dict[str, float], tags: dict[str, str]) -> list[str]:
    """Apply the three documented promotion conditions."""
    failures = []
    if status != "FINISHED":
        failures.append("run non terminé")
    if metrics.get("mae_model", float("inf")) >= metrics.get("mae_baseline_persistence", float("inf")):
        failures.append("MAE modèle non meilleure que la baseline")
    if len(tags.get("data_sha256", "")) != 64:
        failures.append("empreinte des données absente ou invalide")
    return failures


def promote_challenger(run_id: str) -> str:
    import mlflow

    client = mlflow.MlflowClient()
    run = client.get_run(run_id)
    failures = promotion_failures(run.info.status, run.data.metrics, run.data.tags)
    if failures:
        raise ValueError("Promotion refusée : " + "; ".join(failures))

    registered = mlflow.register_model(f"runs:/{run_id}/model", MODEL_NAME)
    client.set_registered_model_alias(MODEL_NAME, "challenger", registered.version)
    return registered.version


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote a valid MLflow run to challenger.")
    parser.add_argument("run_id")
    args = parser.parse_args()
    print(f"challenger version: {promote_challenger(args.run_id)}")


if __name__ == "__main__":
    main()
