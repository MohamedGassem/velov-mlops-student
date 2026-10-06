"""Contrat d'entrée / sortie de l'API (validé par Pydantic, publié dans OpenAPI).

TP1, partie 2 : complétez les schémas. Mode : SANS IA pour cette partie.
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class PredictionRequest(BaseModel):
    """Une observation de station à l'instant t.

    TODO 1 [Must] : déclarer les 6 champs attendus par le modèle (voir velov.features.RAW_COLUMNS)
             avec leur type Python. Pour timestamp, utilisez AwareDatetime et non datetime :
             datetime accepte "2026-10-06T08:00:00" sans fuseau, un instant ambigu.
    TODO 2 [Must] : ajouter des bornes avec Field(...) : station_id >= 1, 0 < capacity <= 100,
             bikes_available >= 0, température entre -30 et 50 °C.
    TODO 3 [Must] : refuser un champ inconnu (indice : model_config / extra).
    TODO 4 [Must] : refuser bikes_available > capacity (indice : @model_validator(mode="after")).
    TODO 4 bis [Should] : normaliser timestamp en UTC
             (indice : @field_validator("timestamp") et value.astimezone(UTC)).
    """

    model_config = ConfigDict(extra="forbid")

    station_id: int = Field(..., description="Identifiant de la station", ge=1)
    timestamp: AwareDatetime = Field(..., description="Observation à l'instant T (fuseau horaire compris)")
    capacity: int = Field(..., description="Nombre de places totales", gt=0, le=100)
    bikes_available: int = Field(..., description="Nombre de vélos disponibles", ge=0)
    temperature: float = Field(..., description="Température en °C", ge=-30, le=50)
    is_raining: bool

    @model_validator(mode="after")
    def check_capacity_available (cls, values: dict) -> dict: # valeurs en entrées générées avec de l'IA car j'avais un doute sur la syntaxe pour le dict
        if values["bikes_available"] > values["capacity"]:
            raise ValueError("bikes_available ne doit pas dépasser capacity")
        return values   


class PredictionResponse(BaseModel):
    station_id: int
    target_timestamp: AwareDatetime = Field(..., description="Instant prédit (t + 1 h)")
    predicted_bikes: float = Field(..., ge=0)
    model_version: str 


# STRETCH : BatchPredictionRequest (1 à 1000 PredictionRequest) et BatchPredictionResponse
