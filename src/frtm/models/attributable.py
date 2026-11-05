"""Run the attributable-deaths script and summarise the cold vs heat burden."""

from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

RES = Path("data/results/dlnm")
FIG = Path("docs/figures")
COLD, HEAT = "#2b6cb0", "#c53030"


def main() -> None:
    subprocess.run(["Rscript", "src/frtm/r/attributable.R"], check=True)
    cell = pl.read_csv(RES / "attributable_by_cell.csv", schema_overrides={"dept": pl.Utf8})
    year = pl.read_csv(RES / "attributable_by_year.csv", schema_overrides={"dept": pl.Utf8})

    nat = cell.group_by("component").agg(an=pl.col("an").sum(), lo=pl.col("lo").sum(), hi=pl.col("hi").sum()).sort("component")
    total_deaths = cell.filter(pl.col("component") == "cold_moderate")["deaths"].sum()
    nat = nat.with_columns(af_pct=100 * pl.col("an") / total_deaths, per_year=pl.col("an") / 24.7)  # 26 years minus 16 Covid months
    cold = nat.filter(pl.col("component").str.starts_with("cold"))["an"].sum()
    heat = nat.filter(pl.col("component").str.starts_with("heat"))["an"].sum()
    print(nat)
    print(f"\nTotal deaths in scope: {total_deaths:,}   cold-attributable: {cold:,.0f} ({100*cold/total_deaths:.2f} %)   "
          f"heat-attributable: {heat:,.0f} ({100*heat/total_deaths:.2f} %)   cold:heat = {cold/heat:.1f}")

    yr = year.group_by(["year", "side"]).agg(an=pl.col("an").sum()).sort(["year", "side"])
    yr = yr.filter(~pl.col("year").is_in([2020, 2021]))
    byband = cell.with_columns(side=pl.col("component").str.slice(0, 4)).group_by(["age_band", "side"]).agg(an=pl.col("an").sum(), deaths=pl.col("deaths").sum() / 2)
    print(byband.with_columns(af_pct=100 * pl.col("an") / pl.col("deaths")).sort(["age_band", "side"]))

    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    c = yr.filter(pl.col("side") == "cold"); h = yr.filter(pl.col("side") == "heat")
    axes[0].bar(c["year"], c["an"], color=COLD, label="cold (below MMT)")
    axes[0].bar(h["year"], h["an"], bottom=c["an"], color=HEAT, label="heat (above MMT)")
    axes[0].set_ylabel("Attributable deaths per year"); axes[0].set_title("Temperature-attributable deaths, metropolitan France"); axes[0].legend(frameon=False); axes[0].grid(alpha=0.3, axis="y")
    d85 = cell.filter(pl.col("age_band") == "85+").with_columns(side=pl.col("component").str.slice(0, 4)).group_by(["dept", "side"]).agg(an=pl.col("an").sum(), deaths=pl.col("deaths").first())
    d85 = d85.pivot(on="side", index=["dept", "deaths"], values="an").with_columns(cold_pct=100 * pl.col("cold") / pl.col("deaths"), heat_pct=100 * pl.col("heat") / pl.col("deaths"))
    axes[1].scatter(d85["heat_pct"], d85["cold_pct"], s=14, color="#4a5568")
    for r in d85.iter_rows(named=True):
        axes[1].annotate(r["dept"], (r["heat_pct"], r["cold_pct"]), fontsize=5, xytext=(2, 2), textcoords="offset points")
    axes[1].set_xlabel("Heat-attributable fraction, 85+ (%)"); axes[1].set_ylabel("Cold-attributable fraction, 85+ (%)"); axes[1].set_title("Each département, 85+"); axes[1].grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(FIG / "attributable_burden.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()