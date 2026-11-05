"""Download INSEE population estimates by département, sex and 5-year age (1 January, 1975-2026)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from frtm.ingest.insee_deaths import download, sha256

URL = "https://www.insee.fr/fr/statistiques/fichier/8721456/estim-pop-dep-sexe-aq-1975-2026.xlsx"
BRONZE = Path("data/bronze/insee_population")
MANIFEST = Path("data/reference/manifest_insee_population.json")


def main() -> None:
    BRONZE.mkdir(parents=True, exist_ok=True)
    dest = BRONZE / URL.rsplit("/", 1)[-1]
    download(URL, dest)
    manifest = {
        "url": URL,
        "source_page": "https://www.insee.fr/fr/statistiques/8721456",
        "sha256": sha256(dest),
        "bytes": dest.stat().st_size,
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()