.PHONY: ingest ingest-deaths ingest-meteo ingest-population silver gold figures dlnm attributable all
ingest: ingest-deaths ingest-meteo ingest-population
ingest-deaths:
	uv run python -m frtm.ingest.insee_deaths
ingest-meteo:
	uv run python -m frtm.ingest.meteo
ingest-population:
	uv run python -m frtm.ingest.insee_population
ingest-communes:
	uv run python -m frtm.ingest.communes
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
dlnm:
	uv run python -m frtm.models.dlnm
attributable:
	uv run python -m frtm.models.attributable
all: ingest silver gold