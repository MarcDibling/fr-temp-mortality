.PHONY: ingest ingest-deaths ingest-meteo silver gold all
ingest: ingest-deaths ingest-meteo
ingest-deaths:
	uv run python -m frtm.ingest.insee_deaths
ingest-meteo:
	uv run python -m frtm.ingest.meteo
