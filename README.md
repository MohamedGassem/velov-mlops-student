# velov-mlops

Projet fil rouge du cours **Industrialisation de l'IA dans le Cloud** (M2 Data Engineering / IA).

Objectif métier : prédire, pour chaque station Vélo'v, le nombre de vélos disponibles **dans une heure**,
et servir cette prédiction via une API fiable, conteneurisée, puis déployée (on-premise et cloud).

## Progression par session

Chaque étape du cours correspond à un tag git. Absent ou bloqué : repartez du tag de fin de la session précédente.

| Tag | Contenu |
|---|---|
| `s1-start` | Données simulées, features, entraînement. API à compléter (TP1) |
| `s1-end` | Modèle v0 servi par FastAPI, tests pytest |
| `s2-end` | Image Docker multi-stage, compose API + PostgreSQL, journalisation des prédictions |
| `s3-end` | Pipeline : collecte bronze, dbt silver et gold sur DuckDB, contrat Pandera, flow Prefect |

```bash
git checkout s1-end          # récupérer l'état de fin de S1
git checkout -b mon-binome   # travailler sur sa propre branche
```

## Démarrage rapide

Prérequis : Python 3.11+ (3.12 recommandé), git, Docker Desktop ou Docker Engine.

```bash
python -m venv .venv
source .venv/bin/activate            # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e .                     # rend le package velov importable

python -m velov.data                 # génère data/velov_history.csv (simulateur, seed fixe)
python -m velov.train                # entraîne et écrit models/model.joblib + models/metadata.json
python -m velov.train --mlflow       # idem + journalisation MLflow (puis : mlflow ui)
pytest                               # tests
uvicorn velov.api.main:app --reload  # API sur http://127.0.0.1:8000/docs (--reload : en dev uniquement)
```

Exemple d'appel :

```bash
curl -X POST http://127.0.0.1:8000/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"station_id": 3, "timestamp": "2026-10-06T08:00:00+02:00", "capacity": 20,
       "bikes_available": 12, "temperature": 14.5, "is_raining": false}'
```

Le `timestamp` doit porter un fuseau (`+02:00`, `Z`...) : sans fuseau, l'API répond 422.
Les instants sont renvoyés et journalisés en UTC (`"target_timestamp": "2026-10-06T07:00:00Z"`).

## Exigences du projet

Le service doit respecter les exigences de [docs/exigences.md](docs/exigences.md), de S1 à S9.
Chaque rendu indique celles qu'il couvre et comment le vérifier.

## Docker (S2)

```bash
python -m velov.data && python -m velov.train   # l'image embarque models/ : il doit exister
docker build -t velov-api:0.1.0 .
docker run --rm -p 8000:8000 velov-api:0.1.0

cp .env.example .env                            # puis changer POSTGRES_PASSWORD
docker compose up --build -d
docker compose logs -f api
docker compose down                             # -v pour supprimer aussi le volume Postgres
```

## Pipeline de données (S3)

```bash
python -m velov.ingest --replay data/fixtures     # bronze de démonstration (48 h, 20 stations)
python -m velov.ingest                            # ou un instantané du vrai flux de la Métropole
cd velov_dbt && dbt build --profiles-dir . && cd ..   # silver et gold, tests et contrat
python -m velov.contract                          # contrat Pandera sur la table gold
python -m velov.train --data data/velov.duckdb --test-days 1
python -m velov.flow                              # les trois étapes orchestrées par Prefect
```

dbt est le seul écrivain de `data/velov.duckdb` : le reste ouvre la base en lecture seule.
Collecte continue sur la VM : voir l'en-tête de `src/velov/ingest.py` (crontab, toutes les 5 minutes).

## Structure

```
src/velov/
  data.py          simulateur de données (remplacé par l'open data en S3, même schéma)
  features.py      features partagées entraînement / API (anti training-serving skew)
  ingest.py        collecte du flux GBFS vers data/bronze, idempotente (S3)
  contract.py      contrat Pandera de la table d'entraînement (S3)
  flow.py          flow Prefect : ingestion, dbt, contrat (S3)
  train.py         entraînement, baseline, artefact + metadata.json, option MLflow
  api/main.py      FastAPI : /health, /ready, /v1/model, /v1/predict, /v1/predict/batch
  api/schemas.py   contrat d'entrée / sortie (Pydantic)
  api/storage.py   journalisation des prédictions (S2)
tests/             pytest (features, API)
docs/              templates : model card, runbook, ADR
velov_dbt/         projet dbt : silver (stg_*), gold (station_hourly), tests, contrat (S3)
data/fixtures/     bronze de démonstration, régénérable avec scripts/make_fixtures.py (S3)
exercices/         démo pickle (S1), audit, debug et conformité Docker (S2), audit SQL (S3)
```

## Usage de l'IA générative

Chaque activité indique son mode : **sans IA**, **IA déclarée** ou **IA imposée**.
En mode IA déclarée, ajoutez dans la description de vos commits ou de votre rendu :
outil utilisé, ce que vous lui avez demandé, ce que vous avez vérifié ou corrigé.
