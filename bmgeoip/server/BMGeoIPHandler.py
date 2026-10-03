"""Serve the Jinja2 web interface and HTTP health endpoints."""

from http.server import BaseHTTPRequestHandler
import json
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from bmgeoip.constants.DBMGeoIP import DBMGeoIP


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

    def serve(self) -> None:
        path = urlsplit(self.path).path
        if path == "/":
            body = TEMPLATES.get_template("home.html").render(version=DBMGeoIP.VERSION)
            self.respond(200, body.encode("utf-8"), "text/html; charset=utf-8")
        elif path in ("/health", "/ready"):
            status = "ok" if path == "/health" else "ready"
            body = json.dumps({"status": status, "service": "bmgeoip-server"}).encode()
            self.respond(200, body, "application/json")
        elif path == "/static/style.css":
            self.respond(200, (SERVER_DIR / "static/style.css").read_bytes(), "text/css; charset=utf-8")
        elif path == "/pages/images/bmgeoip.png":
            self.respond(200, (SERVER_DIR.parents[1] / "pages/images/bmgeoip.png").read_bytes(), "image/png")
        else:
            self.respond(404, b'{"error":"Not found."}', "application/json")

    def respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
