"""Join deaths, weather and population into the model-ready panel:
one row per date x dept x age_band x sex from 1999-01-01, with daily-interpolated
population, calendar terms and temperature lags 0-21."""

from __future__ import annotations

import json
from pathlib import Path

import holidays
import polars as pl

DEATHS = Path("data/silver/deaths_daily.parquet")
WEATHER = Path("data/silver/weather_daily.parquet")
POP = Path("data/silver/population_annual.parquet")
GOLD = Path("data/gold/panel.parquet")
QA = Path("data/reference/qa_panel_gold.json")

START = pl.date(1999, 1, 1)
MAX_LAG = 21
METRO = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]


def daily_population(pop: pl.DataFrame, dates: pl.Series) -> pl.DataFrame:
    """Linear interpolation between 1 January values; flat after the last year."""
    years = pl.DataFrame({"date": dates}).with_columns(year=pl.col("date").dt.year(), doy=pl.col("date").dt.ordinal_day(),
                                                       ndays=pl.when(pl.col("date").dt.is_leap_year()).then(366).otherwise(365))
    nxt = pop.with_columns(year=pl.col("year") - 1).rename({"pop": "pop_next"})
    both = pop.join(nxt, on=["year", "dept", "sex", "age_band"], how="left").with_columns(pop_next=pl.col("pop_next").fill_null(pl.col("pop")))
    return (years.join(both, on="year", how="inner")
                 .with_columns(pop=(pl.col("pop") + (pl.col("pop_next") - pl.col("pop")) * (pl.col("doy") - 1) / pl.col("ndays")))
                 .select("date", "dept", "sex", "age_band", "pop"))


def build() -> None:
    deaths = pl.read_parquet(DEATHS).filter((pl.col("date") >= START) & pl.col("sex").is_in(["M", "F"]) & (pl.col("age_band") != "unknown"))
    weather = pl.read_parquet(WEATHER).filter(pl.col("date") >= START).sort(["dept", "date"])
    pop = pl.read_parquet(POP).filter(pl.col("year") >= 1999)

    # Temperature lags, computed once per dept-day (identical for every age/sex cell).
    weather = weather.with_columns([pl.col("tm").shift(k).over("dept").alias(f"tm_lag{k}") for k in range(1, MAX_LAG + 1)])

    dates = pl.date_range(deaths["date"].min(), deaths["date"].max(), "1d", eager=True)
    popd = daily_population(pop, dates)

    fr_hol = holidays.France(years=range(1999, dates.max().year + 1))
    cal = pl.DataFrame({"date": dates}).with_columns(
        dow=pl.col("date").dt.weekday(), year=pl.col("date").dt.year(), doy=pl.col("date").dt.ordinal_day(),
        holiday=pl.col("date").is_in(list(fr_hol.keys())),
        covid=pl.col("date").is_between(pl.date(2020, 3, 1), pl.date(2021, 6, 30)),
    )

    panel = (deaths.join(popd, on=["date", "dept", "sex", "age_band"], how="inner")
                   .join(weather, on=["date", "dept"], how="left")
                   .join(cal, on="date", how="left")
                   .sort(["dept", "age_band", "sex", "date"]))

    GOLD.parent.mkdir(parents=True, exist_ok=True)
    panel.write_parquet(GOLD)
    metro = panel.filter(pl.col("dept").is_in(METRO))
    qa = {"rows": panel.height, "departements": panel["dept"].n_unique(), "date_min": str(panel["date"].min()), "date_max": str(panel["date"].max()),
          "metro_rows_missing_tm": int(metro["tm"].is_null().sum()), "metro_rows_missing_pop": int(metro["pop"].is_null().sum()),
          "deaths_total": int(panel["deaths"].sum()),
          "deaths_in_silver_same_scope": int(deaths.filter(pl.col("dept").is_in(panel["dept"].unique()))["deaths"].sum())}
    QA.write_text(json.dumps(qa, indent=2))
    print(json.dumps(qa, indent=2))


if __name__ == "__main__":
    build()