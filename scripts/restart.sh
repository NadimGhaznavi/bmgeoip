#!/usr/bin/env bash
# Validate production settings before restarting both listeners.
set -euo pipefail
if [[ $# == 1 && $1 == --help ]]; then
    printf 'Usage: sudo scripts/restart.sh\nValidate configuration and restart BMGeoIP.\n'
    exit 0
fi
[[ $# == 0 && $EUID == 0 ]] || { printf 'Usage: sudo scripts/restart.sh\n' >&2; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

unit=$(python3 -B - <<'PY'
from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.interface.Network import Network

Network.binding('http')
Network.binding('zmq')
print(DBMGeoIP.SERVICE_UNIT)
PY
)
systemctl restart "$unit"
