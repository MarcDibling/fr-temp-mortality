"""Gates for the silver deaths table."""

from pathlib import Path

import polars as pl
import pytest

SILVER = Path("data/silver/deaths_daily.parquet")
REF = Path("data/reference/insee_annual_deaths.csv")

pytestmark = pytest.mark.skipif(not SILVER.exists(), reason="run `make silver` first")


@pytest.fixture(scope="module")
def deaths() -> pl.DataFrame:
    return pl.read_parquet(SILVER)


def test_annual_totals_match_insee(deaths):
    """Our yearly totals (deaths in France, DROM included) within 1 % of INSEE's published figures."""
    ref = pl.read_csv(REF)
    ours = deaths.group_by(deaths["date"].dt.year().alias("year")).agg(pl.col("deaths").sum())
    merged = ref.join(ours, on="year", how="left")
    for row in merged.iter_rows(named=True):
        rel = abs(row["deaths"] - row["insee_deaths"]) / row["insee_deaths"]
        assert rel < 0.01, f"{row['year']}: ours {row['deaths']:,} vs INSEE {row['insee_deaths']:,} ({rel:.1%})"


def test_august_2003_idf_doubles(deaths):
    """Paris + petite couronne, 1-14 Aug 2003, about twice the 1999-2002 same-window mean."""
    idf = deaths.filter(pl.col("dept").is_in(["75", "92", "93", "94"]))
    window = idf.filter((pl.col("date").dt.month() == 8) & (pl.col("date").dt.day() <= 14))
    by_year = window.group_by(window["date"].dt.year().alias("year")).agg(pl.col("deaths").sum())
    y2003 = by_year.filter(pl.col("year") == 2003)["deaths"].item()
    base = by_year.filter(pl.col("year").is_between(1999, 2002))["deaths"].mean()
    ratio = y2003 / base
    assert 2.0 < ratio < 3.8, f"2003/baseline ratio = {ratio:.2f}"

def test_grid_is_complete(deaths):
    n_days = (deaths["date"].max() - deaths["date"].min()).days + 1
    n_cells = deaths["dept"].n_unique() * deaths["age_band"].n_unique() * deaths["sex"].n_unique()
    assert deaths.height == n_days * n_cells
    assert (deaths["deaths"] >= 0).all()