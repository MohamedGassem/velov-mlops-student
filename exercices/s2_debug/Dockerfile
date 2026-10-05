# Exercice de debug S2 : cette image se construit, mais le service ne marche pas.
# Trois problèmes se cachent dans ce fichier.
# Ils apparaissent l'un après l'autre : corrigez, reconstruisez, recommencez.
#
# Depuis la racine du repo :
#   docker build -f exercices/s2_debug/Dockerfile -t velov-debug .
#   docker run -d --name velov-debug -p 8001:8000 velov-debug
#   curl localhost:8001/ready
#
# Outils autorisés : docker ps -a, docker logs, docker exec, docker inspect, docker port.
# Pas d'IA pour cet exercice : le but est d'apprendre à lire les symptômes.

ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONUNBUFFERED=1 MODEL_DIR=/app/model
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY models/ models/
ENV PYTHONPATH=/app/src

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "velov.main:app", "--host", "127.0.0.1", "--port", "8000"]
