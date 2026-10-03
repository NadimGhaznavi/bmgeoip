"""Run the BMGeoIP HTTP server and ZMQ lookup worker."""

import argparse
from http.server import ThreadingHTTPServer
from ipaddress import ip_address
import logging
from pathlib import Path
import signal

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.activity.DataLoader import DataLoader
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from bmgeoip.interface.GeoIpLookup import GeoIpLookup
from bmgeoip.server.BMGeoIPHandler import BMGeoIPHandler
from bmgeoip.server.LookupHandler import LookupHandler
from bmgeoip.zmq.ZMQServer import ZMQServer


class BMGeoIPServer(ThreadingHTTPServer):
    def service_actions(self) -> None:
        self.lookup_worker.check()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DBMGeoIP.HOST)
    parser.add_argument("--port", type=int, default=DBMGeoIP.PORT)
    parser.add_argument("--zmq-endpoint", default=DBMGeoIP.ZMQ_ENDPOINT)
    parser.add_argument("--state-dir", type=Path, default=Path(DBMGeoIP.SERVICE_HOME))
    parser.add_argument('--database-env', type=Path, default=Path(DGeoIp.DATABASE_ENV))
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
        with BMGeoIPServer((args.host, args.port), BMGeoIPHandler) as server, ZMQServer(
                args.zmq_endpoint, LookupHandler(GeoIpLookup(args.database_env))) as worker:
            server.lookup_worker = worker
            server.data_loader = DataLoader(
                DownloadSchedule(args.state_dir / 'download-schedule.json', args.state_dir / 'data'),
                args.database_env, args.state_dir / 'data-status.json')
            messages = server.data_loader.status_messages
            messages.append(f'BMGeoIP {DBMGeoIP.VERSION} starting.')
            try:
                schedule = server.data_loader.schedule.read()
            except (OSError, ValueError):
                logging.exception('Could not read CSV download schedule at startup')
                messages.append('CSV download schedule unavailable. Check the service log.')
            else:
                messages.append(f"CSV download schedule: {'enabled' if schedule['enabled'] else 'disabled'}; {schedule['expression']}.")
            messages.append(f'HTTP listener ready on {args.host}:{server.server_port}.')
            messages.append(f'ZMQ lookup listener ready on {worker.endpoint}.')
            server.data_loader.start()
            print(f"BMGeoIP: http://{args.host}:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                messages.append('HTTP server stopping.')
    finally:
        signal.signal(signal.SIGTERM, previous)
