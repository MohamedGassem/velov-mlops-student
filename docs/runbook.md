# Runbook : API velov-availability

## 1. Vue d'ensemble
- **Ce que fait le service** : API FastAPI qui prédit le nombre de vélos Vélo'v disponibles à H+1 pour une station donnée. Elle charge un modèle scikit-learn au démarrage et expose un endpoint de prédiction.
- **Dépendances** : Python 3.11+, artefact modèle dans `models/` (`model.joblib` + `metadata.json`)

## 2. Démarrer / arrêter
```bash
# démarrer (dev, avec rechargement automatique)
uvicorn velov.api.main:app --reload

# démarrer (prod)
uvicorn velov.api.main:app --host 0.0.0.0 --port 8000

# arrêter
# Ctrl+C ou : kill $(lsof -t -i:8000)
```

## 3. Vérifier que tout va bien
| Vérification | Commande | Résultat attendu |
|---|---|---|
| Le process répond | `curl -s http://localhost:8000/health` | `{"status":"ok"}` |
| Le modèle est chargé | `curl -s http://localhost:8000/ready` | HTTP 200 + `{"status":"ready","model_version":"..."}` |
| Une prédiction fonctionne | `curl -s -X POST http://localhost:8000/v1/predict -H "Content-Type: application/json" -d '{"station_id":3,"timestamp":"2026-10-06T08:00:00+02:00","capacity":20,"bikes_available":12,"temperature":14.5,"is_raining":false}'` | HTTP 200 + JSON avec `predicted_bikes` et `target_timestamp` |

## 4. Incidents connus
| Symptôme | Cause probable | Diagnostic | Action |
|---|---|---|---|
| `/ready` renvoie 503 | Modèle non chargé | Vérifier `MODEL_DIR` pointe vers un dossier contenant `model.joblib` + `metadata.json`. Chercher `"Échec du chargement"` dans les logs. | Corriger `MODEL_DIR`, regénérer l'artefact si fichiers manquants ou SHA256 invalide, vérifier la version de scikit-learn. |
| Le conteneur redémarre en boucle | Échec du chargement du modèle | `docker compose logs api` — chercher l'exception au démarrage. | S'assurer que les artefacts sont présents et non corrompus. Reconstruire avec `python -m velov.train` si nécessaire. |
| Latence élevée | Surcharge système | Vérifier CPU/mémoire. La prédiction seule doit prendre < 100 ms. | Identifier si le goulot est `add_features` ou `predict`. Vérifier qu'aucun autre process ne sature les ressources. |

## 5. Déployer une nouvelle version du modèle
1. Entraîner : `python -m velov.train --data data/velov_history.csv --out models/ --version X.Y.Z`
2. Vérifier : ouvrir `models/metadata.json` — la MAE du modèle doit être inférieure à celle de la baseline (persistance).
3. Redémarrer l'API pour charger le nouveau modèle.
4. Retour arrière (rollback) : restaurer les fichiers `model.joblib` et `metadata.json` précédents, redémarrer l'API.

## 6. Contacts et escalade
- Ouassim Slimani
