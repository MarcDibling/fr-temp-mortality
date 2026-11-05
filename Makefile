.PHONY: ingest silver gold all
ingest:
	uv run python -m frtm.ingest.insee_deaths
silver:
	uv run python -m frtm.silver.deaths
all: ingest silver
