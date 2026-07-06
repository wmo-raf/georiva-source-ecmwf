#!/bin/bash
set -euo pipefail
# Run by georiva when the plugin is built. No extra build steps required:
# this plugin's runtime dependencies (requests, django-timezone-field) are
# already provided by GeoRiva core.
