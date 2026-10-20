#!/usr/bin/env bash
# TP2, niveau Stretch : vérifie qu'une image respecte la checklist de S2 (règles 5 à 8, plus la taille).
# Code retour 1 si un contrôle échoue : le script peut servir tel quel dans une CI.
#
# Usage, sur la VM (Linux ; le `date` de macOS ne connaît pas %N) :
#   chmod +x exercices/s2_audit/check_image.sh
#   ./exercices/s2_audit/check_image.sh velov-api:0.1.0
#
# Limite à discuter : la détection de secrets ne repère que des motifs simples.
set -euo pipefail

IMG="${1:?usage: $0 <image>}"
NAME="check-$$"
fail=0
ok() { echo "OK  $1"; }
ko() { echo "KO  $1"; fail=1; }

docker image inspect "$IMG" >/dev/null 2>&1 || { echo "Image introuvable : $IMG"; exit 2; }
docker run -d --name "$NAME" "$IMG" >/dev/null
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

# Règle 5 : utilisateur non-root (uid réel du process, pas ce qu'annonce le Dockerfile)
uid=$(docker exec "$NAME" id -u)
if [ "$uid" != "0" ]; then ok "non-root (uid $uid)"; else ko "le conteneur tourne en root"; fi

# Règle 6 : pas de secret visible dans l'historique des couches
if docker history --no-trunc "$IMG" | grep -Eiq '(api_key|secret|password|token)='; then
  ko "secret probable dans docker history"
else
  ok "aucun secret évident dans l'historique"
fi

# Règle 8 : HEALTHCHECK défini sur /ready, et conteneur sain (attente max 60 s)
if docker image inspect -f '{{json .Config.Healthcheck}}' "$IMG" | grep -q '/ready'; then
  status=none
  for _ in $(seq 1 30); do
    status=$(docker inspect -f '{{.State.Health.Status}}' "$NAME" 2>/dev/null || echo none)
    [ "$status" = healthy ] && break
    sleep 2
  done
  if [ "$status" = healthy ]; then ok "healthy sur /ready"; else ko "healthcheck /ready non sain ($status)"; fi
else
  ko "pas de HEALTHCHECK sur /ready"
fi

# Règle 7 : arrêt propre en moins de 3 s (uvicorn en PID 1 reçoit SIGTERM)
t0=$(date +%s%N)
docker stop "$NAME" >/dev/null
ms=$(( ($(date +%s%N) - t0) / 1000000 ))
if [ "$ms" -lt 3000 ]; then ok "arrêt en ${ms} ms"; else ko "arrêt lent (${ms} ms) : CMD en forme shell ?"; fi

# Indicateur : taille de l'image (seuil indicatif 800 Mo)
size=$(( $(docker image inspect -f '{{.Size}}' "$IMG") / 1000000 ))
if [ "$size" -lt 800 ]; then ok "taille ${size} Mo"; else ko "image lourde (${size} Mo) : base slim, multi-stage ?"; fi

exit "$fail"
