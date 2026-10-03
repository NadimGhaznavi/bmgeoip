"""Public GeoIP CSV provider defaults."""

from typing import Final


class DGeoIp:
    URL: Final[str] = "https://raw.githubusercontent.com/ipapi-is/ipapi/main/databases/geolocationDatabaseIPv{version}.csv.zip"
    MEMBER: Final[str] = "geolocationDatabaseIPv{version}.csv"
    VERSIONS: Final[tuple[int, ...]] = (4, 6)
    DOWNLOAD_TIMEOUT: Final[int] = 120
    COLUMNS: Final[tuple[str, ...]] = (
        "ip_version", "start_ip", "end_ip", "continent", "country_code", "country",
        "state", "city", "zip", "timezone", "latitude", "longitude", "accuracy", "source",
    )
