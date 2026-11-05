"""Run the stage-1 DLNM in R and draw the pilot curves."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import polars as pl

R_SCRIPT = Path("src/frtm/r/dlnm_stage1.R")
RES = Path("data/results/dlnm")
FIG = Path("docs/figures")
NAMES = {"75": "Paris", "13": "Bouches-du-Rhône", "69": "Rhône", "33": "Gironde", "59": "Nord"}


def run_r(pilots: list[str]) -> None:
    subprocess.run(["Rscript", str(R_SCRIPT), *pilots], check=True)


def plot() -> None:
    curves = pl.read_csv(RES / "curves.csv", schema_overrides={"dept": pl.Utf8})
    summ = pl.read_csv(RES / "summary.csv", schema_overrides={"dept": pl.Utf8})
    lags = pl.read_csv(RES / "lag_curves.csv", schema_overrides={"dept": pl.Utf8})

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    # (a) 85+ overall curves, five départements
    for dept, g in curves.filter(pl.col("age_band") == "85+").group_by("dept", maintain_order=True):
        axes[0].plot(g["tm"], g["rr"], lw=1.6, label=NAMES.get(dept[0], dept[0]))
    axes[0].axhline(1, color="black", lw=0.8); axes[0].set_ylim(0.8, 3); axes[0].set_xlim(-5, 32)
    axes[0].set_title("85+, overall RR over 21 days"); axes[0].set_xlabel("Daily mean temperature (°C)"); axes[0].set_ylabel("Relative risk vs MMT"); axes[0].legend(frameon=False, fontsize=8)
    # (b) Paris, all age bands with CI
    for band, g in curves.filter(pl.col("dept") == "75").group_by("age_band", maintain_order=True):
        axes[1].plot(g["tm"], g["rr"], lw=1.6, label=band[0]); axes[1].fill_between(g["tm"], g["lo"], g["hi"], alpha=0.12)
    axes[1].axhline(1, color="black", lw=0.8); axes[1].set_ylim(0.8, 3); axes[1].set_xlim(-5, 32)
    axes[1].set_title("Paris, by age band (95 % CI)"); axes[1].set_xlabel("Daily mean temperature (°C)"); axes[1].legend(frameon=False, fontsize=8)
    # (c) Paris 85+, lag-response at the 1st and 99th percentiles
    for side, color in (("heat_p99", "#c53030"), ("cold_p1", "#2b6cb0")):
        g = lags.filter((pl.col("dept") == "75") & (pl.col("age_band") == "85+") & (pl.col("side") == side))
        axes[2].plot(g["lag"], g["rr"], color=color, lw=1.6, label=side.replace("_", " at ")); axes[2].fill_between(g["lag"], g["lo"], g["hi"], color=color, alpha=0.12)
    axes[2].axhline(1, color="black", lw=0.8); axes[2].set_title("Paris 85+, RR by lag day"); axes[2].set_xlabel("Lag (days)"); axes[2].legend(frameon=False, fontsize=8)
    for ax in axes: ax.grid(alpha=0.3)
    fig.suptitle("Stage-1 DLNM, five pilot départements, 2000–2025 (Covid months excluded)", fontsize=12)
    fig.tight_layout(); FIG.mkdir(parents=True, exist_ok=True); fig.savefig(FIG / "dlnm_pilot_curves.png", dpi=150); plt.close(fig)

    pl.Config.set_tbl_rows(40); pl.Config.set_tbl_width_chars(200)
    print(summ.with_columns(pl.col("dept").replace(NAMES)).select("dept", "age_band", "mmt", "mmt_pct", "p1", "rr_p1", "p99", "rr_p99", "rr_p99_lo", "rr_p99_hi", "phi"))


def main() -> None:
    pilots = sys.argv[1:] or ["75", "13", "69", "33", "59"]
    run_r(pilots)
    plot()


if __name__ == "__main__":
    main()