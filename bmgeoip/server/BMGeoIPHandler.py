"""Serve the Jinja2 web interface and HTTP health endpoints."""

from http.server import BaseHTTPRequestHandler
import json
import logging
import pymysql
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from bmgeoip.constants.DBMGeoIP import DBMGeoIP
from bmgeoip.activity.DataLoader import DataLoader
from bmgeoip.interface.DownloadSchedule import DownloadSchedule
from bmgeoip.interface.StatusMessages import StatusMessages
from bmgeoip.interface.GeoIpLookup import GeoIpLookup


SERVER_DIR = Path(__file__).resolve().parent
TEMPLATES = Environment(
    loader=FileSystemLoader(SERVER_DIR / "templates"),
    autoescape=select_autoescape(("html", "xml")),
    undefined=StrictUndefined,
)


class BMGeoIPHandler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(DBMGeoIP.REQUEST_TIMEOUT)

    def do_GET(self) -> None:
        self.serve()

    def do_HEAD(self) -> None:
        self.serve()

    def do_POST(self) -> None:
        if urlsplit(self.path).path != '/api/download-schedule':
            self.respond(404, b'{"error":"Not found."}', 'application/json')
            return
        origin = self.headers.get('Origin')
        if origin and (urlsplit(origin).scheme not in ('http', 'https')
                       or urlsplit(origin).netloc != self.headers.get('Host')):
            self.respond(403, b'{"error":"Use the BMGeoIP website to save settings."}', 'application/json')
            return
        try:
            if self.headers.get('Content-Type') != 'application/json':
                raise ValueError('Send schedule settings as application/json.')
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Provide Content-Length.')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Schedule request must be between 1 and 4096 bytes.')
            values = json.loads(self.rfile.read(length))
            if not isinstance(values, dict) or set(values) != {'enabled', 'expression'}:
                raise ValueError('Provide enabled and expression settings.')
            schedule = self.downloads().update(**values)
        except (ValueError, UnicodeError) as error:
            self.respond(400, json.dumps({'error': str(error)}).encode(), 'application/json')
            return
        except (OSError, RuntimeError):
            logging.exception('Could not save CSV download schedule')
            self.messages().append('Could not save CSV download schedule. Check the service log and retry.')
            self.respond(503, b'{"error":"Could not save the schedule and cron entry. Check the service log and retry."}', 'application/json')
            return
        self.messages().append(f"CSV download schedule saved: {'enabled' if schedule['enabled'] else 'disabled'}; {schedule['expression']}.")
        self.respond(200, json.dumps({'schedule': schedule}).encode(), 'application/json')

    def serve(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            try:
                downloads = self.downloads()
                body = TEMPLATES.get_template("home.html").render(
                    version=DBMGeoIP.VERSION, schedule=downloads.read(), files=downloads.files())
            except (OSError, ValueError):
                logging.exception('Could not load download settings')
                self.respond(503, b'{"error":"Download settings are unavailable. Check the service log."}', 'application/json')
                return
            self.respond(200, body.encode("utf-8"), "text/html; charset=utf-8")
        elif path == '/status-messages':
            try:
                values = self.messages().snapshot()
            except (OSError, ValueError):
                logging.exception('Could not read status messages')
                self.respond(503, b'{"error":"Status messages are unavailable. Check the service log."}', 'application/json')
                return
            self.respond(200, json.dumps(values).encode(), 'application/json')
        elif path == '/api/lookup':
            try:
                query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(query) != {'ip'} or len(query['ip']) != 1:
                    raise ValueError('Provide one ip query parameter.')
                loader = getattr(self.server, 'data_loader', None)
                lookup = GeoIpLookup(loader.database) if loader is not None else GeoIpLookup()
                values = lookup.lookup(query['ip'][0])
            except ValueError as error:
                self.respond(400, json.dumps({'error': str(error)}).encode(), 'application/json')
                return
            except LookupError as error:
                self.respond(503, json.dumps({'error': str(error)}).encode(), 'application/json')
                return
            except (OSError, pymysql.OperationalError, pymysql.ProgrammingError):
                logging.exception('GeoIP lookup data is unavailable')
                self.respond(503, b'{"error":"Lookup data is unavailable. Check Dataset Status and the service log."}', 'application/json')
                return
            self.respond(200, json.dumps(values).encode(), 'application/json')
        elif path == '/api/data-status':
            try:
                loader = getattr(self.server, 'data_loader', None)
                values = (loader if loader is not None else DataLoader()).read()
            except (OSError, ValueError):
                logging.exception('Could not read dataset progress')
                self.respond(503, b'{"error":"Dataset progress is unavailable. Check the service log."}', 'application/json')
                return
            self.respond(200, json.dumps(values).encode(), 'application/json')
        elif path in ("/health", "/ready"):
            status = "ok" if path == "/health" else "ready"
            body = json.dumps({"status": status, "service": "bmgeoip-server"}).encode()
            self.respond(200, body, "application/json")
        elif path == "/static/style.css":
            self.respond(200, (SERVER_DIR / "static/style.css").read_bytes(), "text/css; charset=utf-8")
        elif path in ("/static/downloads.js", "/static/status_messages.js", "/static/lookup.js"):
            self.respond(200, (SERVER_DIR / path.lstrip("/")).read_bytes(), "text/javascript; charset=utf-8")
        elif path == "/pages/images/bmgeoip.png":
            self.respond(200, (SERVER_DIR.parents[1] / "pages/images/bmgeoip.png").read_bytes(), "image/png")
        else:
            self.respond(404, b'{"error":"Not found."}', "application/json")

    def messages(self) -> StatusMessages:
        loader = getattr(self.server, 'data_loader', None)
        return loader.status_messages if loader is not None else StatusMessages()

    def downloads(self) -> DownloadSchedule:
        loader = getattr(self.server, 'data_loader', None)
        return loader.schedule if loader is not None else DownloadSchedule()

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
