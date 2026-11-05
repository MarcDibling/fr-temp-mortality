.PHONY: ingest ingest-deaths ingest-meteo ingest-population silver gold all
ingest: ingest-deaths ingest-meteo ingest-population
ingest-deaths:
	uv run python -m frtm.ingest.insee_deaths
ingest-meteo:
	uv run python -m frtm.ingest.meteo
ingest-population:
	uv run python -m frtm.ingest.insee_population
silver:
	uv run python -m frtm.silver.deaths
	uv run python -m frtm.silver.weather
	uv run python -m frtm.silver.population
gold:
	uv run python -m frtm.gold.panel
models:
	uv run python -m frtm.models.baseline
	uv run python -m frtm.models.excess
figures:
	uv run python -m frtm.viz.figures
all: ingest silver gold