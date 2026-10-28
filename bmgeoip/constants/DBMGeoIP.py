"""Bear & Moose GeoIP project constants."""

from typing import Final


class DBMGeoIP:
    VERSION: Final[str] = "1.4.1"
    CMDB_TYPE: Final[str] = "application"
    CMDB_SUBTYPE: Final[str] = "GeoIP Service"
    CMDB_SUPPLIER: Final[str] = "Nadim-Daniel"
    CMDB_CODENAME: Final[str] = "Holmium"
    BASE_DIR: Final[str] = "/opt/prod/bmgeoip"
    SERVICE_USER: Final[str] = "bmgeoip"
    SERVICE_UNIT: Final[str] = "bmgeoip-server.service"
    CMDB_COMPONENTS: Final[tuple[tuple[str, str], ...]] = (
        ("State", "/var/lib/bmgeoip"),
    )
    CMDB_DATABASES: Final[tuple[tuple[str, str], ...]] = (("BMGeoIP", "bmgeoip"),)
    CMDB_NETWORK: Final[tuple[tuple[str, str, int], ...]] = (
        ("http", "0.0.0.0", 54300),
        ("zmq", "0.0.0.0", 54301),
    )
    CONFIG_FILE: Final[str] = "conf/bmgeoip.json"
    REQUEST_TIMEOUT: Final[int] = 10
