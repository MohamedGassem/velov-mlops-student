# S2 + S3 : Docker, Compose et données Vélo'v temps réel

Guide d'onboarding : ce qui a été ajouté au projet, pourquoi, et comment s'en servir.

---

## En 30 secondes

- Une image Docker **multi-stage, non-root, légère**, qui démarre l'API avec le modèle embarqué.
- Un `docker-compose.yaml` : `docker compose up --build` → API dispo sur `http://localhost:8000`.
- Un nouvel endpoint `GET /v1/predict/live/{station_id}` qui va chercher les **vraies données Vélo'v** (open data Métropole de Lyon) et renvoie une prédiction.

---

## Fichiers créés / modifiés

| Fichier | Rôle |
|---|---|
| `Dockerfile` | Image de production, deux étapes (builder + runtime), non-root |
| `.dockerignore` | Évite d'envoyer `.git`, `.env`, `data/`, `mlruns/`, `tests/`… au build |
| `docker-compose.yaml` | Lance le service `api` (build, port, healthcheck) |
| `src/velov/gbfs.py` | Client minimal pour les flux GBFS Vélo'v |
| `src/velov/api/main.py` | + endpoint `/v1/predict/live/{station_id}` |
| `requirements.txt` | + `httpx==0.28.1` (appels HTTP sortants) |

---

## 1. Le Dockerfile (S2)

Il suit la **checklist des 8 règles** vues en cours :

| # | Règle | Dans notre image |
|---|---|---|
| 1 | Base slim avec version explicite | `python:3.12-slim` (via `ARG PYTHON_IMAGE`) |
| 2 | Deps épinglées, installées **avant** le code | `COPY requirements.txt` → `pip install` → *puis* `COPY src/` |
| 3 | Multi-stage | `builder` (jeté) → `runtime` (ne garde que le venv et `models/`) |
| 4 | `.dockerignore` | présent, exclut tout sauf ce qui est nécessaire au serving |
| 5 | Utilisateur non-root | `useradd --uid 10001 appuser` + `USER appuser` |
| 6 | Aucun secret dans l'image | rien de sensible dans `ENV` ni `COPY` |
| 7 | `CMD` en JSON | `CMD ["uvicorn", "velov.api.main:app", ...]` → `SIGTERM` propre |
| 8 | `HEALTHCHECK` sur `/ready` | sain = capable de prédire (pas juste de répondre) |

### Pourquoi deux étapes ?

- **builder** : installe `pip`, compile les wheels, télécharge les caches. Pèse plusieurs centaines de Mo. Jeté à la fin.
- **runtime** : copie uniquement `/opt/venv` + `models/`. Image finale beaucoup plus légère, zéro outil de build.

---

## 2. Le docker-compose (S2)

Un seul service pour l'instant, l'API.

```bash
docker compose up --build -d     # build + démarre en arrière-plan
docker compose ps                # état et santé
docker compose logs -f api       # logs en continu
docker compose down              # tout arrêter
```

### Variables d'env (optionnelles)

| Variable | Défaut | Rôle |
|---|---|---|
| `VELOV_VERSION` | `0.1.0` | tag de l'image produite |
| `LOG_LEVEL` | `INFO` | niveau de log de l'API |

> **Note** : le compose du cours ajoute un service `postgres` pour journaliser les prédictions. On l'ajoutera **quand** le code de journalisation existera côté API — pour l'instant ce serait un service inutile.

---

## 3. Intégration des données réelles Vélo'v (S3)

### Source

**GBFS** (General Bikeshare Feed Specification) publié par la Métropole de Lyon + JCDecaux, sous Licence Ouverte 2.0, rafraîchi chaque minute.

Base : `https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/`

Le `gbfs.json` liste 5 flux. On en utilise **2** :

| Flux utilisé | Champs lus |
|---|---|
| `station_information.json` | `capacity` (change rarement) |
| `station_status.json` | `num_bikes_available`, `last_reported` (toutes les minutes) |

Les 3 autres (`gbfs_versions`, `system_information`, `vehicle_types`) ne portent rien d'utile pour prédire la disponibilité.

### Ce que `fetch_station_snapshot(station_id)` renvoie

```python
{
    "station_id": 1024,
    "capacity": 17,
    "bikes_available": 1,
    "timestamp": datetime(2026, 10, 9, 5, 19, 31, tzinfo=UTC),
}
```

Ces 4 champs viennent de GBFS. Les 2 restants (`temperature`, `is_raining`) ne sont pas dans GBFS : on les passe en query string sur l'endpoint.

### Nouvel endpoint

```
GET /v1/predict/live/{station_id}?temperature=12&is_raining=false
```

| Code | Quand |
|---|---|
| `200` | prédiction OK |
| `404` | station inconnue dans GBFS |
| `502` | flux GBFS injoignable |
| `503` | modèle non chargé |

---

## Démarrage rapide

```bash
# 1. Lancer la stack
docker compose up --build -d

# 2. Vérifier qu'elle est prête
curl http://localhost:8000/ready
# → {"status":"ok","model_version":"0.1.0"}

# 3. Prédire pour une station réelle (ex : 1024 = ROUVILLE)
curl "http://localhost:8000/v1/predict/live/1024?temperature=12&is_raining=false"
# → {"station_id":1024,"target_timestamp":"...","predicted_bikes":3.99,"model_version":"0.1.0"}

# 4. Ou prédire à partir de données qu'on fournit soi-même
curl -X POST http://localhost:8000/v1/predict \
  -H "Content-Type: application/json" \
  -d '{"station_id":3,"timestamp":"2026-10-06T08:00:00+02:00","capacity":20,
       "bikes_available":12,"temperature":14.5,"is_raining":false}'

# 5. Arrêter
docker compose down
```

---

## Vérifications déjà faites

- `pytest` : 8 tests verts (API + features).
- `docker build` : OK.
- Conteneur lancé : `/health`, `/ready`, `/v1/predict/live/1024` renvoient 200.
- `docker exec velov-api id` → `uid=10001(appuser)` (non-root confirmé).
- `docker compose config` : configuration valide.

---

## Pour aller plus loin

- **Postgres + journalisation des prédictions** : ajouter un service `db` au compose quand on écrira le code côté API (TP2 Must du cours).
- **Météo réelle** : remplacer les query params `temperature` / `is_raining` par un appel à Open-Meteo (gratuit, sans clé).
- **Pipeline bronze/silver/gold (dbt + DuckDB)** : vraie approche S3 pour entraîner sur un historique collecté, pas juste prédire sur un snapshot.
