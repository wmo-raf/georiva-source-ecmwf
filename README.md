# GeoRiva ECMWF AIFS

A [GeoRiva](https://github.com/wmo-raf/georiva) source plugin for the
**ECMWF AIFS** (Artificial Intelligence Forecasting System) global forecast,
served as Open Data over HTTPS.

It ships:

- **`ECMWFAIFSDataSource`** — generates download requests for the latest
  published AIFS-single run (today, falling back to yesterday) from
  `https://data.ecmwf.int/forecasts`, over plain HTTPS (`HTTPFetchStrategy`).
  One GRIB2 file is fetched per forecast step; the file holds many variables,
  which are carried as metadata for downstream extraction.
- **`ECMWFAIFSDataFeed`** — a DataFeed with two collections (surface variables
  and pressure-level variables) at 0.25° resolution. The operator chooses which
  model runs (00/06/12/18Z) to fetch and the forecast day range.

## Data model

| Concept | Maps to |
| --- | --- |
| Collection | a variable group — Surface or Pressure Levels |
| DataFeed | the runs to fetch (00/06/12/18Z) + forecast day range + display timezone |
| Variable | an AIFS field (e.g. `2t`, `tp`, `t_850`), plus derived wind speed/direction |

The feed converts its day range into 6-hourly forecast steps (capped at 360h /
15 days) and exposes only the latest published run on each acquisition.

## No credentials required

ECMWF Open Data is public — there is nothing to authenticate. The feed-level
knobs are the model runs, the forecast day range, and a display timezone.

## Install

This plugin installs into a running GeoRiva instance — it is a Python package,
not a standalone service. It needs no environment variables (`requires_env` is
empty).

- **Production:** declare it in the operator's `plugins.toml`
  (`git = "https://github.com/wmo-raf/georiva-source-ecmwf.git"`, with a release
  `tag`), rebuild, and run migrations.
- **Development:** bind-mount the package into the core GeoRiva dev stack — add
  `../plugins/georiva-source-ecmwf/plugins/georiva_source_ecmwf:/georiva/dev-plugins/georiva_source_ecmwf`
  to the core repo's `docker-compose.override.yml` (see its
  `docker-compose.override.sample.yml`), then `make dev-up OV=1` and
  `make dev-makemigrations && make dev-migrate`.

Then in the GeoRiva admin, open **Automated Sources → Set up wizard**, choose
**ECMWF AIFS Data Feed**, pick the runs and forecast range, and select the
collections (surface / pressure levels) to provision.
