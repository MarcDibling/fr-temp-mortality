"""Descriptive figures from the gold panel and the baseline results. Written to docs/figures/."""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

GOLD = Path("data/gold/panel.parquet")
EXPECTED = Path("data/results/expected_daily.parquet")
FIG = Path("docs/figures")
METRO = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]
BANDS = ["0-64", "65-74", "75-84", "85+"]
COLD, HEAT, GREY = "#2b6cb0", "#c53030", "#718096"


def exposure_response() -> None:
    """Observed/expected deaths by 1 °C bin of daily mean temperature, 2000-2025, by age band."""
    res = pl.read_parquet(EXPECTED)
    tm = pl.read_parquet(GOLD, columns=["date", "dept", "tm"]).unique(subset=["date", "dept"])
    d = (res.join(tm, on=["date", "dept"], how="inner")
            .filter(pl.col("date").is_between(pl.date(2000, 1, 1), pl.date(2025, 12, 31)) & pl.col("tm").is_not_null())
            .with_columns(bin=pl.col("tm").round(0)))
    agg = (d.group_by(["age_band", "bin"]).agg(obs=pl.col("deaths").sum(), exp=pl.col("expected").sum(), n=pl.len())
             .filter(pl.col("n") >= 200).with_columns(ratio=pl.col("obs") / pl.col("exp")).sort(["age_band", "bin"]))
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for band, color in zip(BANDS, ["#a0aec0", "#718096", "#e53e3e", "#9b2c2c"]):
        a = agg.filter(pl.col("age_band") == band)
        ax.plot(a["bin"], a["ratio"], marker="o", ms=3, lw=1.5, color=color, label=band)
    ax.axhline(1, color="black", lw=0.8)
    ax.set_xlabel("Daily mean temperature, population-weighted, département level (°C)")
    ax.set_ylabel("Observed / expected deaths")
    ax.set_title("Mortality rises at both ends, steeply with heat in the oldest\nMetropolitan France, 2000–2025, département-days pooled by 1 °C bin")
    ax.legend(title="Age band", frameon=False)
    ax.set_ylim(0.85, 1.8)
    ax.grid(alpha=0.3)
    fig.text(0.01, 0.01, "Expected from a quasi-Poisson baseline per département × age band (season, trend, weekday, holidays). Sources: INSEE deaths, Météo-France.", fontsize=7, color=GREY)
    fig.tight_layout()
    fig.savefig(FIG / "exposure_response_ratio.png", dpi=150)
    plt.close(fig)


def episodes() -> None:
    """Observed vs expected national daily deaths, June-September, for the main heatwave summers."""
    res = pl.read_parquet(EXPECTED)
    nat = (res.group_by("date").agg(obs=pl.col("deaths").sum(), exp=pl.col("expected").sum(), var=(pl.col("phi") * pl.col("expected")).sum())
              .with_columns(lo=pl.col("exp") - 1.96 * pl.col("var").sqrt(), hi=pl.col("exp") + 1.96 * pl.col("var").sqrt())
              .sort("date"))
    years = [2003, 2006, 2019, 2022, 2025, 2026]
    fig, axes = plt.subplots(2, 3, figsize=(13, 6.5), sharey=True)
    for ax, y in zip(axes.flat, years):
        d = nat.filter(pl.col("date").is_between(pl.date(y, 6, 1), pl.date(y, 9, 15)))
        excess = int((d["obs"] - d["exp"]).sum())
        ax.fill_between(d["date"], d["lo"], d["hi"], color=GREY, alpha=0.25, lw=0)
        ax.plot(d["date"], d["exp"], color=GREY, lw=1.2, label="expected")
        ax.plot(d["date"], d["obs"], color=HEAT, lw=1.2, label="observed")
        ax.set_title(f"{y}  —  summer excess {excess:+,}", fontsize=11)
        ax.tick_params(axis="x", labelrotation=45, labelsize=8)
        ax.grid(alpha=0.3)
    axes[0, 0].set_ylabel("Deaths per day, metropolitan France")
    axes[1, 0].set_ylabel("Deaths per day, metropolitan France")
    axes[0, 0].legend(frameon=False, fontsize=9)
    fig.suptitle("Daily deaths against the modelled baseline, 1 June – 15 September", fontsize=13)
    fig.tight_layout()
    fig.savefig(FIG / "episodes_observed_vs_expected.png", dpi=150)
    plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    exposure_response()
    episodes()
    print(f"written to {FIG}/")


if __name__ == "__main__":
    main()