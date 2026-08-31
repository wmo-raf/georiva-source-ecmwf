"""
ECMWF Open Data sources (HTTPS): AIFS and IFS

Thin declarative subclass of ECMWFOpenDataSource — see base.py for the
portal mechanics (run-stamp, URL building, probing, latest-run fallback,
request generation).
"""

from .base import ECMWFOpenDataSource
from .collection_specs import IFS_PRESSURE_LEVELS


class ECMWFAIFSDataSource(ECMWFOpenDataSource):
    """
    Data source for ECMWF AIFS (Artificial Intelligence Forecasting
    System), Open Data HTTPS.
    """

    type = "ecmwf-aifs"
    label = "ECMWF AIFS"

    MODEL_PATH = "aifs-single"
    STREAM = "oper"
    SLUG = "aifs"

    # source_units describes the RAW unit each field carries in the GRIB2 file.
    # The output unit a Collection exposes (after conversion) lives in models.py
    # COLLECTIONS, not here.
    SURFACE_VARIABLES = {
        "2t": {"name": "2m Temperature", "source_units": "K", "grib_param": 167},
        "10u": {"name": "10m U Wind", "source_units": "m/s", "grib_param": 165},
        "10v": {"name": "10m V Wind", "source_units": "m/s", "grib_param": 166},
        "msl": {
            "name": "Mean Sea Level Pressure",
            "source_units": "Pa",
            "grib_param": 151,
        },
        "tp": {"name": "Total Precipitation", "source_units": "m", "grib_param": 228},
        "sp": {"name": "Surface Pressure", "source_units": "Pa", "grib_param": 134},
    }

    PRESSURE_VARIABLES = {
        "t": {"name": "Temperature", "source_units": "K", "grib_param": 130},
        "u": {"name": "U Wind", "source_units": "m/s", "grib_param": 131},
        "v": {"name": "V Wind", "source_units": "m/s", "grib_param": 132},
        "z": {"name": "Geopotential", "source_units": "m²/s²", "grib_param": 129},
        "q": {"name": "Specific Humidity", "source_units": "kg/kg", "grib_param": 133},
    }

    PRESSURE_LEVELS = [1000, 925, 850, 700, 500, 300, 250, 200, 50]

    @property
    def name(self) -> str:
        return "ECMWF AIFS"

    def default_variables(self) -> list[str]:
        return list(self.SURFACE_VARIABLES.keys())

    def default_pressure_levels(self) -> list[int]:
        return self.PRESSURE_LEVELS


class ECMWFIFSDataSource(ECMWFOpenDataSource):
    """
    Data source for ECMWF IFS (Integrated Forecasting System), the
    physics-based deterministic model — `oper` stream, Open Data HTTPS.

    Only the 00Z and 12Z cycles are served: the portal's 06Z/18Z cycles
    belong to the short-cutoff `scda` stream, which is out of scope.
    Fetching is whole-file in this slice.
    """

    type = "ecmwf-ifs"
    label = "ECMWF IFS"

    MODEL_PATH = "ifs"
    STREAM = "oper"
    SLUG = "ifs"

    CYCLES = [0, 12]
    MAX_FORECAST_HOUR = 360
    FORECAST_STEP = 6

    PRESSURE_LEVELS = IFS_PRESSURE_LEVELS

    @property
    def name(self) -> str:
        return "ECMWF IFS"

    def default_variables(self) -> list[str]:
        # The directly-readable surface shared core (derived wind
        # variables are computed downstream, not fetched).
        return ["2t", "10u", "10v", "msl", "tp", "sp"]

    def default_pressure_levels(self) -> list[int]:
        return list(self.PRESSURE_LEVELS)
