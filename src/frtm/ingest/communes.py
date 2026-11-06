"""Communes of France with legal population and centroid, from geo.api.gouv.fr."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import polars as pl

URL = "https://geo.api.gouv.fr/communes?fields=code,nom,codeDepartement,population,centre,surface&format=json"
OUT = Path("data/reference/communes.parquet")
MANIFEST = Path("data/reference/manifest_communes.json")


def main() -> None:
    r = httpx.get(URL, timeout=120)
    r.raise_for_status()
    rows = [{"code": c["code"], "nom": c["nom"], "dept": c["codeDepartement"], "pop": c.get("population"),
             "lon": c["centre"]["coordinates"][0], "lat": c["centre"]["coordinates"][1],
             "surface_km2": (c.get("surface") or 0) / 100}   # API gives hectares
            for c in r.json() if c.get("centre") and c.get("population") is not None]
    df = pl.DataFrame(rows).with_columns(pl.col("pop").cast(pl.Int64))
    df.write_parquet(OUT)
    MANIFEST.write_text(json.dumps({"url": URL, "rows": df.height, "population_total": int(df["pop"].sum()),
                                    "downloaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=2))
    print(df.height, "communes,", df["pop"].sum(), "people")


if __name__ == "__main__":
    main()