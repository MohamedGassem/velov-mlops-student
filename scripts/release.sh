#!/usr/bin/env bash
# Livraison du modèle champion sur la VM (S4).
# Le runner GitHub ne voit pas le réseau de l'école : cette étape tourne sur la VM,
# là où le serveur MLflow est joignable.
#
#   export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
#   ./scripts/release.sh            # exporte @champion, construit l'image, redémarre l'API
set -euo pipefail

: "${MLFLOW_TRACKING_URI:?MLFLOW_TRACKING_URI non défini}"
ALIAS="${1:-champion}"

python -m velov.export --alias "$ALIAS" --out models/
MODEL_VERSION=$(python -c "import json; print(json.load(open('models/metadata.json'))['registry']['version'])")
TAG="m${MODEL_VERSION}-$(git rev-parse --short HEAD)"

# Le tag de l'image dit quel modèle (version du registre) et quel code (commit) elle contient.
TAG="$TAG" docker compose up -d --build api
echo "API redémarrée avec velov-api:${TAG}"
docker compose ps api
