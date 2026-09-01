"""
Tests for index-selected fetching (plugin ADR 0001).

Two seams, both network-free:

- the pure selection function, exercised against a committed ``.index``
  fixture captured from the live portal (20260831 00z IFS oper, step 6);
- ``ECMWFIndexedHTTPFetchStrategy`` with HTTP stubbed at the session
  boundary: Range headers issued, byte concatenation written, and the
  whole-file fallback on a missing/corrupt index or failed range request.
"""

import unittest
from pathlib import Path
from unittest import mock

import requests

from georiva.sources.fetch import FileRequest
from georiva_source_ecmwf.index_fetch import (
    ECMWFIndexedHTTPFetchStrategy,
    index_url_for,
    parse_index_entries,
    select_byte_ranges,
)

FIXTURE = Path(__file__).parent / "fixtures" / "20260831000000-6h-oper-fc.index"


def fixture_entries():
    return parse_index_entries(FIXTURE.read_text())


class ParseIndexEntriesTest(unittest.TestCase):
    def test_parses_every_json_line_of_the_live_fixture(self):
        entries = fixture_entries()

        self.assertEqual(len(entries), 184)
        first = entries[0]
        self.assertEqual(first["param"], "tp")
        self.assertEqual(first["levtype"], "sfc")
        self.assertEqual(first["_offset"], 0)
        self.assertEqual(first["_length"], 688049)

    def test_blank_lines_are_skipped(self):
        text = '{"levtype": "sfc", "param": "2t", "_offset": 0, "_length": 10}\n\n'

        self.assertEqual(len(parse_index_entries(text)), 1)

    def test_garbage_line_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_index_entries("<html>not an index</html>")


class SelectByteRangesTest(unittest.TestCase):
    def test_surface_selector_matches_param_only_entries(self):
        ranges = select_byte_ranges(
            fixture_entries(),
            [{"levtype": "sfc", "params": ["tp", "sp", "2t"]}],
        )

        self.assertEqual(
            ranges,
            [(0, 688049), (1534105, 538743), (18889259, 650266)],
        )

    def test_pressure_selector_needs_levelist_match(self):
        ranges = select_byte_ranges(
            fixture_entries(),
            [{"levtype": "pl", "params": ["t", "z"], "levels": [500, 1000]}],
        )

        self.assertEqual(len(ranges), 4)  # 2 params x 2 levels
        self.assertIn((101650093, 616115), ranges)  # t @ 500
        self.assertIn((16948998, 1096446), ranges)  # z @ 1000

    def test_shared_core_selection_counts(self):
        # The IFS feed's configured shape: 6 surface params + 5 pressure
        # params at 9 levels.
        selectors = [
            {"levtype": "sfc", "params": ["2t", "10u", "10v", "msl", "tp", "sp"]},
            {
                "levtype": "pl",
                "params": ["t", "u", "v", "z", "q"],
                "levels": [1000, 925, 850, 700, 500, 300, 250, 200, 50],
            },
        ]

        ranges = select_byte_ranges(fixture_entries(), selectors)

        self.assertEqual(len(ranges), 6 + 5 * 9)

    def test_no_match_returns_empty_list(self):
        selectors = [{"levtype": "sfc", "params": ["nosuchparam"]}]

        self.assertEqual(select_byte_ranges(fixture_entries(), selectors), [])

    def test_surface_selector_does_not_match_levelled_entries(self):
        # "sot" exists only at levtype "sol" with a levelist; a surface
        # selector for it must not pick it up.
        selectors = [{"levtype": "sfc", "params": ["sot"]}]

        self.assertEqual(select_byte_ranges(fixture_entries(), selectors), [])

    def test_ranges_come_back_sorted_by_offset(self):
        entries = [
            {"levtype": "sfc", "param": "b", "_offset": 100, "_length": 10},
            {"levtype": "sfc", "param": "a", "_offset": 0, "_length": 10},
        ]

        ranges = select_byte_ranges(entries, [{"levtype": "sfc", "params": ["a", "b"]}])

        self.assertEqual(ranges, [(0, 10), (100, 10)])


class IndexUrlTest(unittest.TestCase):
    def test_derives_index_url_from_grib_url(self):
        self.assertEqual(
            index_url_for("https://x/20260831000000-6h-oper-fc.grib2"),
            "https://x/20260831000000-6h-oper-fc.index",
        )

    def test_non_grib2_url_has_no_index(self):
        self.assertIsNone(index_url_for("https://x/file.nc"))


# ---------------------------------------------------------------------------
# Strategy tests: HTTP stubbed at the session boundary
# ---------------------------------------------------------------------------

GRIB_URL = "https://portal/x/20260831000000-6h-oper-fc.grib2"
INDEX_URL = "https://portal/x/20260831000000-6h-oper-fc.index"

# A fake published file: 200 bytes, with three "messages" the index knows.
WHOLE_FILE = bytes(i % 256 for i in range(200))
INDEX_TEXT = "\n".join(
    [
        '{"levtype": "sfc", "param": "2t", "_offset": 10, "_length": 20}',
        '{"levtype": "sfc", "param": "xx", "_offset": 30, "_length": 5}',
        '{"levtype": "pl", "param": "t", "levelist": "500", "_offset": 100, "_length": 50}',
    ]
)


class _FakeResponse:
    def __init__(self, status_code=200, body=b"", text=None):
        self.status_code = status_code
        self.content = body
        self.text = text if text is not None else body.decode("latin-1")
        self.headers = {"content-length": str(len(body))} if body else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]


class _FakeSession:
    """Serves the fake portal: index text, Range slices, whole file."""

    def __init__(self, index_response=None, range_status=206):
        self.index_response = index_response or _FakeResponse(text=INDEX_TEXT)
        self.range_status = range_status
        self.calls = []  # (url, range-header-or-None)

    def get(self, url, headers=None, stream=False, timeout=None):
        range_header = (headers or {}).get("Range")
        self.calls.append((url, range_header))

        if url == INDEX_URL:
            return self.index_response

        if range_header:
            start, end = map(int, range_header.removeprefix("bytes=").split("-"))
            return _FakeResponse(self.range_status, WHOLE_FILE[start : end + 1])

        return _FakeResponse(200, WHOLE_FILE)


def _request(selectors):
    params = {"url": GRIB_URL}
    if selectors is not None:
        params["index_selectors"] = selectors
    return FileRequest(identifier="r", filename="f.grib2", params=params)


def _strategy(session):
    strategy = ECMWFIndexedHTTPFetchStrategy()
    strategy._session = session
    return strategy


SELECTORS = [
    {"levtype": "sfc", "params": ["2t"]},
    {"levtype": "pl", "params": ["t"], "levels": [500]},
]


class IndexedFetchTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local_path = Path(self.tmp.name) / "out.grib2"

    def test_writes_the_selected_byte_concatenation(self):
        session = _FakeSession()

        result = _strategy(session).fetch(_request(SELECTORS), self.local_path)

        self.assertTrue(result.success)
        expected = WHOLE_FILE[10:30] + WHOLE_FILE[100:150]
        self.assertEqual(self.local_path.read_bytes(), expected)
        self.assertEqual(result.bytes_transferred, len(expected))

    def test_issues_range_headers_for_selected_messages_only(self):
        session = _FakeSession()

        _strategy(session).fetch(_request(SELECTORS), self.local_path)

        range_headers = [rng for url, rng in session.calls if rng]
        self.assertEqual(range_headers, ["bytes=10-29", "bytes=100-149"])
        # And the whole file was never downloaded.
        self.assertNotIn((GRIB_URL, None), session.calls)

    def test_adjacent_ranges_are_coalesced_into_one_request(self):
        selectors = [{"levtype": "sfc", "params": ["2t", "xx"]}]
        session = _FakeSession()

        result = _strategy(session).fetch(_request(selectors), self.local_path)

        range_headers = [rng for url, rng in session.calls if rng]
        self.assertEqual(range_headers, ["bytes=10-34"])
        self.assertTrue(result.success)
        self.assertEqual(self.local_path.read_bytes(), WHOLE_FILE[10:35])

    def test_without_selectors_falls_through_to_plain_download(self):
        session = _FakeSession()

        result = _strategy(session).fetch(_request(None), self.local_path)

        self.assertTrue(result.success)
        self.assertEqual(self.local_path.read_bytes(), WHOLE_FILE)
        self.assertNotIn(INDEX_URL, [url for url, _ in session.calls])

    def test_missing_index_falls_back_to_whole_file_with_warning(self):
        session = _FakeSession(index_response=_FakeResponse(404))

        with self.assertLogs("georiva.fetch", level="WARNING") as logs:
            result = _strategy(session).fetch(_request(SELECTORS), self.local_path)

        self.assertTrue(result.success)
        self.assertEqual(self.local_path.read_bytes(), WHOLE_FILE)
        self.assertTrue(any("whole file" in m for m in logs.output))

    def test_corrupt_index_falls_back_to_whole_file(self):
        session = _FakeSession(index_response=_FakeResponse(text="<html>nope</html>"))

        with self.assertLogs("georiva.fetch", level="WARNING"):
            result = _strategy(session).fetch(_request(SELECTORS), self.local_path)

        self.assertTrue(result.success)
        self.assertEqual(self.local_path.read_bytes(), WHOLE_FILE)

    def test_no_matching_messages_falls_back_to_whole_file(self):
        selectors = [{"levtype": "sfc", "params": ["nosuchparam"]}]
        session = _FakeSession()

        with self.assertLogs("georiva.fetch", level="WARNING"):
            result = _strategy(session).fetch(_request(selectors), self.local_path)

        self.assertTrue(result.success)
        self.assertEqual(self.local_path.read_bytes(), WHOLE_FILE)

    def test_failed_range_request_falls_back_to_whole_file(self):
        # A server that ignores Range (200) means we cannot trust slices.
        session = _FakeSession(range_status=200)

        with self.assertLogs("georiva.fetch", level="WARNING"):
            result = _strategy(session).fetch(_request(SELECTORS), self.local_path)

        self.assertTrue(result.success)
        self.assertEqual(self.local_path.read_bytes(), WHOLE_FILE)


class SourceWiringTest(unittest.TestCase):
    """The IFS source derives selectors; AIFS stays on plain HTTP."""

    def _requests_for(self, cls, config=None):
        from datetime import datetime, timezone

        source = cls(config or {"forecast_hours": [0], "run_hours": [0]})
        with mock.patch.object(source, "get_latest_available_run") as latest:
            latest.return_value = datetime(2026, 8, 31, tzinfo=timezone.utc)
            return list(source.generate_requests())

    def test_ifs_requests_carry_shared_core_and_ifs_only_selectors(self):
        from georiva_source_ecmwf.source import ECMWFIFSDataSource

        (request,) = self._requests_for(ECMWFIFSDataSource)

        selectors = request.params["index_selectors"]
        self.assertEqual(
            selectors[0],
            {
                "levtype": "sfc",
                "params": [
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
                ],
            },
        )
        self.assertEqual(selectors[1]["levtype"], "pl")
        self.assertEqual(selectors[1]["params"], ["t", "u", "v", "z", "q"])
        self.assertEqual(
            selectors[1]["levels"],
            [1000, 925, 850, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50],
        )

    def test_default_ifs_selectors_resolve_against_the_live_index_fixture(self):
        # Every configured surface param and every (param, level) pair must
        # name a real message in the captured portal index — otherwise a
        # variable would silently never be staged (ADR 0001).
        from georiva_source_ecmwf.source import ECMWFIFSDataSource

        source = ECMWFIFSDataSource({})
        selectors = source.index_selectors(source.default_variables())
        entries = fixture_entries()

        for param in selectors[0]["params"]:
            with self.subTest(param=param):
                matched = select_byte_ranges(
                    entries, [{"levtype": "sfc", "params": [param]}]
                )
                self.assertEqual(len(matched), 1)

        for param in selectors[1]["params"]:
            for level in selectors[1]["levels"]:
                with self.subTest(param=param, level=level):
                    matched = select_byte_ranges(
                        entries,
                        [{"levtype": "pl", "params": [param], "levels": [level]}],
                    )
                    self.assertEqual(len(matched), 1)

    def test_unknown_requested_variable_is_dropped_with_warning(self):
        from georiva_source_ecmwf.source import ECMWFIFSDataSource

        source = ECMWFIFSDataSource(
            {"forecast_hours": [0], "run_hours": [0], "variables": ["2t", "bogus"]}
        )

        with self.assertLogs("georiva.datasource.ecmwf-ifs", level="WARNING") as logs:
            selectors = source.index_selectors(source.requested_variables)

        self.assertEqual(selectors[0], {"levtype": "sfc", "params": ["2t"]})
        self.assertTrue(any("bogus" in m for m in logs.output))

    def test_ifs_uses_the_indexed_strategy(self):
        from georiva_source_ecmwf.source import ECMWFIFSDataSource

        source = ECMWFIFSDataSource({})

        self.assertIs(source.fetch_strategy, ECMWFIndexedHTTPFetchStrategy)

    def test_aifs_requests_and_strategy_are_unchanged(self):
        from georiva.sources.fetch import HTTPFetchStrategy
        from georiva_source_ecmwf.source import ECMWFAIFSDataSource

        source = ECMWFAIFSDataSource({})
        self.assertIs(source.fetch_strategy, HTTPFetchStrategy)

        (request,) = self._requests_for(
            ECMWFAIFSDataSource, {"forecast_hours": [0], "run_hours": [0]}
        )
        self.assertNotIn("index_selectors", request.params)


if __name__ == "__main__":
    unittest.main()
