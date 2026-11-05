# Decisions log

## 2026-11-05
- Project skeleton created. R will be used only for the DLNM step (dlnm, mixmeta).
- Deaths source: data.gouv aggregated parquet (resource d7aed239…), not the ~60 raw INSEE files. Reason: already merged, same content plus `fichier_origine` and `opposition` columns.
- Bronze files are named by the source's last_modified date so re-runs after an INSEE update create a new file instead of overwriting.
- Deaths with a blank or foreign (99xxx) commune of death are dropped (~235k rows, 0.8 %). Dept "20" = Corse before the 1976 split; kept as is.
- Death dates after the download date (source typos) are dropped; day/month "00" are imputed to the 15th / July and counted in the QA file.