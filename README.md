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

```bash
git checkout s1-end          # récupérer l'état de fin de S1
git checkout -b mon-binome   # travailler sur sa propre branche
```

## Démarrage rapide

Prérequis : Python 3.11+ (3.12 recommandé), git. Docker sera nécessaire en S2.

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

### Rendu TP1 : exigences couvertes

Toutes les preuves se lancent après l'installation (voir *Démarrage rapide*) : `pytest` (18 tests au vert),
`python -m velov.train` pour la métrique, `uvicorn velov.api.main:app` pour les appels `curl`.

| Exigence | Couverte | Preuve |
|---|---|---|
| EX-01 | Oui | `tests/test_api.py` : `test_predict_rejects_bikes_above_capacity`, `test_champ_inconnu_rejete`, `test_timestamp_sans_fuseau_rejete`, `test_batch_rejette_liste_vide_et_item_invalide` (422). Bornes et champs dans `api/schemas.py`. |
| EX-02 | Partiellement | `/ready` répond 503 si le modèle est absent (`test_health_ok_sans_modele`) et le modèle n'est chargé qu'après vérification du SHA-256 (`load_model`). Le `HEALTHCHECK` de l'image relève de S2. |
| EX-03 | Oui | Champ `model_version` dans chaque réponse (`test_predict_borne_et_version`, `test_ready_donne_la_version`). |
| EX-04 | Python seulement | Procédure du *Démarrage rapide* suivie depuis un venv vierge. Pas encore de revue par un autre binôme ni de `docker compose` (S2). |
| EX-05 | Oui | `models/metadata.json` : MAE modèle 1,339 contre 1,879 pour la persistance, sur le test temporel de 14 jours. Seuil automatisé en CI prévu en S4. |
| EX-07 | Partiellement | Un échec de chargement du modèle est journalisé avec sa cause (`logger.exception` dans `lifespan`), visible dans le terminal d'uvicorn. |

Non couvertes à ce stade : EX-06 (secrets), EX-08 (traçabilité en base) et EX-09 (revue croisée), prévues à partir de S2.

Stretch réalisé : `/v1/predict/batch` (1 à 1000 observations), `/v1/model`, journal MLflow (`python -m velov.train --mlflow`).

### Rendu TP1 : usage de l'IA générative

| Partie | Mode prévu | Mode réel |
|---|---|---|
| `api/main.py` : `/v1/predict`, `/health`, `/ready` | IA déclarée | IA déclarée |
| `tests/test_api.py` (tests d'erreur) | IA déclarée | IA déclarée |
| Stretch : batch, `/v1/model` | IA déclarée | IA déclarée |

- **Outil utilisé** : Claude Code (modèle Claude Sonnet 5.5).
- **Ce que j'ai demandé** : compléter les TODO de `api/main.py`, ajouter des tests d'erreur, puis le Stretch
  (batch, `/v1/model`) ; corriger un test trop faible ; ajouter `*.pkl` et `*.egg-info/` au `.gitignore` et un message d'erreur dans `exercices/s1_pickle/demo_pickle.py`.
- **Ce qui a été vérifié** : `pytest` (18 tests) et `ruff` au vert ; appels `curl` réels sur `/health`, `/ready`, `/v1/predict`
  (200 avec `target_timestamp` en UTC, 422 sans fuseau) ; MAE du modèle inférieure à celle de la baseline.
- **Ce qui a été corrigé** : un test qui n'avait pas de valeur (`status_code in (422, 503)`) a été supprimé, le 503 étant déjà couvert par un test dédié.


## Structure

```
src/velov/
  data.py          simulateur de données (remplacé par l'open data en S3, même schéma)
  features.py      features partagées entraînement / API (anti training-serving skew)
  train.py         entraînement, baseline, artefact + metadata.json, option MLflow
  api/main.py      FastAPI : /health, /ready, /v1/model, /v1/predict, /v1/predict/batch
  api/schemas.py   contrat d'entrée / sortie (Pydantic)
tests/             pytest (features, API)
docs/              templates : model card, runbook, ADR
exercices/         démo pickle (S1)
```

## Usage de l'IA générative

Chaque activité indique son mode : **sans IA**, **IA déclarée** ou **IA imposée**.
En mode IA déclarée, ajoutez dans la description de vos commits ou de votre rendu :
outil utilisé, ce que vous lui avez demandé, ce que vous avez vérifié ou corrigé.
