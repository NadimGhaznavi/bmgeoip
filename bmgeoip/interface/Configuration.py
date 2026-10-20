"""Create and resolve the production network configuration."""

from ipaddress import IPv4Address
import json
from pathlib import Path

from bmgeoip.constants.DBMGeoIP import DBMGeoIP


class Configuration:
    @staticmethod
    def read(path: Path, defaults: tuple[tuple[str, str, int], ...]) -> dict[str, tuple[str, int]]:
        bindings = {use: (interface, port) for use, interface, port in defaults}
        try:
            text = path.read_text()
        except FileNotFoundError:
            return bindings
        try:
            values = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(f'{path}: invalid JSON: {error}') from error
        if not isinstance(values, dict) or values.keys() - {'network'}:
            raise ValueError(f'{path}: expected an object containing only network settings.')
        network = values.get('network', {})
        if not isinstance(network, dict):
            raise ValueError(f'{path}: network must be an object.')
        for use, settings in network.items():
            field = f'{path}: network.{use}'
            if use not in bindings:
                raise ValueError(f'{field}: unknown network use.')
            if not isinstance(settings, dict) or settings.keys() - {'interface', 'port'}:
                raise ValueError(f'{field}: expected interface and/or port settings.')
            interface = settings.get('interface', bindings[use][0])
            port = settings.get('port', bindings[use][1])
            try:
                if not isinstance(interface, str):
                    raise ValueError('expected a string')
                IPv4Address(interface)
            except ValueError as error:
                raise ValueError(f'{field}.interface: expected an IPv4 address.') from error
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError(f'{field}.port: expected an integer between 1 and 65535.')
            bindings[use] = (interface, port)
        return bindings

    @staticmethod
    def install() -> None:
        path = Path(DBMGeoIP.BASE_DIR) / DBMGeoIP.CONFIG_FILE
        path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        values = {'network': {use: {'interface': interface, 'port': port}
                              for use, interface, port in DBMGeoIP.CMDB_NETWORK}}
        try:
            stream = path.open('x')
        except FileExistsError:
            pass
        else:
            with stream:
                stream.write(json.dumps(values, indent=2) + '\n')
            path.chmod(0o644)
        Configuration.read(path, DBMGeoIP.CMDB_NETWORK)
