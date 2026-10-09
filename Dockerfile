# Fixed base image
FROM python:3.13-slim@sha256:8fb4cfa1a2616d7b8e0c2175cc6ad68f5729c34ea8488c0b360d2934b7be9024

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    MODEL_DIR=/app/models

WORKDIR /app

# Security: Creation of a non-privileged use
RUN adduser --disabled-password --gecos "" appuser

# Cache optimization: Dependency installation first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copying source code and setting ownership
COPY --chown=appuser:appuser pyproject.toml .
COPY --chown=appuser:appuser src ./src

# Local package install
RUN pip install --no-cache-dir --no-deps .

# Models directory creation and ownership setting
RUN mkdir -p /app/models && chown -R appuser:appuser /app

# Setting the user to a non-privileged user for security
USER appuser

# Test imports as app user to ensure everything is set up correctly
RUN python -c "import velov; import velov.api.main"

EXPOSE 8000

# Targeted healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready')" || exit 1

CMD ["uvicorn", "velov.api.main:app", "--host", "0.0.0.0", "--port", "8000"]