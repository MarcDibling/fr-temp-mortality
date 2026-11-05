"""Expected daily deaths per département x age band (sexes combined), quasi-Poisson GLM.

Model, fitted on 2000-01-01 .. latest, excluding Mar 2020 - Jun 2021:
  log E[deaths] = log(pop) + smooth trend (natural cubic spline, 6 df over 26 years)
                  + annual + semi-annual Fourier terms + day of week + public holiday
Prediction intervals use the overdispersion phi: deaths ~ mu ± 1.96 * sqrt(phi * mu).
Output: data/results/expected_daily.parquet with observed, expected, lo95, hi95, excess.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import statsmodels.api as sm
import statsmodels.formula.api as smf

GOLD = Path("data/gold/panel.parquet")
OUT = Path("data/results/expected_daily.parquet")
QA = Path("data/reference/qa_baseline.json")

METRO = [f"{i:02d}" for i in range(1, 96) if i != 20] + ["2A", "2B"]
BANDS = ["0-64", "65-74", "75-84", "85+"]
COVID = (pl.date(2020, 3, 1), pl.date(2021, 6, 30))
FORMULA = "deaths ~ cr(t, df=6, constraints='center') + s1 + c1 + s2 + c2 + C(dow) + holiday"

def load() -> pl.DataFrame:
    p = pl.read_parquet(GOLD, columns=["date", "dept", "age_band", "sex", "deaths", "pop", "dow", "holiday", "tm"])
    p = p.filter(pl.col("dept").is_in(METRO)).group_by(["date", "dept", "age_band"]).agg(
        deaths=pl.col("deaths").sum(), pop=pl.col("pop").sum(), dow=pl.col("dow").first(), holiday=pl.col("holiday").first(), tm=pl.col("tm").first()
    )
    t = (pl.col("date") - pl.date(2000, 1, 1)).dt.total_days().cast(pl.Float64)
    w = 2 * np.pi / 365.25
    return p.with_columns(
        t=t, s1=(t * w).sin(), c1=(t * w).cos(), s2=(2 * t * w).sin(), c2=(2 * t * w).cos(),
        holiday=pl.col("holiday").cast(pl.Int8),
        train=(~pl.col("date").is_between(*COVID)
               & pl.col("tm").is_between(pl.col("tm").quantile(0.025).over("dept"), pl.col("tm").quantile(0.975).over("dept"))).fill_null(False),
    ).sort(["dept", "age_band", "date"])


def fit_one(df: pl.DataFrame) -> pl.DataFrame:
    pdf = df.to_pandas()
    tr = pdf[pdf["train"]]
    model = smf.glm(FORMULA, data=tr, family=sm.families.Poisson(), offset=np.log(tr["pop"]))
    res = model.fit(scale="X2")  # quasi-Poisson: Pearson-chi2 dispersion
    mu = res.predict(pdf, offset=np.log(pdf["pop"]))
    phi = float(res.scale)
    sd = np.sqrt(phi * mu)
    return df.with_columns(
        expected=pl.Series(mu.to_numpy()), phi=pl.lit(phi),
        lo95=pl.Series(np.clip(mu - 1.96 * sd, 0, None).to_numpy()), hi95=pl.Series((mu + 1.96 * sd).to_numpy()),
    ).with_columns(excess=pl.col("deaths") - pl.col("expected"))


def build() -> None:
    data = load()
    out = []
    groups = data.partition_by(["dept", "age_band"], as_dict=True)
    for i, ((dept, band), df) in enumerate(sorted(groups.items()), 1):
        if i % 40 == 0:
            print(f"{i}/{len(groups)} fitted")
        out.append(fit_one(df))
    res = pl.concat(out).select("date", "dept", "age_band", "deaths", "pop", "expected", "lo95", "hi95", "excess", "phi")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    res.write_parquet(OUT)

    nat = res.group_by(res["date"].dt.year().alias("year")).agg(observed=pl.col("deaths").sum(), expected=pl.col("expected").sum()).sort("year")
    aug03 = res.filter(pl.col("date").is_between(pl.date(2003, 8, 1), pl.date(2003, 8, 20)))
    qa = {"models": len(groups), "phi_median": float(res["phi"].median()),
          "excess_1_20_aug_2003_metro": int(aug03["excess"].sum()),
          "annual_national": [{"year": int(r["year"]), "observed": int(r["observed"]), "expected": int(r["expected"])} for r in nat.iter_rows(named=True)]}
    QA.write_text(json.dumps(qa, indent=2))
    print(json.dumps({k: v for k, v in qa.items() if k != "annual_national"}, indent=2))
    print(nat)


if __name__ == "__main__":
    build()