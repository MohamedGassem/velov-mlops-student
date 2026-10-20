"""Ingestion bronze (S3) : on stocke la réponse brute, telle quelle, sans la transformer.

Idempotence : le nom du fichier dépend du contenu (`last_updated` publié par le flux),
pas de l'heure d'exécution. Relancer la tâche sur le même instantané ne crée pas de doublon.
Le fichier est écrit sous un nom temporaire puis renommé : un run interrompu ne laisse
jamais un JSON à moitié écrit.

Usage (depuis la racine du repo) :
    python -m velov.ingest                          # un instantané du vrai flux vers data/bronze
    python -m velov.ingest --replay data/fixtures   # rejoue le bronze de démonstration (48 h)

Collecte continue sur la VM, toutes les 5 minutes (crontab -e) :
    */5 * * * *  cd ~/velov-mlops && .venv/bin/python -m velov.ingest >> data/ingest.log 2>&1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

# Flux GBFS 2.3 de la Métropole de Lyon (Licence Ouverte 2.0). L'index liste les URL des sous-flux.
GBFS_INDEX = "https://download.data.grandlyon.com/files/rdata/jcd_jcdecaux.jcdvelov/gbfs.json"
# Météo horaire Open-Meteo sur Lyon, en GMT : la veille et le jour courant.
WEATHER = (
    "https://api.open-meteo.com/v1/forecast?latitude=45.76&longitude=4.84"
    "&hourly=temperature_2m,precipitation&past_days=1&forecast_days=1&timezone=GMT"
)
BRONZE = Path("data/bronze")


def fetch_json(url: str, timeout: float = 10.0) -> dict:
    if not url.startswith(("https://", "file://")):
        raise ValueError(f"URL refusée : {url}")
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 (schéma vérifié ci-dessus)
        return json.load(resp)


def ingest(url: str, bronze: Path, feed: str) -> tuple[Path, bool]:
    """Range une réponse dans bronze/<feed>/dt=<date>/<clé>.json. Retourne (chemin, écrit ?)."""
    payload = fetch_json(url)
    if feed.startswith("station_") and "last_updated" not in payload:
        raise ValueError(f"{feed} : réponse inattendue, pas de 'last_updated'")
    # Clé = horodatage publié par la source, sinon empreinte du contenu (cas de la météo).
    key = str(
        payload.get("last_updated") or hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
    )
    ts = datetime.fromtimestamp(payload["last_updated"], tz=UTC) if "last_updated" in payload else datetime.now(UTC)
    target = bronze / feed / f"dt={ts:%Y-%m-%d}" / f"{key}.json"
    if target.exists():
        return target, False  # déjà ingéré : on ne fait rien
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload))
    tmp.replace(target)  # écriture atomique
    return target, True


def feed_urls(index_url: str = GBFS_INDEX) -> dict[str, str]:
    """Lit gbfs.json et renvoie {nom du flux: URL}. Les URL ne sont pas écrites en dur."""
    data = fetch_json(index_url)["data"]
    feeds = next(iter(data.values()))["feeds"]  # première langue publiée
    return {f["name"]: f["url"] for f in feeds}


def ingest_live(bronze: Path = BRONZE) -> dict[str, bool]:
    urls = feed_urls()
    sources = {
        "station_status": urls["station_status"],
        "station_information": urls["station_information"],
        "weather": WEATHER,
    }
    return {feed: ingest(url, bronze, feed)[1] for feed, url in sources.items()}


def replay(fixtures: Path, bronze: Path = BRONZE) -> tuple[int, int]:
    """Rejoue le bronze de démonstration : chaque fichier joue le rôle d'un appel au flux."""
    written = skipped = 0
    for snap in sorted((fixtures / "snapshots").glob("*.json")):
        _, new = ingest(snap.resolve().as_uri(), bronze, "station_status")
        written += new
        skipped += not new
    for feed in ("station_information", "weather"):
        ingest((fixtures / f"{feed}.json").resolve().as_uri(), bronze, feed)
    return written, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingestion bronze du flux Vélo'v.")
    parser.add_argument("--replay", type=Path, help="dossier du bronze de démonstration (data/fixtures)")
    parser.add_argument("--bronze", type=Path, default=BRONZE)
    args = parser.parse_args()

    if args.replay:
        written, skipped = replay(args.replay, args.bronze)
        print(f"bronze : {written} fichiers écrits, {skipped} déjà présents")
        return 0
    result = ingest_live(args.bronze)
    print(" ".join(f"{feed}={'écrit' if new else 'déjà présent'}" for feed, new in result.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
