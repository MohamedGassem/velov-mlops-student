# Model card : velov-availability

> Inspirée de Mitchell et al., "Model Cards for Model Reporting" (2019).

## 1. Identité
- Nom / version : velov-availability v0.1.0
- Date d'entraînement : 2026-10-06
- Responsables : Ouassim Slimani
- Emplacement de l'artefact : `models/model.joblib` + `models/metadata.json`

## 2. Usage prévu
- Ce que le modèle prédit : le nombre de vélos disponibles à H+1 par station Vélo'v.
- Utilisateurs et décisions alimentées : équipe d'exploitation de la Métropole, applications grand public affichant la disponibilité prévisionnelle.
- Usages hors périmètre : planification long terme, dimensionnement de capacité, prédictions temps réel (infra-minute).

## 3. Données
- Source, période couverte, volume : données simulées (`velov.data`, seed=42), 90 jours, 20 stations, granularité horaire (43 200 lignes).
- Découpage entraînement / test : temporel — les 14 derniers jours servent de test. Jamais aléatoire, pour éviter toute fuite temporelle.
- Limites connues : données synthétiques uniquement (pas d'événements réels : grèves, travaux, intempéries exceptionnelles), couverture limitée à 20 stations simulées.

## 4. Performance
| Métrique | Modèle | Baseline (persistance) | Seuil d'acceptation |
|---|---|---|---|
| MAE (vélos) | 1.339 | 1.879 | MAE modèle < MAE baseline |

- Performance par segment : non évaluée sur la v0 (à approfondir en S4 avec segmentation heure de pointe / week-end / station).

## 5. Contrat d'entrée / sortie
- Champs d'entrée : `station_id` (int, ≥ 1), `timestamp` (datetime avec fuseau, normalisé UTC), `capacity` (int, 1–100), `bikes_available` (int, ≥ 0, ≤ capacity), `temperature` (float, −30 à 50 °C), `is_raining` (bool).
- Sortie : `station_id`, `target_timestamp` (t + 1 h), `predicted_bikes` (float, borné entre 0 et capacity), `model_version`.
- Comportement sur entrée inconnue : une station jamais vue à l'entraînement ne fait pas planter l'API (`OneHotEncoder(handle_unknown="ignore")`), mais la prédiction sera moins fiable.

## 6. Risques et limites
- Dérive attendue : saisonnalité (été/hiver), ajout/suppression de stations, travaux de voirie, événements exceptionnels.
- Données personnelles : non — seules des données agrégées par station sont utilisées, aucune donnée utilisateur.

## 7. Exploitation
- Latence cible : < 100 ms par prédiction.
- Fréquence de réentraînement prévue : à définir (pipeline de données réelles prévu en S3).
- Lien vers le runbook : [docs/runbook.md](runbook.md)
