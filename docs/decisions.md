# Decisions log

## 2026-11-05
- Project skeleton created. R will be used only for the DLNM step (dlnm, mixmeta).
- Deaths source: data.gouv aggregated parquet (resource d7aed239…), not the ~60 raw INSEE files. Reason: already merged, same content plus `fichier_origine` and `opposition` columns.
- Bronze files are named by the source's last_modified date so re-runs after an INSEE update create a new file instead of overwriting.