"""
Index-selected fetching for ECMWF Open Data GRIBs (plugin ADR 0001).

Every published ``.grib2`` has a companion ``.index``: JSON-lines, one
entry per GRIB message, each carrying ``_offset``/``_length`` byte
coordinates plus MARS-style keys (``levtype``, ``param``, and — for
levelled entries — ``levelist``). We select only the messages a feed is
configured for and download them with HTTP Range requests; concatenated
GRIB messages are themselves a valid GRIB2 file.

The staged object is therefore a subset of what the portal published.
When the index is missing/unparseable, nothing matches, or a range
request fails, the strategy falls back to the whole published file with
a logged warning — so a staged object may be either shape.
"""

import json
import time
from pathlib import Path

import requests

from georiva.sources.fetch import FetchResult, FileRequest, HTTPFetchStrategy


def parse_index_entries(text: str) -> list[dict]:
    """
    Parse a ``.index`` body (JSON lines) into entry dicts.

    Blank lines are skipped; any non-JSON line raises ValueError — a
    partially readable index cannot be trusted for byte arithmetic.
    """
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"Unparseable index line: {line[:80]!r}") from e
        if not isinstance(entry, dict):
            raise ValueError(f"Index line is not an object: {line[:80]!r}")
        entries.append(entry)
    return entries


def select_byte_ranges(
    entries: list[dict], selectors: list[dict]
) -> list[tuple[int, int]]:
    """
    Pure selection: index entries + selectors -> sorted (offset, length).

    A selector is a JSON-safe dict:
        {"levtype": "sfc", "params": [...]}                    # surface
        {"levtype": "pl", "params": [...], "levels": [...]}    # pressure

    An entry matches when its ``levtype`` and ``param`` match and — for a
    selector carrying ``levels`` — its ``levelist`` names one of them.
    A surface selector never matches a levelled entry.
    """
    ranges = []
    for entry in entries:
        if any(_matches(entry, selector) for selector in selectors):
            ranges.append((int(entry["_offset"]), int(entry["_length"])))
    return sorted(ranges)


def _matches(entry: dict, selector: dict) -> bool:
    if entry.get("levtype") != selector["levtype"]:
        return False
    if entry.get("param") not in selector["params"]:
        return False
    levels = selector.get("levels")
    if levels is None:
        # A plain-surface selector must not swallow levelled entries.
        return "levelist" not in entry
    return entry.get("levelist") in {str(level) for level in levels}


def index_url_for(grib_url: str) -> str | None:
    """The companion ``.index`` URL for a portal ``.grib2`` URL."""
    if not grib_url.endswith(".grib2"):
        return None
    return grib_url.removesuffix(".grib2") + ".index"


def coalesce_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge byte-adjacent (offset, length) pairs into single ranges."""
    merged: list[list[int]] = []
    for offset, length in sorted(ranges):
        if merged and merged[-1][0] + merged[-1][1] == offset:
            merged[-1][1] += length
        else:
            merged.append([offset, length])
    return [(offset, length) for offset, length in merged]


class ECMWFIndexedHTTPFetchStrategy(HTTPFetchStrategy):
    """
    HTTP fetch that stages an index-selected subset of the published GRIB.

    Reads selectors from ``request.params["index_selectors"]`` (placed
    there by the source); without them it behaves exactly like the plain
    HTTP strategy. On any index or range trouble it falls back to the
    whole published file, so a fetch never fails because of selection.
    """

    type = "ecmwf-indexed-http"
    label = "ECMWF Open Data indexed HTTP"

    def fetch(self, request: FileRequest, local_path: Path) -> FetchResult:
        selectors = request.params.get("index_selectors")
        url = request.params.get("url")
        index_url = index_url_for(url) if url else None

        if not selectors or not index_url:
            return super().fetch(request, local_path)

        try:
            ranges = self._select_ranges(index_url, selectors)
        except (requests.RequestException, ValueError, KeyError, TypeError) as e:
            return self._fall_back(request, local_path, f"index unusable ({e})")

        if not ranges:
            return self._fall_back(
                request, local_path, "no index entries matched the selectors"
            )

        try:
            return self._fetch_ranges(request, local_path, url, ranges)
        except (requests.RequestException, OSError) as e:
            if local_path.exists():
                local_path.unlink()
            return self._fall_back(request, local_path, f"range request failed ({e})")

    # ------------------------------------------------------------------

    def _select_ranges(
        self, index_url: str, selectors: list[dict]
    ) -> list[tuple[int, int]]:
        response = self._session.get(
            index_url, timeout=(self.connect_timeout, self.timeout)
        )
        response.raise_for_status()
        entries = parse_index_entries(response.text)
        return select_byte_ranges(entries, selectors)

    def _fetch_ranges(
        self,
        request: FileRequest,
        local_path: Path,
        url: str,
        ranges: list[tuple[int, int]],
    ) -> FetchResult:
        result = FetchResult(request=request, local_path=local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        start_time = time.time()
        bytes_downloaded = 0

        with open(local_path, "wb") as f:
            for offset, length in coalesce_ranges(ranges):
                response = self._session.get(
                    url,
                    headers={"Range": f"bytes={offset}-{offset + length - 1}"},
                    stream=True,
                    timeout=(self.connect_timeout, self.timeout),
                )
                response.raise_for_status()
                if response.status_code != 206:
                    # The server ignored Range: the body is not our slice.
                    raise requests.exceptions.RequestException(
                        f"expected 206 Partial Content, got {response.status_code}"
                    )
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if chunk:
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

        result.success = True
        result.status = "complete"
        result.bytes_transferred = bytes_downloaded
        result.duration_seconds = time.time() - start_time
        self.logger.debug(
            f"Staged {len(ranges)} index-selected messages "
            f"({bytes_downloaded / 1024 / 1024:.1f} MB) from {url}"
        )
        return result

    def _fall_back(
        self, request: FileRequest, local_path: Path, reason: str
    ) -> FetchResult:
        self.logger.warning(
            f"Index-selected fetch unavailable for "
            f"{request.params.get('url')}: {reason}; "
            f"falling back to the whole file"
        )
        return super().fetch(request, local_path)
