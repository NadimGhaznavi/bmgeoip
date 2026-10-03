"""Validate lookup requests and own a database connection for each lookup."""

from ipaddress import ip_address
from pathlib import Path

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.DbMgr import DbMgr
from bmgeoip.interface.GeoIpDb import GeoIpDb


class GeoIpLookup:
    def __init__(self, database: Path = Path(DGeoIp.DATABASE_FILE)) -> None:
        self.database = Path(database)

    def lookup(self, value: str) -> dict:
        value = value.strip()
        if not value or len(value) > 45 or '%' in value:
            raise ValueError('Enter one IPv4 or IPv6 address without a network prefix or zone ID.')
        try:
            address = ip_address(value)
        except ValueError as error:
            raise ValueError('Enter a valid IPv4 or IPv6 address.') from error
        db = DbMgr(self.database, readonly=True)
        try:
            return {'ip': str(address), 'ip_version': address.version,
                    'results': GeoIpDb.lookup(db, address)}
        finally:
            db.close()
