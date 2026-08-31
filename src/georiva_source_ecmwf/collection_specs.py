"""
Collection specs for the ECMWF Open Data feeds (AIFS + IFS).

The raw dicts here are the canonical source of truth for what each feed's
collections contain; feed models parse them through the core
collection-definition parser in get_collection_definitions().

The shared-core variables — same keys, same output units in both models —
are built by the shared helpers below so AIFS and IFS layers stay
comparable side by side. Deliberately Django-free so tests can parse the
specs without a configured settings module.
"""

AIFS_PRESSURE_LEVELS = [1000, 925, 850, 700, 500, 300, 250, 200, 50]

# This slice serves the AIFS list; the IFS-only levels (600, 400, 150,
# 100 hPa) arrive with the IFS-only variables in a later slice.
IFS_PRESSURE_LEVELS = list(AIFS_PRESSURE_LEVELS)


def _height(name, value):
    """Source dict for a height-above-ground level."""
    return {
        "name": name,
        "level": {
            "type": "heightAboveGround",
            "value": value,
            "dimension": "heightAboveGround",
            "unit": "m",
        },
    }


def _pl_source(name, level):
    """Source dict for a pressure level."""
    return {
        "name": name,
        "level": {
            "type": "pressure",
            "value": level,
            "dimension": "isobaricInhPa",
            "unit": "hPa",
        },
    }


def _pl_vars(
    base_key, base_name, source_units, levels, value_range=None, output_units=None
):
    """Generate one variable dict per pressure level."""
    v = [
        {
            "key": f"{base_key}_{lv}",
            "name": f"{base_name} at {lv} hPa",
            "source_units": source_units,
            "source_variable": _pl_source(base_key, lv),
            **({"output_units": output_units} if output_units else {}),
            **({"value_range": value_range} if value_range else {}),
        }
        for lv in levels
    ]
    return v


def _shared_surface_variables():
    """The surface shared core: identical keys and output units in AIFS
    and IFS, so the two models render comparably side by side."""
    return [
        {
            "key": "2t",
            "name": "2m Temperature",
            "source_units": "K",
            "output_units": "degC",
            "source_variable": _height("2t", 2),
            "value_range": (-60.0, 60.0),
        },
        {
            "key": "10u",
            "name": "10m U Wind Component",
            "source_units": "m/s",
            "source_variable": _height("10u", 10),
            "value_range": (-80.0, 80.0),
        },
        {
            "key": "10v",
            "name": "10m V Wind Component",
            "source_units": "m/s",
            "source_variable": _height("10v", 10),
            "value_range": (-80.0, 80.0),
        },
        {
            "key": "msl",
            "name": "Mean Sea Level Pressure",
            "source_units": "Pa",
            "output_units": "hPa",
            "source_variable": "msl",
            "value_range": (870.0, 1080.0),
        },
        {
            "key": "tp",
            "name": "Total Precipitation",
            "source_units": "m",
            "output_units": "mm",
            "source_variable": "tp",
            "value_range": (0.0, 500.0),
        },
        {
            "key": "sp",
            "name": "Surface Pressure",
            "source_units": "Pa",
            "output_units": "hPa",
            "source_variable": "sp",
            "value_range": (470.0, 1080.0),
        },
        {
            "key": "wind_speed_10m",
            "name": "10m Wind Speed",
            "source_units": "m/s",
            "transform": "vector_magnitude",
            "components": {"u": _height("10u", 10), "v": _height("10v", 10)},
            "value_range": (0.0, 80.0),
        },
        {
            "key": "wind_dir_10m",
            "name": "10m Wind Direction",
            "source_units": "deg",
            "transform": "vector_direction",
            "components": {"u": _height("10u", 10), "v": _height("10v", 10)},
            "value_range": (0.0, 360.0),
        },
    ]


def _shared_surface_groups():
    return [
        {
            "key": "temp-pressure",
            "name": "Temperature & Pressure",
            "variable_keys": ["2t", "msl", "sp", "tp"],
        },
        {
            "key": "wind",
            "name": "10m Wind",
            "variable_keys": ["10u", "10v", "wind_speed_10m", "wind_dir_10m"],
        },
    ]


def _shared_pressure_level_variables(levels):
    """The pressure-level shared core: t/u/v/z/q at each level."""
    return [
        *_pl_vars(
            "t",
            "Temperature",
            "K",
            levels,
            value_range=(-100.0, 60.0),
            output_units="degC",
        ),
        *_pl_vars("u", "U Wind Component", "m/s", levels, value_range=(-120.0, 120.0)),
        *_pl_vars("v", "V Wind Component", "m/s", levels, value_range=(-120.0, 120.0)),
        *_pl_vars("z", "Geopotential Height", "m2 s-2", levels, output_units="gpdam"),
        *_pl_vars(
            "q",
            "Specific Humidity",
            "kg kg-1",
            levels,
            value_range=(0.0, 40.0),
            output_units="g kg-1",
        ),
    ]


def _pressure_level_groups(levels):
    return [
        {
            "key": f"pl-{lv}",
            "name": f"{lv} hPa",
            "variable_keys": [
                f"t_{lv}",
                f"u_{lv}",
                f"v_{lv}",
                f"z_{lv}",
                f"q_{lv}",
            ],
        }
        for lv in levels
    ]


AIFS_COLLECTIONS = {
    "ecmwf-aifs-surface": {
        "name": "Surface Variables",
        "time_resolution": "hourly",
        "is_forecast": True,
        "variables": _shared_surface_variables(),
        "groups": _shared_surface_groups(),
    },
    "ecmwf-aifs-pressure-levels": {
        "name": "Pressure Level Variables",
        "time_resolution": "hourly",
        "is_forecast": True,
        "variables": _shared_pressure_level_variables(AIFS_PRESSURE_LEVELS),
        "groups": _pressure_level_groups(AIFS_PRESSURE_LEVELS),
    },
}

IFS_COLLECTIONS = {
    "ecmwf-ifs-surface": {
        "name": "Surface Variables",
        "time_resolution": "hourly",
        "is_forecast": True,
        "variables": _shared_surface_variables(),
        "groups": _shared_surface_groups(),
    },
    "ecmwf-ifs-pressure-levels": {
        "name": "Pressure Level Variables",
        "time_resolution": "hourly",
        "is_forecast": True,
        "variables": _shared_pressure_level_variables(IFS_PRESSURE_LEVELS),
        "groups": _pressure_level_groups(IFS_PRESSURE_LEVELS),
    },
}
