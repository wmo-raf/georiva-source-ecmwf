"""
Characterization tests for the ECMWF AIFS data source.

These pin the source's observable behaviour at its public seam
(``generate_requests`` / ``get_latest_available_run``) with HTTP stubbed
at the session boundary and the clock frozen. No network access.
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from georiva_source_ecmwf.source import ECMWFAIFSDataSource, ECMWFIFSDataSource

FROZEN_NOW = datetime(2026, 8, 15, 14, 30, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    """datetime whose now() is pinned to FROZEN_NOW."""

    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW.astimezone(tz) if tz else FROZEN_NOW.replace(tzinfo=None)


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeSession:
    """Stands in for requests.Session; answers HEAD by URL substring match."""

    def __init__(self, ok_substrings):
        self.ok_substrings = list(ok_substrings)
        self.head_urls = []

    def head(self, url, **kwargs):
        self.head_urls.append(url)
        ok = any(s in url for s in self.ok_substrings)
        return _FakeResponse(200 if ok else 404)


def _make_source(config=None, ok_substrings=(), cls=ECMWFAIFSDataSource):
    source = cls(config or {})
    source._http = _FakeSession(ok_substrings)
    return source


class FrozenClockTestCase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("georiva_source_ecmwf.base.datetime", _FrozenDatetime)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.today = FROZEN_NOW.date()
        self.date_folder = self.today.strftime("%Y%m%d")  # 20260815


class GenerateRequestsTest(FrozenClockTestCase):
    def test_request_urls_follow_open_data_layout_for_latest_run(self):
        # Only today's 12z run is published
        source = _make_source(
            config={"forecast_hours": [0, 6], "run_hours": [0, 12]},
            ok_substrings=[f"/{self.date_folder}/12z/"],
        )

        requests_out = list(source.generate_requests())

        self.assertEqual(len(requests_out), 2)
        run_stamp = "20260815120000"
        self.assertEqual(
            requests_out[0].params["url"],
            "https://data.ecmwf.int/forecasts"
            "/20260815/12z/aifs-single/0p25/oper/20260815120000-0h-oper-fc.grib2",
        )
        self.assertEqual(
            requests_out[1].params["url"],
            "https://data.ecmwf.int/forecasts"
            "/20260815/12z/aifs-single/0p25/oper/20260815120000-6h-oper-fc.grib2",
        )
        self.assertEqual(requests_out[0].identifier, f"aifs-open-{run_stamp}-0h")
        self.assertEqual(requests_out[1].filename, f"aifs_{run_stamp}_6h_oper_fc.grib2")
        self.assertEqual(requests_out[1].expected_format, "grib")

    def test_step_not_on_six_hour_cadence_or_beyond_range_is_skipped(self):
        source = _make_source(
            config={"forecast_hours": [0, 3, 6, 366, -6], "run_hours": [0]},
            ok_substrings=[f"/{self.date_folder}/00z/"],
        )

        steps = [r.params["step_hours"] for r in source.generate_requests()]

        self.assertEqual(steps, [0, 6])

    def test_valid_and_reference_times_derive_from_run_and_step(self):
        source = _make_source(
            config={"forecast_hours": [12], "run_hours": [0]},
            ok_substrings=[f"/{self.date_folder}/00z/"],
        )

        (request,) = list(source.generate_requests())

        run_time = datetime(2026, 8, 15, tzinfo=timezone.utc)
        self.assertEqual(request.reference_time, run_time)
        self.assertEqual(request.valid_time, run_time + timedelta(hours=12))


class LatestRunSelectionTest(FrozenClockTestCase):
    def test_prefers_latest_published_cycle_of_today(self):
        # Both 00z and 12z published; latest (12z) must win
        source = _make_source(
            config={"run_hours": [0, 12]},
            ok_substrings=[f"/{self.date_folder}/00z/", f"/{self.date_folder}/12z/"],
        )

        run = source.get_latest_available_run()

        self.assertEqual(run.hour, 12)
        self.assertEqual(run.date(), self.today)

    def test_falls_back_to_yesterday_when_today_unpublished(self):
        source = _make_source(
            config={"run_hours": [0, 12]},
            ok_substrings=["/20260814/12z/"],
        )

        run = source.get_latest_available_run()

        self.assertEqual(run.date(), self.today - timedelta(days=1))
        self.assertEqual(run.hour, 12)

    def test_no_fallback_when_disabled(self):
        source = _make_source(
            config={"run_hours": [0, 12], "allow_yesterday_fallback": False},
            ok_substrings=["/20260814/12z/"],
        )

        self.assertIsNone(source.get_latest_available_run())

    def test_generates_nothing_when_no_run_published(self):
        source = _make_source(config={"forecast_hours": [0, 6]}, ok_substrings=[])

        self.assertEqual(list(source.generate_requests()), [])

    def test_run_hours_outside_published_cycles_are_ignored(self):
        # 5z is not an ECMWF cycle: it must never be probed or selected,
        # even if a file happened to exist at that URL.
        source = _make_source(
            config={"run_hours": [5, 12]},
            ok_substrings=[f"/{self.date_folder}/05z/"],
        )

        self.assertIsNone(source.get_latest_available_run())
        self.assertNotIn(
            f"/{self.date_folder}/05z/",
            "".join(source._http.head_urls),
        )


class IFSGenerateRequestsTest(FrozenClockTestCase):
    def test_request_urls_follow_ifs_open_data_layout(self):
        source = _make_source(
            cls=ECMWFIFSDataSource,
            config={"forecast_hours": [0, 6], "run_hours": [0, 12]},
            ok_substrings=[f"/{self.date_folder}/12z/"],
        )

        requests_out = list(source.generate_requests())

        self.assertEqual(len(requests_out), 2)
        run_stamp = "20260815120000"
        self.assertEqual(
            requests_out[0].params["url"],
            "https://data.ecmwf.int/forecasts"
            "/20260815/12z/ifs/0p25/oper/20260815120000-0h-oper-fc.grib2",
        )
        self.assertEqual(
            requests_out[1].params["url"],
            "https://data.ecmwf.int/forecasts"
            "/20260815/12z/ifs/0p25/oper/20260815120000-6h-oper-fc.grib2",
        )
        self.assertEqual(requests_out[0].identifier, f"ifs-open-{run_stamp}-0h")
        self.assertEqual(requests_out[1].filename, f"ifs_{run_stamp}_6h_oper_fc.grib2")
        self.assertEqual(requests_out[1].expected_format, "grib")

    def test_off_cadence_and_out_of_range_steps_are_skipped(self):
        # 3h is a published oper step (3-hourly to 144h); 2h never is,
        # and steps outside 0..360h are dropped regardless of cadence.
        source = _make_source(
            cls=ECMWFIFSDataSource,
            config={"forecast_hours": [0, 2, 3, 6, 366, -6], "run_hours": [0]},
            ok_substrings=[f"/{self.date_folder}/00z/"],
        )

        steps = [r.params["step_hours"] for r in source.generate_requests()]

        self.assertEqual(steps, [0, 3, 6])

    def test_three_hourly_steps_are_valid_only_up_to_144h(self):
        # The portal's piecewise rule: 3-hourly to 144h, 6-hourly beyond.
        source = _make_source(
            cls=ECMWFIFSDataSource,
            config={
                "forecast_hours": [138, 141, 144, 147, 150, 153, 156],
                "run_hours": [0],
            },
            ok_substrings=[f"/{self.date_folder}/00z/"],
        )

        steps = [r.params["step_hours"] for r in source.generate_requests()]

        self.assertEqual(steps, [138, 141, 144, 150, 156])

    def test_aifs_cadence_is_unchanged_six_hourly(self):
        source = _make_source(
            config={"forecast_hours": [0, 3, 6], "run_hours": [0]},
            ok_substrings=[f"/{self.date_folder}/00z/"],
        )

        steps = [r.params["step_hours"] for r in source.generate_requests()]

        self.assertEqual(steps, [0, 6])

    def test_falls_back_to_yesterday_when_today_unpublished(self):
        source = _make_source(
            cls=ECMWFIFSDataSource,
            config={"forecast_hours": [0], "run_hours": [0, 12]},
            ok_substrings=["/20260814/12z/"],
        )

        (request,) = list(source.generate_requests())

        self.assertEqual(
            request.params["url"],
            "https://data.ecmwf.int/forecasts"
            "/20260814/12z/ifs/0p25/oper/20260814120000-0h-oper-fc.grib2",
        )


class IFSCycleRestrictionTest(FrozenClockTestCase):
    def test_only_00z_and_12z_cycles_are_considered(self):
        # 06z/18z belong to the scda stream, which oper does not serve to
        # 360h: they must never be probed, even when configured.
        source = _make_source(
            cls=ECMWFIFSDataSource,
            config={"run_hours": [0, 6, 12, 18]},
            ok_substrings=[f"/{self.date_folder}/18z/"],
        )

        self.assertIsNone(source.get_latest_available_run())
        probed = "".join(source._http.head_urls)
        self.assertNotIn("/06z/", probed)
        self.assertNotIn("/18z/", probed)

    def test_default_run_hours_are_00z_and_12z(self):
        source = _make_source(cls=ECMWFIFSDataSource)

        self.assertEqual(source.run_hours, [0, 12])


if __name__ == "__main__":
    unittest.main()
