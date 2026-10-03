"""Dispatch ZMQ lookup requests through the shared lookup interface."""

import logging
import pymysql

from bmgeoip.interface.GeoIpLookup import GeoIpLookup
from bmgeoip.zmq.ZMQMsg import ZMQMsg


class LookupHandler:
    def __init__(self, lookup: GeoIpLookup) -> None:
        self.lookup = lookup

    def __call__(self, request: ZMQMsg) -> dict:
        if request.target not in (None, 'bmgeoip'):
            return self.error('invalid_request', 'target must be bmgeoip or null.')
        if request.method != 'lookup':
            return self.error('invalid_request', 'method must be lookup.')
        if set(request.payload) != {'ip'} or not isinstance(request.payload['ip'], str):
            return self.error('invalid_request', 'Provide one ip string in payload.')
        try:
            result = self.lookup.lookup(request.payload['ip'])
        except ValueError as error:
            return self.error('invalid_request', str(error))
        except LookupError as error:
            return self.error('data_unavailable', str(error))
        except (OSError, pymysql.OperationalError, pymysql.ProgrammingError):
            logging.exception('ZMQ GeoIP lookup data is unavailable')
            return self.error('data_unavailable', 'Lookup data is unavailable. Check Dataset Status and the service log.')
        return {'status': 'ok', **result}

    @staticmethod
    def error(code: str, message: str) -> dict:
        return {'status': 'error', 'error': {'code': code, 'message': message}}
