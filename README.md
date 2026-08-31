# GeoRiva ECMWF Open Data

A [GeoRiva](https://github.com/wmo-raf/georiva) source plugin for ECMWF's
Open Data global forecasts, served over HTTPS: **AIFS** (Artificial
Intelligence Forecasting System) and **IFS** (the physics-based Integrated
Forecasting System, deterministic `oper` stream).

It ships:

- **`ECMWFAIFSDataSource`** / **`ECMWFIFSDataSource`** — thin subclasses of a
  shared `ECMWFOpenDataSource` base that generates download requests for the
  latest published run (today, falling back to yesterday) from
  `https://data.ecmwf.int/forecasts`, over plain HTTPS (`HTTPFetchStrategy`).
  One GRIB2 file is fetched per forecast step; the file holds many variables,
  which are carried as metadata for downstream extraction.
- **`ECMWFAIFSDataFeed`** / **`ECMWFIFSDataFeed`** — DataFeeds with two
  collections each (surface variables and pressure-level variables) at 0.25°
  resolution. The operator chooses which model runs to fetch — 00/06/12/18Z
  for AIFS, 00/12Z for IFS (the cycles `oper` serves out to 360h) — and the
  forecast day range.

The two models share a variable core — identical keys and output units for
2m temperature, 10m wind (components, speed, direction), MSL/surface
pressure, total precipitation, and t/u/v/z/q on the pressure levels — so
AIFS and IFS layers render comparably side by side.

## Data model

| Concept | Maps to |
| --- | --- |
| Collection | a variable group — Surface or Pressure Levels (per model) |
| DataFeed | the runs to fetch + forecast day range + step cadence (IFS) + display timezone |
| Variable | a model field (e.g. `2t`, `tp`, `t_850`), plus derived wind speed/direction |

Each feed converts its day range into forecast steps (capped at 360h /
15 days) and exposes only the latest published run on each acquisition.
AIFS steps are 6-hourly; an IFS feed chooses a 3-hourly or 6-hourly
cadence (default 6-hourly). The portal publishes 3-hourly steps only up
to 144h, so a 3-hourly feed silently continues 6-hourly beyond that.

## No credentials required

ECMWF Open Data is public — there is nothing to authenticate. The feed-level
knobs are the model runs, the forecast day range, the step cadence
(IFS only), and a display timezone.

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
**ECMWF AIFS Data Feed** or **ECMWF IFS Data Feed**, pick the runs and
forecast range, and select the collections (surface / pressure levels) to
provision.
