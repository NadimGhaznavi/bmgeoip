"""Retrieve and validate upstream CSV data independently of lookup storage."""

from collections.abc import Iterator
import csv
from ipaddress import ip_address
import math
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit
from urllib.request import urlopen
from zipfile import ZipFile

from bmgeoip.constants.DGeoIp import DGeoIp


class GeoIpSource:
    def __init__(self, url: str = DGeoIp.URL, member: str = DGeoIp.MEMBER,
                 timeout: float = DGeoIp.DOWNLOAD_TIMEOUT) -> None:
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Download timeout must be finite and positive.")
        for version in DGeoIp.VERSIONS:
            address = urlsplit(url.format(version=version))
            if address.scheme not in ("http", "https") or not address.hostname:
                raise ValueError("GeoIP URL must be an HTTP(S) URL.")
            if not member.format(version=version):
                raise ValueError("GeoIP archive member must not be empty.")
        self._url = url
        self._member = member
        self._timeout = timeout

    def download(self, version: int, destination: Path, progress=None) -> None:
        """Atomically replace destination with a fully validated UTF-8 CSV."""
        self._validate_version(version)
        destination = Path(destination)
        # Staging beside the destination keeps the final rename on one filesystem.
        with TemporaryDirectory(prefix=".bmgeoip-", dir=destination.parent) as directory:
            archive = Path(directory) / "source.zip"
            with urlopen(self._url.format(version=version), timeout=self._timeout) as response:
                length = response.headers.get('Content-Length') if hasattr(response, 'headers') else None
                total = int(length) if length and length.isdigit() else None
                received = 0
                with archive.open("wb") as output:
                    while chunk := response.read(1024 * 1024):
                        output.write(chunk)
                        received += len(chunk)
                        if progress:
                            progress('downloading', received, total)
                if total is not None and received != total:
                    raise OSError('Incomplete GeoIP archive download.')
            candidate = Path(directory) / "source.csv"
            if progress:
                progress('extracting', 0, None)
            with ZipFile(archive) as zipped:
                with zipped.open(self._member.format(version=version)) as stream:
                    with candidate.open("wb") as output:
                        shutil.copyfileobj(stream, output)
            if progress:
                progress('validating', 0, None)
            for count, row in enumerate(self.rows(candidate, version), 1):
                if progress and count % 1000 == 0:
                    progress('validating', count, None)
            candidate.replace(destination)

    def rows(self, source: Path, version: int) -> Iterator[dict[str, str]]:
        """Yield validated CSV rows, preserving all fourteen fields as text."""
        self._validate_version(version)
        with Path(source).open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            if reader.fieldnames != list(DGeoIp.COLUMNS):
                raise ValueError("Unexpected GeoIP CSV header.")
            count = 0
            for row in reader:
                line = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"Incomplete GeoIP row at line {line}.")
                start, end = ip_address(row["start_ip"]), ip_address(row["end_ip"])
                if (row["ip_version"] != str(version) or start.version != version
                        or end.version != version or int(start) > int(end)):
                    raise ValueError(f"Invalid GeoIP range at line {line}.")
                for field, limit in (("latitude", 90), ("longitude", 180)):
                    if row[field].strip():
                        try:
                            value = float(row[field])
                        except ValueError as error:
                            raise ValueError(f"Invalid GeoIP {field} at line {line}.") from error
                        if not -limit <= value <= limit:
                            raise ValueError(f"Invalid GeoIP {field} at line {line}.")
                count += 1
                yield row
            if count == 0:
                raise ValueError(f"The IPv{version} database is empty.")

    @staticmethod
    def _validate_version(version: int) -> None:
        if type(version) is not int or version not in DGeoIp.VERSIONS:
            raise ValueError("IP version must be 4 or 6.")
