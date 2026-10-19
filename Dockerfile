# Checklist S2 : base slim versionnée, deps epinglees avant le code, multi-stage,
# .dockerignore, non-root, aucun secret, CMD en JSON, HEALTHCHECK sur /ready.

ARG PYTHON_IMAGE=python:3.12-slim

# --- Etape 1 : builder (atelier, jete apres le build) ---------------------
FROM ${PYTHON_IMAGE} AS builder
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Les deps bougent peu : on les installe avant le code pour profiter du cache.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-deps .

# --- Etape 2 : runtime (ce qui part en production) ------------------------
FROM ${PYTHON_IMAGE} AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    MODEL_DIR=/app/models \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY models/ models/

USER appuser
EXPOSE 8000

# "Sain" = pret a predire : on interroge /ready, pas /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/ready').read()"]

# CMD en JSON pour que uvicorn soit PID 1 et recoive SIGTERM proprement.
CMD ["uvicorn", "velov.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
