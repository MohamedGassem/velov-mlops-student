FROM python:3.12-slim

ENV PIP_NO_CACHE_DIR=1 \
    MLFLOW_DISABLE_TELEMETRY=true

RUN pip install "mlflow==3.16.1" "psycopg[binary]==3.3.6" \
    && useradd --create-home --uid 10001 mlflow \
    && mkdir /mlartifacts \
    && chown mlflow:mlflow /mlartifacts

USER mlflow
WORKDIR /mlartifacts

EXPOSE 5000
