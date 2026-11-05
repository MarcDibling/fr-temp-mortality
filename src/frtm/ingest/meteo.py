"""Download Météo-France daily station observations (data.gouv dataset) into data/bronze/meteo.

For every département, the periods 1950-2024 and 2025-2026 of both parameter
groups (RR-T-Vent: rain, temperature, wind; autres-parametres: humidity etc.).
Pre-1949 files are skipped and model starts in 2000.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from frtm.ingest.insee_deaths import download  # reuse the chunked downloader

DATASET_ID = "6569b51ae64326786e4e8e1a"  # Données climatologiques de base - quotidiennes
API = f"https://www.data.gouv.fr/api/2/datasets/{DATASET_ID}/resources/"
BRONZE = Path("data/bronze/meteo")
REFERENCE = Path("data/reference")
MANIFEST = REFERENCE / "manifest_meteo.json"
PERIODS = ("1950-2024", "2025-2026")


def list_resources() -> list[dict]:
    """Walk every page of the dataset's resource list (50 per page)."""
    out, page = [], 1
    while True:
        r = httpx.get(API, params={"page": page, "page_size": 50}, timeout=60, follow_redirects=True)
        r.raise_for_status()
        body = r.json()
        out.extend(body["data"])
        if body.get("next_page") is None:
            return out
        page += 1


def wanted(res: dict) -> bool:
    title = res["title"]
    return res["type"] == "main" and title.startswith("QUOT_departement_") and any(p in title for p in PERIODS)


def main() -> None:
    BRONZE.mkdir(parents=True, exist_ok=True)
    REFERENCE.mkdir(parents=True, exist_ok=True)

    print("listing resources on data.gouv")
    resources = list_resources()
    data_files = [r for r in resources if wanted(r)]
    docs = [r for r in resources if r["type"] == "documentation" and r["format"] == "csv" and "descriptif_champs" in r["title"]]
    print(f"{len(resources)} resources, {len(data_files)} to download, {len(docs)} field descriptions")

    entries = []
    for i, res in enumerate(sorted(data_files, key=lambda r: r["title"]), 1):
        dest = BRONZE / res["url"].rsplit("/", 1)[-1]  # e.g. Q_01_previous-1950-2024_RR-T-Vent.csv.gz
        # The 2025-2026 files change daily, so they are always re-downloaded; the others only if missing.
        expected = None if "2025-2026" in res["title"] else res.get("filesize")
        if "2025-2026" in res["title"] and dest.exists():
            dest.unlink()
        print(f"[{i}/{len(data_files)}] {dest.name}")
        download(res["url"], dest, expected)
        entries.append({"title": res["title"], "url": res["url"], "last_modified": res["last_modified"],
                        "bytes": dest.stat().st_size, "local_path": str(dest)})

    for res in docs:
        download(res["url"], REFERENCE / f"meteo_{res['title']}")

    manifest = {"dataset": DATASET_ID, "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "n_files": len(entries), "files": entries}
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"done: {len(entries)} files, {sum(e['bytes'] for e in entries) / 1e9:.2f} GB")


if __name__ == "__main__":
    main()