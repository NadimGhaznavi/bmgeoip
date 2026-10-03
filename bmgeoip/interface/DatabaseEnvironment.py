"""Read MariaDB connection settings as data, never as shell code."""

from pathlib import Path


class DatabaseEnvironment:
    @staticmethod
    def read(path: Path) -> dict[str, str]:
        values = {}
        for line in Path(path).read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator or key in values:
                raise ValueError('Invalid database environment file.')
            values[key] = value
        DatabaseEnvironment.validate(values)
        return values

    @staticmethod
    def validate(values: dict[str, str]) -> None:
        required = {'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD'}
        if not required <= values.keys() or values.keys() - required - {'DB_SOCKET'}:
            raise ValueError('Unexpected database environment fields.')
        if any(not isinstance(value, str) for value in values.values()):
            raise ValueError('Database settings must be text.')
        if any(not values[key] for key in required - {'DB_PASSWORD'}):
            raise ValueError('Missing database connection settings.')
        try:
            port = int(values['DB_PORT'])
        except ValueError as error:
            raise ValueError('DB_PORT must be an integer between 1 and 65535.') from error
        if not 1 <= port <= 65535:
            raise ValueError('DB_PORT must be between 1 and 65535.')
