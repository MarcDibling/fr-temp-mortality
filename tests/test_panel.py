from pathlib import Path

import polars as pl
import pytest

GOLD = Path("data/gold/panel.parquet")
pytestmark = pytest.mark.skipif(not GOLD.exists(), reason="run `make gold` first")
METRO = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]


@pytest.fixture(scope="module")
def p() -> pl.DataFrame:
    return pl.read_parquet(GOLD)


def test_shape_is_complete(p):
    m = p.filter(pl.col("dept").is_in(METRO))
    n_days = (m["date"].max() - m["date"].min()).days + 1
    assert m.height == n_days * 96 * 4 * 2


def test_population_present_and_plausible(p):
    m = p.filter(pl.col("dept").is_in(METRO))
    assert m["pop"].is_null().sum() == 0
    total_2020 = m.filter(pl.col("date") == pl.date(2020, 1, 1))["pop"].sum()
    assert 64e6 < total_2020 < 67e6, total_2020


def test_lags_are_shifted_correctly(p):
    d = p.filter((pl.col("dept") == "75") & (pl.col("age_band") == "85+") & (pl.col("sex") == "F")).sort("date")
    assert (d["tm"].shift(1).head(100).drop_nulls() == d["tm_lag1"].head(100).drop_nulls()).all()


def test_paris_rate_august_2003(p):
    d = p.filter((pl.col("dept") == "75") & (pl.col("date") == pl.date(2003, 8, 12)) & (pl.col("age_band") == "85+"))
    rate = d["deaths"].sum() / d["pop"].sum() * 1e5
    assert rate > 20, f"85+ death rate on 12 Aug 2003 = {rate:.1f} per 100k/day"