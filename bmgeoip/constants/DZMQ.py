"""ZMQ envelope and transport settings."""

from typing import Final


class DZMQ:
    PROTOCOL_VERSION: Final[int] = 1
    TIMEOUT_SECONDS: Final[float] = 15.0
    POLL_MS: Final[int] = 100
