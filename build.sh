#!/usr/bin/env bash
# Build l'image avec deux tags :
#   - la version du modele (lue dans models/metadata.json)
#   - le short SHA du commit git qui l'a produite
# Les deux repondent a des questions differentes :
#   "quelle version tourne ?"  -> velov-api:0.1.0
#   "quel code l'a produite ?" -> velov-api:f687c9e
set -euo pipefail

IMAGE=${IMAGE:-velov-api}

if [[ ! -f models/metadata.json ]]; then
    echo "models/metadata.json introuvable : lancer d'abord python -m velov.train" >&2
    exit 1
fi

VERSION=$(python3 -c "import json; print(json.load(open('models/metadata.json'))['model_version'])")
COMMIT=$(git rev-parse --short HEAD)

if [[ -n "$(git status --porcelain)" ]]; then
    COMMIT="${COMMIT}-dirty"
    echo "Attention : le repo a des modifications non commitees, tag commit = ${COMMIT}" >&2
fi

echo "Build ${IMAGE}:${VERSION} + ${IMAGE}:${COMMIT}"
docker build \
    -t "${IMAGE}:${VERSION}" \
    -t "${IMAGE}:${COMMIT}" \
    .

echo
echo "Tags poses :"
docker images "${IMAGE}" --format "  {{.Repository}}:{{.Tag}}  (id {{.ID}}, {{.Size}})"
