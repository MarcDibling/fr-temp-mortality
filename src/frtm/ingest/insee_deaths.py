"""Download the data.gouv aggregated INSEE deaths file (1970 -> today) into data/bronze.

A manifest with URL, date, checksum, row count and schema is written to data/reference
so the download is documented in git even though the data itself is not.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import polars as pl

DATASET_API = (
    "https://www.data.gouv.fr/api/1/datasets/agregation-des-fichiers-des-personnes-decedees/"
)
BRONZE = Path("data/bronze/insee_deces")
REFERENCE = Path("data/reference")
MANIFEST = REFERENCE / "manifest_insee_deces.json"


def find_resources(meta: dict) -> tuple[dict, dict | None]:
    """Pick the parquet data file and the field-description file out of the API answer."""
    resources = meta["resources"]
    parquet = next(r for r in resources if r["format"] == "parquet" and r["type"] == "main")
    doc = next((r for r in resources if r["type"] == "documentation"), None)
    return parquet, doc


def download(url: str, dest: Path, expected_size: int | None = None) -> None:
    """Stream a file to disk in chunks; skip if it is already there with the right size."""
    if dest.exists() and (expected_size is None or dest.stat().st_size == expected_size):
        print(f"already have {dest}, skipping download")
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=None) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=8 * 1024 * 1024):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done / 1e6:,.0f} / {total / 1e6:,.0f} MB", end="", flush=True)
    print()
    tmp.replace(dest)  # only rename to the final name once fully downloaded


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    BRONZE.mkdir(parents=True, exist_ok=True)
    REFERENCE.mkdir(parents=True, exist_ok=True)

    print("asking data.gouv for the dataset metadata")
    meta = httpx.get(DATASET_API, timeout=60, follow_redirects=True).json()
    parquet, doc = find_resources(meta)

    stamp = parquet["last_modified"][:10]  # e.g. 2026-09-25
    dest = BRONZE / f"deces_{stamp}.parquet"
    print(f"downloading {parquet['title']} ({parquet['filesize'] / 1e6:,.0f} MB)")
    download(parquet["url"], dest, parquet.get("filesize"))

    if doc is not None:
        try:
            download(doc["url"], REFERENCE / "insee_deces_description_champs.csv")
        except httpx.HTTPError as e:
            print(f"could not fetch the field description ({e}); not blocking")

    print("computing checksum and row count")
    lf = pl.scan_parquet(dest)
    manifest = {
        "source": DATASET_API,
        "resource_id": parquet["id"],
        "url": parquet["url"],
        "last_modified": parquet["last_modified"],
        "filesize_bytes": dest.stat().st_size,
        "sha256": sha256(dest),
        "rows": lf.select(pl.len()).collect().item(),
        "schema": {name: str(dtype) for name, dtype in lf.collect_schema().items()},
        "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "local_path": str(dest),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()