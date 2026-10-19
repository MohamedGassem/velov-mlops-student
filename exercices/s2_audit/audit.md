# Audit du Dockerfile.ia — grille S2

> **Mode : IA imposée.** Cet audit a été produit par un assistant (comme demandé étape 2).
> À comparer avec la critique faite seul (étape 1).

**Fichier audité** : `exercices/s2_audit/Dockerfile.ia`
**Résultat global** : à **refuser** en production. 11 problèmes trouvés, dont plusieurs bloquants.

## Rappel de la checklist S2 (les 8 règles)

1. Image de base slim, version explicite
2. Dépendances épinglées, installées avant le code
3. Plusieurs étapes (multi-stage)
4. Un `.dockerignore`
5. Un utilisateur non-root
6. Aucun secret dans l'image
7. `CMD` en JSON
8. Un `HEALTHCHECK` sur `/ready`

---

## Les 11 problèmes

### #1 — L4 : `FROM python:latest` — règle 1 ❌

**Risque** : base non versionnée. L'image peut changer du jour au lendemain (nouvelle version de Python ou de la distro) et casser le build. `python:latest` est aussi la variante **complète** (~1 Go), pas slim.

**Correction** : `ARG PYTHON_IMAGE=python:3.12-slim` puis `FROM ${PYTHON_IMAGE}`.

---

### #2 — L7-8 : secrets en dur dans `ENV` — règle 6 ❌ (bloquant sécurité)

```dockerfile
ENV API_KEY=sk-prod-7f3a9d2c8b1e4f5a6d7c8b9a0e1f2d3c
ENV POSTGRES_PASSWORD=supersecret
```

**Risque** : lisibles par quiconque fait `docker history <image>`. Supprimer la variable dans une couche suivante **ne les efface pas** : la couche d'origine reste. Si l'image est poussée sur un registre, ces secrets fuitent définitivement.

**Correction** : retirer ces lignes. Passer les secrets au démarrage via `environment:` du compose, lues d'un `.env` **non versionné** (dans `.gitignore` et `.dockerignore`).

---

### #3 — L10 : `COPY . .` avant `pip install` — règles 2 + 4 ❌

**Risque** :
- Casse le cache Docker : toute modification du code force la réinstallation de **toutes** les dépendances → builds lents.
- Sans `.dockerignore`, on embarque `.git`, `.env` locaux, `data/`, `mlruns/`, `__pycache__/`… secrets inclus.

**Correction** :
```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ src/
```
Et ajouter un `.dockerignore`.

---

### #4 — L12 : `apt-get install vim wget` + pas de cleanup — règle 3 ❌

**Risque** : outils d'édition et de debug dans une image de production (surface d'attaque, poids). Le cache apt (`/var/lib/apt/lists`) est gardé, +50 Mo pour rien.

**Correction** : ne garder que ce dont le runtime a besoin (ici : rien, scikit-learn a ses wheels). Si install nécessaire : `rm -rf /var/lib/apt/lists/*` à la fin de la ligne. Mieux : installer dans une **étape builder** qui ne finit pas dans l'image.

---

### #5 — L14 : dépendances non épinglées — règle 2 ❌ (bloquant ML)

```dockerfile
RUN pip install fastapi uvicorn scikit-learn pandas ...
```

**Risque** : chaque build peut tirer une version différente. **Un modèle scikit-learn n'est pas garanti d'une version à l'autre** → prédictions qui dérivent sans erreur visible. C'est la cause classique de `UnpicklingError` ou pire, de résultats faux.

**Correction** : utiliser `requirements.txt` avec les versions **notées dans `models/metadata.json`** (ce qu'on fait dans notre vrai Dockerfile).

---

### #6 — absent : aucun `USER` → tourne en **root** — règle 5 ❌ (bloquant sécurité)

**Risque** : une faille applicative (RCE via Pydantic, injection…) donne root sur le conteneur. Si un volume est monté, le dégât sort du conteneur.

**Correction** :
```dockerfile
RUN useradd --create-home --uid 10001 appuser
USER appuser
```

---

### #7 — L16 : `EXPOSE 80` incohérent avec `--port 8000` sur L20

**Risque** : documentation mensongère. Les outils (compose, K8s, scan) lisent `EXPOSE` pour deviner le port. Un `docker run -P` publiera 80, qui ne répond jamais.

**Correction** : `EXPOSE 8000`.

---

### #8 — L18 : `HEALTHCHECK curl -f http://localhost/` — règle 8 ❌

Deux problèmes :

**(a)** `curl` **n'est pas installé** dans `python:slim` par défaut. Dans notre image réelle, le healthcheck planterait silencieusement et le conteneur serait marqué `unhealthy`.

**(b)** Interroge `/`, pas `/ready`. Un conteneur dont le modèle n'a pas pu se charger répond quand même 404 sur `/` → marqué `healthy` alors qu'**il est incapable de prédire**. C'est exactement le piège dénoncé en S2.

**Correction** :
```dockerfile
HEALTHCHECK CMD ["python", "-c", \
  "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/ready').read()"]
```

---

### #9 — L20 : `CMD` en shell form + `--reload` — règle 7 ❌

```dockerfile
CMD uvicorn velov.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Shell form** : Docker lance `/bin/sh -c "uvicorn ..."`. PID 1 est le shell, qui **garde `SIGTERM` pour lui**. Résultat : à chaque `docker stop` ou nouveau déploiement, Docker attend 10 s puis `SIGKILL` → **requêtes en cours coupées**, utilisateurs reçoivent des erreurs.

**`--reload`** : watcher de dev qui redémarre uvicorn à chaque fichier modifié. En prod : surcoût CPU, instabilité, et pas pertinent dans un conteneur immutable.

**Correction** :
```dockerfile
CMD ["uvicorn", "velov.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### #10 — absent : pas de multi-stage — règle 3 ❌

**Risque** : `gcc`, les caches pip, les wheels téléchargés, les en-têtes dev restent dans l'image finale. +200 à 400 Mo, outils exploitables en cas de compromission.

**Correction** : deux `FROM`. Builder installe dans `/opt/venv`, runtime copie uniquement le venv.

---

### #11 — absent : pas de `.dockerignore` — règle 4 ❌

Déjà mentionné dans #3 côté cache. Point séparé car c'est **un fichier manquant** à créer.

**Correction** :
```
.git
.env
.env.*
data/
mlruns/
mlflow.db
tests/
docs/
**/__pycache__
```

---

## Synthèse par règle de la checklist

| # | Règle S2 | Statut |
|---|---|---|
| 1 | Image slim versionnée | ❌ `python:latest` |
| 2 | Deps épinglées, avant le code | ❌ pas de versions + `COPY . .` d'abord |
| 3 | Multi-stage | ❌ une seule étape |
| 4 | `.dockerignore` | ❌ absent |
| 5 | Non-root | ❌ tourne en root |
| 6 | Pas de secret dans l'image | ❌ `API_KEY` + `POSTGRES_PASSWORD` en ENV |
| 7 | `CMD` en JSON | ❌ shell form + `--reload` |
| 8 | `HEALTHCHECK` sur `/ready` | ❌ `curl /` + curl absent |

**Score** : 0 / 8. L'image démarre, répond, mais échoue sur **toute** la checklist.

---

## À comparer avec notre vrai Dockerfile

Notre `Dockerfile` à la racine du projet coche les 8 règles. C'est le "corrigé".

```bash
diff <(cat exercices/s2_audit/Dockerfile.ia) <(cat Dockerfile)
```

---

## Étape 3 (5 min) — grille à remplir à la main

| Ce que l'IA (moi) a trouvé | Ce qu'elle a raté | Ce qu'elle a inventé |
|---|---|---|
| à remplir après avoir fait l'audit seul | à remplir | à remplir |
