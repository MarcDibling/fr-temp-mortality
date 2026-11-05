"""Bronze Météo-France station files -> silver weather_daily (one row per day x département).

Steps: read the two parameter files per département, keep temperature and humidity columns
with acceptable quality flags, score every station on completeness since 2000, select the
stations per département by a fixed rule, average them with equal weights.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

BRONZE = Path("data/bronze/meteo")
SILVER = Path("data/silver/weather_daily.parquet")
STATIONS_OUT = Path("data/reference/stations_selected.csv")
QA = Path("data/reference/qa_weather_silver.json")

START = 19990101            # read from here; models start 2000 but lags need late 1999
SCORE_FROM, SCORE_TO = 20000101, 20241231
MIN_COMPLETENESS = 0.90     # share of days with a valid TM over the scoring window
MAX_STATIONS = 8
MIN_STATIONS = 3            # if fewer pass, take the best ones down to this floor
MAX_ALTI = 800              # metres; mountain summits do not represent where people live
BAD_QUALITY = {"2"}    # Météo-France flags: 2 = doubtful, 9 = filtered out
DONORS = {"92": "75", "93": "75"}  # used only if a département has no usable station at all

TEMP_COLS = ["RR", "TN", "TX", "TM", "TNTXM"]
HUM_COLS = ["UN", "UX", "UM"]



def dept_from_poste() -> pl.Expr:
    """Département from the station id. Corse ('20') split 2A/2B by latitude (approximate)."""
    p2 = pl.col("NUM_POSTE").str.slice(0, 2)
    return (
        pl.when(p2.is_in(["97", "98"])).then(pl.col("NUM_POSTE").str.slice(0, 3))
        .when(p2 == "20").then(pl.when(pl.col("LAT") < 42.1).then(pl.lit("2A")).otherwise(pl.lit("2B")))
        .otherwise(p2)
    )

def read_file(path: Path, value_cols: list[str]) -> pl.DataFrame:
    """Read one csv.gz as strings, keep id + value + quality columns, blank out bad-quality values."""
    wanted = ["NUM_POSTE", "NOM_USUEL", "LAT", "LON", "ALTI", "AAAAMMJJ"] + value_cols + [f"Q{c}" for c in value_cols]
    df = pl.read_csv(path, separator=";", infer_schema_length=0)  # everything as str, no guessing
    present = [c for c in wanted if c in df.columns]
    df = df.select(present).with_columns(
        pl.col("AAAAMMJJ").cast(pl.Int64, strict=False),
        pl.col("LAT", "LON", "ALTI").cast(pl.Float64, strict=False),
    ).filter(pl.col("AAAAMMJJ") >= START)
    for c in value_cols:
        if c not in df.columns:
            continue
        val = pl.col(c).str.strip_chars().cast(pl.Float64, strict=False)
        if f"Q{c}" in df.columns:
            val = pl.when(pl.col(f"Q{c}").is_in(BAD_QUALITY)).then(None).otherwise(val)
        df = df.with_columns(val.alias(c))
    return df.drop([c for c in df.columns if c.startswith("Q")]).with_columns(dept=dept_from_poste()).filter(pl.col("dept") != "99")

def load_all() -> pl.DataFrame:
    frames = []
    temp_files = sorted(BRONZE.glob("Q_*_RR-T-Vent.csv.gz"))
    for i, f in enumerate(temp_files, 1):
        print(f"[{i}/{len(temp_files)}] {f.name}")
        t = read_file(f, TEMP_COLS)
        hum_path = BRONZE / f.name.replace("RR-T-Vent", "autres-parametres")
        if hum_path.exists():
            h = read_file(hum_path, HUM_COLS)
            h = h.select([c for c in ["NUM_POSTE", "AAAAMMJJ", *HUM_COLS] if c in h.columns])
            t = t.join(h, on=["NUM_POSTE", "AAAAMMJJ"], how="left")
        frames.append(t)
    df = pl.concat(frames, how="diagonal")
    return df.with_columns(
        date=pl.col("AAAAMMJJ").cast(pl.Utf8).str.to_date("%Y%m%d"),
        TM=pl.coalesce(pl.col("TM"), pl.col("TNTXM"), (pl.col("TN") + pl.col("TX")) / 2),
    ).drop("AAAAMMJJ", "TNTXM")

def select_stations(df: pl.DataFrame) -> pl.DataFrame:
    """Score stations on TM completeness 2000-2024 and apply the per-département rule."""
    n_days = (pl.date(2024, 12, 31) - pl.date(2000, 1, 1)).dt.total_days() + 1
    window = df.filter(pl.col("date").is_between(pl.date(2000, 1, 1), pl.date(2024, 12, 31)))
    scores = (
        window.group_by(["dept", "NUM_POSTE"])
        .agg(
            nom=pl.col("NOM_USUEL").last(), lat=pl.col("LAT").last(), lon=pl.col("LON").last(), alti=pl.col("ALTI").last(),
            completeness=pl.col("TM").is_not_null().sum() / n_days,
            humidity_completeness=pl.col("UM").is_not_null().sum() / n_days,
        )
        .filter(pl.col("alti").fill_null(0) <= MAX_ALTI)
        .sort(["dept", "completeness"], descending=[False, True])
    )
    good = scores.filter(pl.col("completeness") >= MIN_COMPLETENESS).group_by("dept").head(MAX_STATIONS)
    n_good = scores.select("dept").unique().join(good.group_by("dept").len(), on="dept", how="left").with_columns(pl.col("len").fill_null(0))
    short = n_good.filter(pl.col("len") < MIN_STATIONS)["dept"]
    fallback = scores.filter(pl.col("dept").is_in(short.to_list())).group_by("dept").head(MIN_STATIONS)
    selected = pl.concat([good.filter(~pl.col("dept").is_in(short.to_list())), fallback]).sort(["dept", "completeness"], descending=[False, True])
    return selected.with_columns(rule=pl.when(pl.col("completeness") >= MIN_COMPLETENESS).then(pl.lit("completeness>=0.90")).otherwise(pl.lit("fallback_best_available")))


def build() -> None:
    df = load_all()
    stations = select_stations(df)
    STATIONS_OUT.parent.mkdir(parents=True, exist_ok=True)
    stations.write_csv(STATIONS_OUT)

    kept = df.join(stations.select("dept", "NUM_POSTE"), on=["dept", "NUM_POSTE"], how="inner")
    daily = (
        kept.group_by(["date", "dept"])
        .agg(
            tn=pl.col("TN").mean(), tx=pl.col("TX").mean(), tm=pl.col("TM").mean(),
            um=pl.col("UM").mean(), rr=pl.col("RR").mean(),
            n_stations=pl.col("TM").is_not_null().sum(),
        )
        .sort(["dept", "date"])
    )
    present = daily["dept"].unique().to_list()
    for dst, src in DONORS.items():
        if dst not in present:
            daily = pl.concat([daily, daily.filter(pl.col("dept") == src).with_columns(dept=pl.lit(dst))])
    daily = daily.sort(["dept", "date"])
    SILVER.parent.mkdir(parents=True, exist_ok=True)
    daily.write_parquet(SILVER)

    cov = (
        daily.filter(pl.col("date") >= pl.date(2000, 1, 1))
        .group_by("dept")
        .agg(days=pl.len(), tm_coverage=pl.col("tm").is_not_null().mean(), um_coverage=pl.col("um").is_not_null().mean())
        .sort("dept")
    )
    qa = {
        "station_days_read": df.height,
        "stations_scored": int(df.select("dept", "NUM_POSTE").unique().height),
        "stations_selected": stations.height,
        "departements": stations["dept"].n_unique(),
        "depts_on_fallback": stations.filter(pl.col("rule") != "completeness>=0.90")["dept"].unique().sort().to_list(),
        "rows_silver": daily.height,
        "date_min": str(daily["date"].min()), "date_max": str(daily["date"].max()),
        "coverage_2000plus": cov.to_dicts(),
    }
    QA.write_text(json.dumps(qa, indent=2, ensure_ascii=False))
    print(json.dumps({k: v for k, v in qa.items() if k != "coverage_2000plus"}, indent=2, ensure_ascii=False))
    print(cov.filter(pl.col("tm_coverage") < 0.98))


if __name__ == "__main__":
    build()