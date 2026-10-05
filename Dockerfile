# syntax=docker/dockerfile:1
# Image de serving de l'API Vélo'v (solution TP2).
# Build :  docker build -t velov-api:0.1.0 .
# Run   :  docker run --rm -p 8000:8000 velov-api:0.1.0

# Image de base paramétrable (utile pour un miroir interne ou un registre d'entreprise).
ARG PYTHON_IMAGE=python:3.12-slim

# ---------- Étape 1 : builder (outils de build, cache pip, sources) ----------
FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build

# Environnement virtuel isolé, copié tel quel dans l'image finale.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dépendances AVANT le code : cette couche reste en cache tant que
# requirements.txt ne change pas, même si le code change à chaque commit.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-deps .

# ---------- Étape 2 : runtime (le strict nécessaire pour servir) ----------
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    MODEL_DIR=/app/models

# Utilisateur dédié, sans privilèges.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
# Le modèle est embarqué dans l'image : image = code + dépendances + modèle, immuable.
# Fichiers possédés par root et seulement lisibles par appuser : il ne peut pas les modifier.
COPY models/ models/

USER appuser
EXPOSE 8000

# Docker ne connaît qu'un seul HEALTHCHECK. On le fait porter sur /ready : un conteneur
# incapable de prédire n'est pas exploitable. Un orchestrateur comme Kubernetes distingue
# ensuite liveness (/health) et readiness (/ready). Docker seul ne redémarre pas un
# conteneur unhealthy : le statut sert à l'observer et à ordonner les démarrages (compose).
# Pas de curl dans l'image slim : on interroge /ready avec Python.
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)"]

# Forme exec (tableau JSON) : uvicorn est le PID 1 et reçoit SIGTERM à l'arrêt.
CMD ["uvicorn", "velov.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
