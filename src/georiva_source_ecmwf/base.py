"""
Shared base for ECMWF Open Data (HTTPS) forecast sources.

Everything model-agnostic about the https://data.ecmwf.int/forecasts portal
lives here: run-stamp formatting, URL building, step-0 existence probing,
latest-run selection (today -> yesterday fallback) and request generation.

A concrete model (AIFS, IFS, ...) subclasses this and declares:
    MODEL_PATH  - portal path segment, e.g. "aifs-single" or "ifs"
    STREAM      - portal stream segment, e.g. "oper"
    SLUG        - short name used in filenames/identifiers, e.g. "aifs"
    CYCLES      - run hours the model publishes, e.g. [0, 6, 12, 18]
    MAX_FORECAST_HOUR / FORECAST_STEP - step range and cadence

and may override ``is_valid_step`` when the cadence is not uniform.
"""

from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional

import requests

from georiva.sources.fetch import FileRequest, HTTPFetchStrategy
from georiva.sources.source import BaseDataSource, DataSourceType

BASE_URL = "https://data.ecmwf.int/forecasts"
GRID = "0p25"


class ECMWFOpenDataSource(BaseDataSource):
    """
    Base data source for ECMWF Open Data models, HTTPS portal.

    Portal layout:
    https://data.ecmwf.int/forecasts/{YYYYMMDD}/{HH}z/{model}/{grid}/{stream}/
        {YYYYMMDDHHMMSS}-{step}h-{stream}-fc.grib2
        {YYYYMMDDHHMMSS}-{step}h-{stream}-fc.index
    """

    # --- subclass declarations -----------------------------------------
    MODEL_PATH: str = ""  # e.g. "aifs-single", "ifs"
    STREAM: str = "oper"
    SLUG: str = ""  # e.g. "aifs", "ifs"

    CYCLES: list[int] = [0, 6, 12, 18]  # run hours the model publishes
    MAX_FORECAST_HOUR = 360
    FORECAST_STEP = 6

    # (Optional) informational only; selection uses URL existence checks
    AVAILABILITY_DELAY = 7

    def __init__(self, config: dict, fetch_strategy=HTTPFetchStrategy):
        """
        Config options:
            variables: list of variable slugs (metadata; extraction is downstream)
            pressure_levels: list of pressure levels (metadata)
            forecast_hours: list of step hours to fetch
            run_hours: list of run hours to consider (default [0, 12])
            allow_yesterday_fallback: bool (default True) -> if no run found
                today, try yesterday
            head_timeout: int seconds (default 20)
        """
        super().__init__(config, fetch_strategy)

        self.requested_variables = config.get("variables", self.default_variables())
        self.pressure_levels = config.get(
            "pressure_levels", self.default_pressure_levels()
        )

        fh_config = config.get("forecast_hours", [0, 6, 12, 18])
        self.forecast_hours = list(fh_config)

        rt_config = config.get("run_hours", [0, 12])
        # Only run hours the model actually publishes are considered
        self.run_hours = [h for h in rt_config if h in self.CYCLES]

        self.allow_yesterday_fallback = bool(
            config.get("allow_yesterday_fallback", True)
        )
        self.head_timeout = int(config.get("head_timeout", 20))

        # Reuse HTTP session for efficiency
        self._http = requests.Session()

    # --- subclass hooks -------------------------------------------------

    def default_variables(self) -> list[str]:
        return []

    def default_pressure_levels(self) -> list[int]:
        return []

    def is_valid_step(self, step: int) -> bool:
        """Whether the portal publishes this step for this model/stream."""
        return step % self.FORECAST_STEP == 0

    def index_selectors(self, variables: list[str]) -> list[dict] | None:
        """
        JSON-safe selectors for index-selected fetching (plugin ADR 0001),
        placed on request params for ECMWFIndexedHTTPFetchStrategy. None
        (the default) means whole-file fetching.
        """
        return None

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.FORECAST

    # -------------------------------------------------------------------------
    # Latest-run selection (today -> yesterday fallback)
    # -------------------------------------------------------------------------

    def _run_stamp(self, run_time: datetime) -> str:
        # e.g. 20260128060000
        return run_time.strftime("%Y%m%d%H%M%S")

    def _step_url(self, run_time: datetime, step: int) -> str:
        date_folder = run_time.strftime("%Y%m%d")
        run_hour_folder = f"{run_time.hour:02d}z"
        run_stamp = self._run_stamp(run_time)
        return (
            f"{BASE_URL}/{date_folder}/{run_hour_folder}"
            f"/{self.MODEL_PATH}/{GRID}/{self.STREAM}"
            f"/{run_stamp}-{step}h-{self.STREAM}-fc.grib2"
        )

    def _url_exists(self, url: str) -> bool:
        try:
            r = self._http.head(url, allow_redirects=True, timeout=self.head_timeout)
            return r.status_code == 200
        except requests.RequestException:
            return False

    def _candidate_run_times_for_date(self, d) -> list[datetime]:
        # Latest-first for "latest available" behavior
        return [
            datetime(d.year, d.month, d.day, hh, 0, 0, tzinfo=timezone.utc)
            for hh in sorted(self.run_hours, reverse=True)
        ]

    def get_latest_available_run(self) -> Optional[datetime]:
        """
        Returns the latest *published* run time:
        - checks today's run hours, latest first
        - if none found and allow_yesterday_fallback=True, checks yesterday similarly
        """
        today = datetime.now(timezone.utc).date()

        # 1) Today
        for rt in self._candidate_run_times_for_date(today):
            if self._url_exists(self._step_url(rt, 0)):
                return rt

        # 2) Yesterday (fallback)
        if self.allow_yesterday_fallback:
            yesterday = today - timedelta(days=1)
            for rt in self._candidate_run_times_for_date(yesterday):
                if self._url_exists(self._step_url(rt, 0)):
                    return rt

        return None

    # -------------------------------------------------------------------------
    # Forecast-native request generation
    # -------------------------------------------------------------------------

    def generate_requests(
        self, *_, variables: Optional[list[str]] = None, **kwargs
    ) -> Iterator[FileRequest]:
        """
        Generates requests for ONLY the latest available run
        (today, else yesterday if enabled).
        """
        variables = variables or self.requested_variables

        run_time = self.get_latest_available_run()
        if not run_time:
            return  # nothing published yet (or network issue)

        for step in self.forecast_hours:
            # keep it sane
            if step < 0 or step > self.MAX_FORECAST_HOUR:
                continue
            if not self.is_valid_step(step):
                continue

            yield from self._generate_open_data_requests(run_time, step, variables)

    # -------------------------------------------------------------------------
    # Open Data requests (one GRIB2 per step)
    # -------------------------------------------------------------------------

    def _generate_open_data_requests(
        self,
        run_time: datetime,
        step: int,
        variables: list[str],
    ) -> Iterator[FileRequest]:
        valid_time = run_time + timedelta(hours=step)
        run_stamp = self._run_stamp(run_time)  # e.g. 20260128060000
        url = self._step_url(run_time, step)  # step NOT zero-padded

        filename = f"{self.SLUG}_{run_stamp}_{step}h_{self.STREAM}_fc.grib2"

        params = {
            "url": url,
            "source": "open_data",
            "model": self.MODEL_PATH,
            "grid": GRID,
            "run_stamp": run_stamp,
            "step_hours": step,
            "requested_variables": variables,  # metadata only
        }
        selectors = self.index_selectors(variables)
        if selectors:
            params["index_selectors"] = selectors

        yield FileRequest(
            identifier=f"{self.SLUG}-open-{run_stamp}-{step}h",
            filename=filename,
            valid_time=valid_time,
            reference_time=run_time,
            params=params,
            expected_format="grib",
            variables=variables,  # metadata only
        )
