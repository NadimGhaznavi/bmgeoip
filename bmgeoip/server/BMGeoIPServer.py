"""Run the BMGeoIP HTTP server."""

import argparse
from http.server import ThreadingHTTPServer
from ipaddress import ip_address
import signal

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.server.BMGeoIPHandler import BMGeoIPHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DBMGeoIP.HOST)
    parser.add_argument("--port", type=int, default=DBMGeoIP.PORT)
    args = parser.parse_args()
    try:
        address = ip_address(args.host)
    except ValueError:
        parser.error("--host must be an IPv4 address.")
    if address.version != 4:
        parser.error("--host must be an IPv4 address.")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")

    def stop(signum, frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, stop)
    try:
        with ThreadingHTTPServer((args.host, args.port), BMGeoIPHandler) as server:
            print(f"BMGeoIP: http://{args.host}:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        signal.signal(signal.SIGTERM, previous)
