# Pinned to the Linux amd64 image digest used by Docker Desktop on this project.
FROM python:3.13-slim@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024

# Prevents creation of .pyc files and ensures direct output of logs
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MODEL_DIR=/app/models

WORKDIR /app

# Create a non-privileged user for the serving process.
RUN adduser --disabled-password --gecos "" appuser

# Cache optimization: dependency installation first.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install the project package so its package metadata and src layout are validated.
COPY pyproject.toml .
COPY --chown=appuser:appuser src ./src
RUN pip install --no-cache-dir --no-deps .

# The model is downloaded by the deployment pipeline into this directory.
RUN mkdir -p /app/models && chown appuser:appuser /app/models && \
    python -c "import velov; import velov.api.main"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')" || exit 1

CMD ["uvicorn", "velov.api.main:app", "--host", "0.0.0.0", "--port", "8000"]