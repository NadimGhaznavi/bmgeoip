"""Bear & Moose GeoIP project constants."""

from typing import Final


class DBMGeoIP:
    VERSION: Final[str] = "0.0.0"
    BASE_DIR: Final[str] = "/opt/prod/bmgeoip"
    SERVICE_USER: Final[str] = "bmgeoip"
    SERVICE_HOME: Final[str] = "/var/lib/bmgeoip"
    SERVICE_UNIT: Final[str] = "bmgeoip-server.service"
    HOST: Final[str] = "0.0.0.0"
    PORT: Final[int] = 54300
    REQUEST_TIMEOUT: Final[int] = 10
