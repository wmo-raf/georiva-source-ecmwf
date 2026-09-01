"""
ECMWF Open Data sources (HTTPS): AIFS and IFS

Thin declarative subclass of ECMWFOpenDataSource — see base.py for the
portal mechanics (run-stamp, URL building, probing, latest-run fallback,
request generation).
"""

from .base import ECMWFOpenDataSource
from .collection_specs import IFS_PRESSURE_LEVELS
from .index_fetch import ECMWFIndexedHTTPFetchStrategy
from .steps import is_published_ifs_step


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

    Fetching is index-selected (plugin ADR 0001): each staged GRIB holds
    only the messages matching the feed's configured variables/levels,
    with whole-file fallback when the `.index` is unusable.
    """

    type = "ecmwf-ifs"
    label = "ECMWF IFS"

    MODEL_PATH = "ifs"
    STREAM = "oper"
    SLUG = "ifs"

    CYCLES = [0, 12]
    MAX_FORECAST_HOUR = 360
    FORECAST_STEP = 6

    # The directly-readable surface params, in `.index` naming: the
    # shared core (derived wind variables are computed downstream, not
    # fetched) plus the IFS-only variables — note CAPE is published as
    # "mucape" (most-unstable CAPE).
    SURFACE_PARAMS = [
        "2t",
        "10u",
        "10v",
        "msl",
        "tp",
        "sp",
        "mucape",
        "ptype",
        "10fg",
        "2d",
        "tcwv",
        "ssrd",
    ]

    # The pressure-level shared core, one message per param per level.
    PRESSURE_PARAMS = ["t", "u", "v", "z", "q"]

    PRESSURE_LEVELS = IFS_PRESSURE_LEVELS

    def __init__(self, config: dict, fetch_strategy=ECMWFIndexedHTTPFetchStrategy):
        super().__init__(config, fetch_strategy)

    @property
    def name(self) -> str:
        return "ECMWF IFS"

    def default_variables(self) -> list[str]:
        return list(self.SURFACE_PARAMS)

    def default_pressure_levels(self) -> list[int]:
        return list(self.PRESSURE_LEVELS)

    def is_valid_step(self, step: int) -> bool:
        """
        The portal's piecewise oper cadence: 3-hourly steps exist only up
        to 144h; beyond that only 6-hourly steps (to 360h).
        """
        return is_published_ifs_step(step)

    def index_selectors(self, variables: list[str]) -> list[dict] | None:
        """
        Selectors for the feed's configured shape: the requested surface
        params, plus the pressure-level shared core at the configured
        levels. Unknown/derived variable keys are not fetchable messages
        and are dropped.
        """
        selectors = []
        surface = [v for v in variables if v in self.SURFACE_PARAMS]
        dropped = [v for v in variables if v not in self.SURFACE_PARAMS]
        if dropped:
            # ADR 0001: a message never selected is never staged, and
            # re-fetching history cannot recover it — make the drop loud.
            self.logger.warning(
                f"Requested variables {dropped} are not fetchable surface params; they will not be in the staged subset"
            )
        if surface:
            selectors.append({"levtype": "sfc", "params": surface})
        if self.PRESSURE_PARAMS and self.pressure_levels:
            selectors.append(
                {
                    "levtype": "pl",
                    "params": list(self.PRESSURE_PARAMS),
                    "levels": list(self.pressure_levels),
                }
            )
        return selectors or None
