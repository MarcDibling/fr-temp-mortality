"""One row per metropolitan département with the meta-regression predictors."""

from __future__ import annotations

from pathlib import Path

import polars as pl

METRO = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]
COASTAL = ["06", "11", "13", "14", "17", "22", "29", "2A", "2B", "30", "33", "34", "35", "40", "44", "50", "56", "59", "62", "64", "66", "76", "80", "83", "85"]
OUT = Path("data/reference/dept_covariates.csv")


def main() -> None:
    w = pl.read_parquet("data/silver/weather_daily.parquet").filter(pl.col("date").is_between(pl.date(2000, 1, 1), pl.date(2025, 12, 31)))
    climate = w.group_by("dept").agg(tm_mean=pl.col("tm").mean(), tm_sd=pl.col("tm").std(),
                                     tm_p1=pl.col("tm").quantile(0.01), tm_p99=pl.col("tm").quantile(0.99))
    pop = pl.read_parquet("data/silver/population_annual.parquet").filter(pl.col("year") == 2013)
    demo = pop.group_by("dept").agg(share_85plus=pl.col("pop").filter(pl.col("age_band") == "85+").sum() / pl.col("pop").sum())
    com = pl.read_parquet("data/reference/communes.parquet").with_columns(density=pl.col("pop") / pl.col("surface_km2"))
    urb = com.group_by("dept").agg(density=pl.col("pop").sum() / pl.col("surface_km2").sum(),
                                   urban_share=pl.col("pop").filter(pl.col("density") > 1500).sum() / pl.col("pop").sum(),
                                   lat=(pl.col("lat") * pl.col("pop")).sum() / pl.col("pop").sum())
    cov = (pl.DataFrame({"dept": METRO}).join(climate, on="dept", how="left").join(demo, on="dept", how="left").join(urb, on="dept", how="left")
             .with_columns(coastal=pl.col("dept").is_in(COASTAL).cast(pl.Int8), log_density=pl.col("density").log()))
    cov.write_csv(OUT)
    print(cov.describe())
    print(cov.sort("urban_share", descending=True).head(8))


if __name__ == "__main__":
    main()