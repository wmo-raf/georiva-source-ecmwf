# Staged ECMWF GRIBs are index-selected subsets, not the published files

Status: accepted — implemented (issue #7): IFS feeds fetch index-selected subsets; AIFS still whole-file.

ECMWF open-data per-step GRIB2 files carry far more parameters/levels than a feed is configured for
(IFS files run to hundreds of MB). We fetch via the companion `.index` file: parse its JSON-lines
entries, select only the messages matching the feed's configured variables/levels, download them with
HTTP Range requests, and concatenate them into the staged `.grib2`. The staged object is therefore a
**valid GRIB2 but a subset of what the portal published** — comparing it to the source file will show
messages missing, and re-fetching history cannot recover messages that were never selected. We chose
bandwidth over archival completeness; when the `.index` is missing or unparseable, the fetch falls
back to the whole published file, so a staged object may be either shape.

## Consequences

- Downstream (extraction, COG writing) is unaffected: concatenated GRIB messages are a valid GRIB2 file.
- Widening a feed's variable set only affects runs fetched from then on; earlier staged files lack the new messages.
- AIFS feeds still fetch whole files (small); the strategy is available to them but not enabled.
