"""Run the meta-regression and plot 85+ curves at low vs high values of each predictor."""

from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

RES = Path("data/results/dlnm")
FIG = Path("docs/figures")
LABEL = {"tm_mean": "mean temperature", "share_85plus": "share aged 85+", "urban_share": "urban share"}


def main() -> None:
    subprocess.run(["Rscript", "src/frtm/r/dlnm_meta.R"], check=True)
    meta = pl.read_csv(RES / "meta_regression.csv")
    curves = pl.read_csv(RES / "meta_curves.csv")
    pl.Config.set_tbl_rows(40); pl.Config.set_tbl_width_chars(160)
    print(meta.filter(pl.col("model") == "multivariable").select("age_band", "predictor", "wald", "p_value", "I2_before", "I2_after"))

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=True)
    for ax, p in zip(axes, LABEL):
        for q, color in ((0.25, "#2b6cb0"), (0.75, "#c53030")):
            g = curves.filter((pl.col("age_band") == "85+") & (pl.col("predictor") == p) & (pl.col("quantile") == q))
            v = g["value"][0]
            ax.plot(g["pct"], g["rr"], color=color, lw=1.8, label=f"{'low' if q == 0.25 else 'high'} {LABEL[p]} ({v:.2f})")
            ax.fill_between(g["pct"], g["lo"], g["hi"], color=color, alpha=0.12)
        ax.axhline(1, color="black", lw=0.8); ax.set_xlabel("Temperature percentile"); ax.set_title(f"85+, by {LABEL[p]}"); ax.legend(frameon=False, fontsize=8); ax.grid(alpha=0.3)
    axes[0].set_ylabel("Relative risk vs MMT"); axes[0].set_ylim(0.9, 2.6)
    fig.suptitle("Meta-regression: predicted pooled curve at the 25th vs 75th percentile of each département characteristic", fontsize=11)
    fig.tight_layout(); fig.savefig(FIG / "meta_regression_curves.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()