"""Promotion d'un modèle : le challenger devient-il champion ? (S4)

Règle du projet, écrite avant de regarder les chiffres :
1. Le challenger et le champion sont évalués sur la MÊME fenêtre de test, la plus récente.
   Comparer des métriques calculées à l'entraînement, sur des fenêtres différentes,
   ne prouve rien.
2. Le challenger doit battre la baseline de persistance (EX-05).
3. Il doit battre le champion d'au moins MIN_GAIN (2 % de MAE par défaut) : en dessous,
   l'écart est du bruit et un changement de modèle a un coût (redéploiement, risque).

Par défaut, le script affiche sa décision sans rien changer : un humain valide.
Avec --apply, il déplace les alias (champion, previous-champion pour le retour arrière).

Usage :
    python -m velov.promote --data data/velov_history.csv            # décision seule
    python -m velov.promote --data data/velov_history.csv --apply    # décision appliquée
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mlflow import MlflowClient

from velov.features import make_training_frame
from velov.tracking import CHALLENGER, CHAMPION, MODEL_NAME, PREVIOUS, load_registered, version_by_alias
from velov.train import evaluate, load_table, temporal_split

MIN_GAIN = 0.02


def decide(challenger: dict, champion: dict | None, min_gain: float = MIN_GAIN) -> tuple[bool, str]:
    """Applique la règle de promotion à des métriques déjà calculées."""
    if challenger["mae_model"] >= challenger["mae_baseline_persistence"]:
        return False, "le challenger ne bat pas la baseline de persistance (EX-05)"
    if champion is None:
        return True, "aucun champion : premier modèle qui bat la baseline"
    target = champion["mae_model"] * (1 - min_gain)
    if challenger["mae_model"] <= target:
        return True, f"MAE {challenger['mae_model']} <= {target:.3f} (champion - {min_gain:.0%})"
    return False, f"MAE {challenger['mae_model']} > {target:.3f} : gain insuffisant sur le champion"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare challenger et champion, puis promeut ou non.")
    parser.add_argument("--data", type=Path, default=Path("data/velov_history.csv"))
    parser.add_argument("--test-days", type=int, default=14)
    parser.add_argument("--min-gain", type=float, default=MIN_GAIN)
    parser.add_argument("--apply", action="store_true", help="déplacer les alias (sinon : décision seule)")
    args = parser.parse_args()

    challenger_v = version_by_alias(CHALLENGER)
    if challenger_v is None:
        print("Aucune version avec l'alias challenger : rien à évaluer.")
        return 1
    champion_v = version_by_alias(CHAMPION)

    _, test_df = temporal_split(make_training_frame(load_table(args.data)), args.test_days)
    first, last = test_df["timestamp"].min(), test_df["timestamp"].max()
    print(f"Fenêtre de test : {first:%Y-%m-%d %H:%M} -> {last:%Y-%m-%d %H:%M} UTC, {len(test_df)} lignes")

    scores = {"challenger": evaluate(load_registered(challenger_v.version), test_df)}
    print(f"{f'challenger v{challenger_v.version}':<16}: MAE {scores['challenger']['mae_model']}")
    if champion_v is not None:
        scores["champion"] = evaluate(load_registered(champion_v.version), test_df)
        print(f"{f'champion v{champion_v.version}':<16}: MAE {scores['champion']['mae_model']}")
    print(f"{'persistance':<16}: MAE {scores['challenger']['mae_baseline_persistence']}")

    promote, reason = decide(scores["challenger"], scores.get("champion"), args.min_gain)
    print(f"Décision : {'PROMOUVOIR' if promote else 'GARDER le champion'} ({reason})")

    if promote and args.apply:
        client = MlflowClient()
        if champion_v is not None:
            client.set_registered_model_alias(MODEL_NAME, PREVIOUS, champion_v.version)
        client.set_registered_model_alias(MODEL_NAME, CHAMPION, challenger_v.version)
        client.set_model_version_tag(MODEL_NAME, challenger_v.version, "promotion", reason)
        print(f"Alias champion -> version {challenger_v.version}")
    elif promote:
        print("Rien n'a été modifié : relancer avec --apply pour promouvoir.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
