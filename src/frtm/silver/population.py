"""INSEE population workbook (one sheet per year) -> silver population_annual
(year x dept x sex x age_band, population on 1 January)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import polars as pl

XLSX = Path("data/bronze/insee_population/estim-pop-dep-sexe-aq-1975-2026.xlsx")
SILVER = Path("data/silver/population_annual.parquet")
QA = Path("data/reference/qa_population_silver.json")

# Columns of the 20 five-year groups (0-4 ... 95+) for each sex block, as seen in the workbook.
MALE_COLS = [f"column_{i}" for i in range(23, 43)]
FEMALE_COLS = [f"column_{i}" for i in range(44, 64)]
# Group index -> band: groups 0..12 = 0-64, 13..14 = 65-74, 15..16 = 75-84, 17..19 = 85+
BAND_OF_GROUP = ["0-64"] * 13 + ["65-74"] * 2 + ["75-84"] * 2 + ["85+"] * 3
DEPT_RE = r"^(\d{2}|2A|2B|97\d)$"


def read_year(year: int) -> pl.DataFrame:
    raw = pl.read_excel(XLSX, sheet_name=str(year), has_header=False)
    header_idx = next(i for i, v in enumerate(raw["column_2"].to_list()) if v and str(v).startswith("0 à"))
    rows = raw.slice(header_idx + 1).filter(pl.col("column_0").str.strip_chars().str.contains(DEPT_RE))
    out = []
    for sex, cols in (("M", MALE_COLS), ("F", FEMALE_COLS)):
        part = rows.select(dept=pl.col("column_0").str.strip_chars(), *[pl.col(c).cast(pl.Float64, strict=False).alias(f"g{i}") for i, c in enumerate(cols)])
        for band in ["0-64", "65-74", "75-84", "85+"]:
            gcols = [f"g{i}" for i, b in enumerate(BAND_OF_GROUP) if b == band]
            out.append(part.select("dept", pl.sum_horizontal(gcols).alias("pop")).with_columns(year=pl.lit(year), sex=pl.lit(sex), age_band=pl.lit(band)))
    return pl.concat(out)


def build() -> None:
    frames = [read_year(y) for y in range(1975, 2027)]
    pop = pl.concat(frames).select("year", "dept", "sex", "age_band", pl.col("pop").cast(pl.Int64)).sort(["year", "dept", "sex", "age_band"])
    SILVER.parent.mkdir(parents=True, exist_ok=True)
    pop.write_parquet(SILVER)
    totals = pop.group_by("year").agg(pl.col("pop").sum()).sort("year")
    qa = {"rows": pop.height, "departements": pop["dept"].n_unique(), "years": [int(pop["year"].min()), int(pop["year"].max())],
          "france_total_2026": int(totals.filter(pl.col("year") == 2026)["pop"].item()),
          "france_total_2000": int(totals.filter(pl.col("year") == 2000)["pop"].item())}
    QA.write_text(json.dumps(qa, indent=2))
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    build()