# ADR-0002 : D'où l'API tire son modèle

- Statut : accepté
- Date : 2026-10-26
- Auteurs : équipe pédagogique (exemple d'ADR rempli)

## Contexte
Depuis S4, les modèles sont enregistrés dans le registre MLflow et l'alias `champion` désigne
celui qui doit servir. Il faut décider comment ce modèle arrive dans l'API. Le serveur MLflow tourne
sur la VM du binôme ; l'image de l'API ne contient aujourd'hui aucune dépendance MLflow.

## Options envisagées
| Option | Avantages | Inconvénients |
|---|---|---|
| A. L'API charge `models:/velov-availability@champion` au démarrage | Changer de modèle = déplacer l'alias, sans rebuild | MLflow dans l'image de serving ; l'API ne démarre pas si le registre est indisponible ; déplacer l'alias change la production sans déploiement ni trace dans git |
| B. L'alias est résolu avant le build ; le modèle est copié dans l'image | Image immuable (code + dépendances + modèle) ; retour arrière = image précédente ; l'API ne dépend pas du registre | Changer de modèle demande un build et un redéploiement |
| C. L'API recharge le modèle à chaud quand l'alias bouge | Pas d'interruption | Deux versions possibles dans le même process, état difficile à observer : hors périmètre du cours |

## Décision
Option B. `velov.export` télécharge le paquet de la version `champion`, vérifie son empreinte et ajoute
la référence au registre dans `metadata.json`. L'image est taguée `m<version du registre>-<commit court>`.

## Conséquences
- Le registre décide quel modèle part, l'image le livre : deux étapes distinctes, chacune tracée.
- `GET /v1/model` expose `registry.version` et `registry.run_id` (EX-13).
- Retour arrière : redéployer l'image précédente, ou exporter `@previous-champion` puis reconstruire.
- À réévaluer si le rythme de réentraînement devient quotidien ou plus fréquent (S7, cloud).
