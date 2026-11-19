# Runbook : API velov-availability

> Template à compléter au fil des sessions. Public cible : une personne d'astreinte
> qui ne connaît pas le projet et doit rétablir le service à 3 h du matin.

## 1. Vue d'ensemble
- Ce que fait le service, en deux phrases :
- Schéma d'architecture (lien) :
- Dépendances (base de données, stockage du modèle...) :

## 2. Démarrer / arrêter
```bash
# démarrer
# arrêter
# redémarrer un seul service
```

## 3. Vérifier que tout va bien
| Vérification | Commande | Résultat attendu |
|---|---|---|
| Le process répond | `curl -s http://<hôte>:8000/health` | `{"status":"ok"}` |
| Le modèle est chargé | `curl -s http://<hôte>:8000/ready` | HTTP 200 + version |
| | | |

## 4. Incidents connus
| Symptôme | Cause probable | Diagnostic | Action |
|---|---|---|---|
| `/ready` renvoie 503 | | | |
| Le conteneur redémarre en boucle | | | |
| Latence élevée | | | |

## 5. Déployer une nouvelle version du modèle (EX-18)
Stratégie : **shadow, puis bascule**. Une seule VM, un seul conteneur API : pas de répartiteur
pour un canary. Le challenger est d'abord évalué sur le trafic réel, sans servir de réponse.

1. Shadow (24 h minimum, un jour de semaine compris) : les prédictions du challenger sont journalisées
   avec sa `model_version`, à côté de celles du champion ; MAE des deux à H+1, globale et en heures de pointe.
2. Bascule si les trois critères tiennent : MAE du challenger meilleure d'au moins 2 % (règle de promotion,
   S4), p95 de l'API sous 200 ms au palier de 50 usagers, aucune erreur 5xx pendant le test de charge.
   `python -m velov.promote --apply` puis `./scripts/release.sh` sur la VM.
3. Retour arrière, sans discuter, dans l'heure qui suit la bascule si : p95 au-dessus de 200 ms pendant
   5 minutes, taux de 5xx au-dessus de 1 %, ou `/ready` en 503.
   Commande : `./scripts/release.sh previous-champion` (ou relancer l'image précédente, déjà sur la VM).

## 6. Performance et capacité (EX-16)
- **SLO** : 95 % des requêtes `/v1/predict` en moins de 200 ms, moins de 1 % d'erreurs, mesuré par
  Locust depuis un poste du réseau de l'école (`loadtest/paliers.sh`, puis `loadtest/summary.py`).
- **Capacité mesurée** (machine de préparation, 1 worker, 1 cœur) : environ 41 req/s sous le SLO en
  joblib, environ 80 req/s en ONNX. Au-delà, la latence monte avant le débit : la file d'attente grossit.
- **Quand on approche du plafond** : passer à `--workers 2` si la VM a 2 cœurs libres (un worker par cœur,
  le modèle est chargé dans chaque worker), puis remesurer. Ajouter des workers sur un seul cœur n'apporte rien.
- **Symptôme « latence élevée »** : comparer l'en-tête `X-Process-Time-Ms` (temps dans l'API) à la latence
  vue par Locust. Proches : le calcul sature le CPU. Très différents : attente avant traitement ou réseau.

## 7. Contacts et escalade
-
