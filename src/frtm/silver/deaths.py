"""Bronze INSEE deaths (one row per person) -> silver deaths_daily (one row per day x dept x age band x sex).

Steps: keep needed columns, parse YYYYMMDD strings, impute unknown day/month, drop deaths
abroad and before 1970, remove duplicates across monthly files, compute age and band,
aggregate, then fill every missing combination with an explicit zero.
"""

from __future__ import annotations

from datetime import datetime, timezone

import json
from pathlib import Path

import polars as pl

BRONZE = Path("data/bronze/insee_deces")
SILVER = Path("data/silver/deaths_daily.parquet")
QA = Path("data/reference/qa_deaths_silver.json")

DEDUP_KEY = ["nom", "prenoms", "sexe", "date_naissance", "date_deces", "code_insee_deces", "numero_acte_deces"]
AGE_BANDS = ["0-64", "65-74", "75-84", "85+", "unknown"]
SEXES = ["M", "F"]

def parse_yyyymmdd(col: str) -> pl.Expr:
    """Turn '19330228' into a Date. Month '00' -> July, day '00' -> 15th; anything invalid -> null."""
    s = pl.col(col)
    y = s.str.slice(0, 4)
    m = pl.when(s.str.slice(4, 2) == "00").then(pl.lit("07")).otherwise(s.str.slice(4, 2))
    d = pl.when(s.str.slice(6, 2) == "00").then(pl.lit("15")).otherwise(s.str.slice(6, 2))
    return pl.concat_str([y, m, d]).str.to_date("%Y%m%d", strict=False)

def departement(col: str) -> pl.Expr:
    """'75106' -> '75', '2A004' -> '2A', '97411' -> '974'; abroad ('99xxx') or blank -> null."""
    c = pl.col(col).str.strip_chars()
    return (
        pl.when((c == "") | c.str.starts_with("99")).then(None)
        .when(c.str.starts_with("97") | c.str.starts_with("98")).then(c.str.slice(0, 3))
        .otherwise(c.str.slice(0, 2))
    )

def build() -> None:
    qa: dict = {}

    raw = pl.scan_parquet(BRONZE / "*.parquet").select(DEDUP_KEY + ["opposition"])
    qa["rows_bronze"] = raw.select(pl.len()).collect().item()

    dedup = raw.unique(subset=DEDUP_KEY, keep="first")
    qa["rows_after_dedup"] = dedup.select(pl.len()).collect().item()
    qa["duplicates_removed"] = qa["rows_bronze"] - qa["rows_after_dedup"]

    typed = dedup.with_columns(
        date_deces=parse_yyyymmdd("date_deces"),
        date_naissance=parse_yyyymmdd("date_naissance"),
        naissance_imputee=(pl.col("date_naissance").str.slice(4, 2) == "00")
        | (pl.col("date_naissance").str.slice(6, 2) == "00"),
        deces_impute=(pl.col("date_deces").str.slice(4, 2) == "00")
        | (pl.col("date_deces").str.slice(6, 2) == "00"),
        dept=departement("code_insee_deces"),
        sexe=pl.when(pl.col("sexe").is_in(SEXES)).then(pl.col("sexe")).otherwise(pl.lit("U")),
    )

    qa["rows_bad_death_date"] = typed.filter(pl.col("date_deces").is_null()).select(pl.len()).collect().item()
    qa["rows_abroad"] = typed.filter(pl.col("dept").is_null()).select(pl.len()).collect().item()
    qa["rows_before_1970"] = (
        typed.filter(pl.col("date_deces") < pl.date(1970, 1, 1)).select(pl.len()).collect().item()
    )
    qa["rows_death_date_imputed"] = typed.filter(pl.col("deces_impute")).select(pl.len()).collect().item()

    today = pl.lit(datetime.now(timezone.utc).date())
    qa["rows_after_today"] = typed.filter(pl.col("date_deces") > today).select(pl.len()).collect().item()

    kept = typed.filter(
        pl.col("date_deces").is_not_null()
        & pl.col("dept").is_not_null()
        & (pl.col("date_deces") >= pl.date(1970, 1, 1))
        & (pl.col("date_deces") <= today)
    )

    aged = kept.with_columns(
        age=((pl.col("date_deces") - pl.col("date_naissance")).dt.total_days() / 365.25).floor().cast(pl.Int32)
    ).with_columns(
        age=pl.when((pl.col("age") < 0) | (pl.col("age") > 120)).then(None).otherwise(pl.col("age"))
    ).with_columns(
        age_band=pl.when(pl.col("age").is_null()).then(pl.lit("unknown"))
        .when(pl.col("age") < 65).then(pl.lit("0-64"))
        .when(pl.col("age") < 75).then(pl.lit("65-74"))
        .when(pl.col("age") < 85).then(pl.lit("75-84"))
        .otherwise(pl.lit("85+"))
    )

    counts = (
        aged.group_by(["date_deces", "dept", "age_band", "sexe"])
        .agg(deaths=pl.len())
        .rename({"date_deces": "date", "sexe": "sex"})
        .collect(engine="streaming")
    )
    qa["rows_kept"] = int(counts["deaths"].sum())
    qa["unknown_age_rows"] = int(counts.filter(pl.col("age_band") == "unknown")["deaths"].sum())
    qa["sex_unknown_rows"] = int(counts.filter(pl.col("sex") == "U")["deaths"].sum())

    # Complete grid: every date x dept x band x sex, so a missing row never silently means zero.
    depts = counts.group_by("dept").agg(pl.col("deaths").sum()).filter(pl.col("deaths") >= 1000)["dept"].sort()
    qa["departements_kept"] = depts.to_list()
    grid = (
        pl.DataFrame({"date": pl.date_range(counts["date"].min(), counts["date"].max(), "1d", eager=True)})
        .join(pl.DataFrame({"dept": depts}), how="cross")
        .join(pl.DataFrame({"age_band": AGE_BANDS}), how="cross")
        .join(pl.DataFrame({"sex": SEXES + ["U"]}), how="cross")
    )
    full = (
        grid.join(counts, on=["date", "dept", "age_band", "sex"], how="left")
        .with_columns(deaths=pl.col("deaths").fill_null(0).cast(pl.Int32))
        .sort(["date", "dept", "age_band", "sex"])
    )

    SILVER.parent.mkdir(parents=True, exist_ok=True)
    full.write_parquet(SILVER)
    qa["rows_silver"] = full.height
    qa["date_min"], qa["date_max"] = str(full["date"].min()), str(full["date"].max())
    QA.write_text(json.dumps(qa, indent=2, ensure_ascii=False))
    print(json.dumps(qa, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    build()