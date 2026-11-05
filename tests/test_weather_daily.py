from pathlib import Path

import polars as pl
import pytest

SILVER = Path("data/silver/weather_daily.parquet")
pytestmark = pytest.mark.skipif(not SILVER.exists(), reason="run the weather silver step first")

METRO = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]


@pytest.fixture(scope="module")
def w() -> pl.DataFrame:
    return pl.read_parquet(SILVER)


def test_every_metro_departement_present(w):
    missing = sorted(set(METRO) - set(w["dept"].unique().to_list()))
    assert not missing, f"no weather for {missing}"


def test_coverage_since_2000(w):
    cov = (w.filter((pl.col("date") >= pl.date(2000, 1, 1)) & pl.col("dept").is_in(METRO))
             .group_by("dept").agg(c=pl.col("tm").is_not_null().mean()))
    bad = cov.filter(pl.col("c") < 0.97)
    assert bad.height == 0, f"low coverage: {bad.to_dicts()}"


def test_plausible_ranges(w):
    assert w["tm"].min() > -30 and w["tm"].max() < 45
    ok = (w["tx"] >= w["tn"]).fill_null(True).mean()
    assert ok > 0.995, f"tx < tn on {(1 - ok):.2%} of rows"

def test_paris_heatwave_2003(w):
    tx = w.filter((pl.col("dept") == "75") & (pl.col("date") == pl.date(2003, 8, 12)))["tx"].item()
    assert 36 < tx < 41, f"Paris TX on 12 Aug 2003 = {tx}"