"""Client minimal pour les flux GBFS Vélo'v (open data de la Métropole de Lyon).

"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

GBFS_BASE = "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov"
STATION_INFORMATION_URL = f"{GBFS_BASE}/station_information.json"
STATION_STATUS_URL = f"{GBFS_BASE}/station_status.json"
HTTP_TIMEOUT_S = 10.0


def _fetch(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=HTTP_TIMEOUT_S) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def fetch_station_snapshot(station_id: int) -> dict[str, Any]:
    """Retourne l'état courant d'une station au format d'entrée du modèle.

    Les champs renvoyés correspondent aux 4 colonnes brutes connues côté GBFS :
    station_id, capacity, bikes_available, timestamp. temperature et is_raining
    restent à fournir par l'appelant.

    Raises:
        LookupError: si la station n'existe pas dans les flux.
    """
    info_payload = _fetch(STATION_INFORMATION_URL)
    status_payload = _fetch(STATION_STATUS_URL)
    target = str(station_id)
    info = next(
        (s for s in info_payload["data"]["stations"] if str(s["station_id"]) == target),
        None,
    )
    status = next(
        (s for s in status_payload["data"]["stations"] if str(s["station_id"]) == target),
        None,
    )
    if info is None or status is None:
        raise LookupError(f"Station {station_id} introuvable dans les flux GBFS")
    return {
        "station_id": station_id,
        "capacity": int(info["capacity"]),
        "bikes_available": int(status["num_bikes_available"]),
        "timestamp": datetime.fromtimestamp(int(status["last_reported"]), tz=UTC),
    }
