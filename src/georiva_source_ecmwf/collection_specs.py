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

# The AIFS list plus the levels only the IFS oper files carry.
IFS_PRESSURE_LEVELS = [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50]


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


def _shared_surface_variables(tp_source_units="m"):
    """The surface shared core: identical keys and exposed units in AIFS
    and IFS, so the two models render comparably side by side.

    Source units may differ per model where the portals stamp the same
    field differently: IFS tp is metres (paramId 228) while AIFS tp is
    kg m-2 — numerically millimetres — (paramId 228228), so AIFS passes
    tp_source_units="mm" and the mm->mm conversion is a no-op (issue #15).
    Both models expose mm. Every other surface param carries the same raw
    unit in both portals (verified against live GRIB messages).
    """
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
            "source_units": tp_source_units,
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


def _ifs_only_surface_variables():
    """The surface variables only IFS carries — no AIFS counterpart.

    Names, units, levels and observed value spans were verified against
    live 0.25° oper GRIB2 messages and their ``.index`` param names.
    Convective precipitation (cp) is deliberately absent: the open-data
    oper files do not publish it.
    """
    return [
        {
            # Published as most-unstable CAPE; there is no plain "cape"
            # message in the oper files.
            "key": "cape",
            "name": "CAPE (Most-Unstable)",
            "source_units": "J kg-1",
            "source_variable": "mucape",
            "value_range": (0.0, 12000.0),
        },
        {
            # GRIB code table 4.201 (0 = none, 1 = rain, ... 12).
            "key": "ptype",
            "name": "Precipitation Type",
            "source_units": "dimensionless",
            "source_variable": "ptype",
            "value_range": (0.0, 12.0),
        },
        {
            "key": "10fg",
            "name": "10m Wind Gust",
            "source_units": "m/s",
            "source_variable": _height("10fg", 10),
            "value_range": (0.0, 100.0),
        },
        {
            "key": "2d",
            "name": "2m Dewpoint Temperature",
            "source_units": "K",
            "output_units": "degC",
            "source_variable": _height("2d", 2),
            "value_range": (-70.0, 50.0),
        },
        {
            "key": "tcwv",
            "name": "Total Column Water Vapour",
            "source_units": "kg m-2",
            "source_variable": "tcwv",
            "value_range": (0.0, 100.0),
        },
        {
            # Accumulated from the start of the forecast, so the span
            # covers a full 360h run (~30 MJ/day of insolation).
            "key": "ssrd",
            "name": "Downward Surface Solar Radiation",
            "source_units": "J m-2",
            "output_units": "MJ m-2",
            "source_variable": "ssrd",
            "value_range": (0.0, 500.0),
        },
    ]


def _source_name(variable):
    """The GRIB shortName a spec variable reads (None for transforms)."""
    source = variable.get("source_variable")
    if source is None:
        return None
    return source["name"] if isinstance(source, dict) else source


def _ifs_surface_groups():
    return [
        *_shared_surface_groups(),
        {
            "key": "convection",
            "name": "Convection",
            "variable_keys": ["cape", "ptype", "10fg"],
        },
        {
            "key": "moisture-radiation",
            "name": "Moisture & Radiation",
            "variable_keys": ["2d", "tcwv", "ssrd"],
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
        # AIFS tp arrives as kg m-2 (numerically mm) — no m->mm conversion.
        "variables": _shared_surface_variables(tp_source_units="mm"),
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
        "variables": [*_shared_surface_variables(), *_ifs_only_surface_variables()],
        "groups": _ifs_surface_groups(),
    },
    "ecmwf-ifs-pressure-levels": {
        "name": "Pressure Level Variables",
        "time_resolution": "hourly",
        "is_forecast": True,
        "variables": _shared_pressure_level_variables(IFS_PRESSURE_LEVELS),
        "groups": _pressure_level_groups(IFS_PRESSURE_LEVELS),
    },
}

# The `.index` params the IFS surface collection needs, derived from the
# spec so a variable added above is fetched without a second edit (the
# portal's index `param` equals the GRIB shortName for every message we
# read — e.g. the "cape" variable selects the "mucape" message). Derived
# transforms carry no source and are computed downstream, not fetched.
IFS_SURFACE_INDEX_PARAMS = [
    name
    for v in [*_shared_surface_variables(), *_ifs_only_surface_variables()]
    if (name := _source_name(v)) is not None
]
