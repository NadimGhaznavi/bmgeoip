#!/usr/bin/env bash
# Reuse provisioning and deployment while retaining downloaded data and settings.
set -euo pipefail
if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/upgrade.sh\nDeploy BMGeoIP from this checkout, retaining CSVs, download settings, and logs.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Usage: sudo scripts/upgrade.sh\n' >&2; exit 1; }
exec "$(dirname -- "${BASH_SOURCE[0]}")/install.sh"
