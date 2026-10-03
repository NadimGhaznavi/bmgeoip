"""Public GeoIP CSV provider defaults."""

from typing import Final

from bmgeoip.constants.DBMGeoIP import DBMGeoIP


class DGeoIp:
    DATA_DIR: Final[str] = DBMGeoIP.SERVICE_HOME + "/data"
    SCHEDULE_FILE: Final[str] = DBMGeoIP.SERVICE_HOME + "/download-schedule.json"
    DATABASE_FILE: Final[str] = DBMGeoIP.SERVICE_HOME + "/geoip.sqlite3"
    STATUS_FILE: Final[str] = DBMGeoIP.SERVICE_HOME + "/data-status.json"
    DOWNLOAD_CRON: Final[str] = "0 3 * * 0"
    URL: Final[str] = "https://raw.githubusercontent.com/ipapi-is/ipapi/main/databases/geolocationDatabaseIPv{version}.csv.zip"
    MEMBER: Final[str] = "geolocationDatabaseIPv{version}.csv"
    VERSIONS: Final[tuple[int, ...]] = (4, 6)
    DOWNLOAD_TIMEOUT: Final[int] = 120
    COLUMNS: Final[tuple[str, ...]] = (
        "ip_version", "start_ip", "end_ip", "continent", "country_code", "country",
        "state", "city", "zip", "timezone", "latitude", "longitude", "accuracy", "source",
    )
