# Decisions log

## 2026-11-05
- Project skeleton created. R will be used only for the DLNM step (dlnm, mixmeta).
- Deaths source: data.gouv aggregated parquet (resource d7aed239…), not the ~60 raw INSEE files. Reason: already merged, same content plus `fichier_origine` and `opposition` columns.
- Bronze files are named by the source's last_modified date so re-runs after an INSEE update create a new file instead of overwriting.
- Deaths with a blank or foreign (99xxx) commune of death are dropped (~235k rows, 0.8 %). Dept "20" = Corse before the 1976 split; kept as is.
- Death dates after the download date (source typos) are dropped; day/month "00" are imputed to the 15th / July and counted in the QA file.
- Météo-France quality flags: values flagged 2 (doubtful) are blanked; 9 (filtered, not hand-validated) are kept. Oct 2004–Sep 2005 is flagged 9 nationwide; dropping it would remove a whole year.
- Station selection: ≥ 90 % TM completeness 2000–2024, ≤ 800 m altitude, up to 8 per département, best 3 as fallback. Corse split 2A/2B by latitude 42.1 (approximation). TM = TM, else TNTXM, else (TN+TX)/2.
- Baseline model (commit 7): quasi-Poisson GLM per dept × age band, spline trend (6 df), annual + semi-annual Fourier, day-of-week, holidays, log(pop) offset. Training excludes Mar 2020–Jun 2021 and, per département, days outside the 2.5–97.5 % temperature range (EuroMOMO practice).
- Effect of excluding extreme days, ratio of our episode excess to SPF's: 2003 1.02→1.05, 2006 0.65→0.95, 2019 Jun 0.35→0.90, 2019 Jul 0.56→0.76, 2026 1.10→1.26 (SPF figure provisional). Kept the exclusion.
- 2022 not comparable: SPF counts only département-days under canicule vigilance. Redo with the vigilance archive.