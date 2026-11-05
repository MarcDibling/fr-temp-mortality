# fr-temp-mortality

Daily all-cause mortality in France (INSEE, 1970–) joined to Météo-France station
temperatures, modelled with distributed-lag non-linear models by département and age,
with an early-warning evaluation, cross-country comparison and 2050 scenarios.
Published as a dashboard.

## Pre-registered modelling choices (fixed before looking at results)
- Spatial unit: département (96 metropolitan). Period for models: 2000-01-01 onward.
- Age bands: 0–64, 65–74, 75–84, 85+.
- Exposure: population-weighted daily mean temperature from 3–8 stations per département.
- Model: quasi-Poisson, cross-basis with natural splines, knots at the 10th/75th/90th
  percentiles, lag 0–21, 8 df per year for season/trend, day-of-week, holidays.
- Exclusion: 1 Mar 2020 – 30 Jun 2021 (sensitivity analysis includes them).
- Validation: 2000–2019 for fitting and tuning; 2022–2025 held out.

## Run
`make all`
