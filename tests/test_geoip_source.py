"""Verify CSV retrieval and preservation of existing data on failure."""

import csv
from io import BytesIO, StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from zipfile import BadZipFile, ZipFile

from bmgeoip.constants.DGeoIp import DGeoIp
from bmgeoip.interface.GeoIpSource import GeoIpSource


def csv_data(version=4, changes=None):
    row = dict.fromkeys(DGeoIp.COLUMNS, "")
    row.update(ip_version=str(version), start_ip="8.8.8.0", end_ip="8.8.8.255",
               country_code="CA", country="Canada", city="É, Example\nCity", zip="00123",
               latitude="43.25", longitude="-79.87", timezone="America/Toronto")
    if version == 6:
        row.update(start_ip="2606:4700::", end_ip="2606:4700::ff")
    row.update(changes or {})
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=DGeoIp.COLUMNS)
    writer.writeheader()
    writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def zipped(data, member=DGeoIp.MEMBER.format(version=4)):
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(member, data)
    return stream.getvalue()


class GeoIpSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.destination = self.directory / "ipv4.csv"
        self.destination.write_bytes(b"previous dataset")

    def download(self, data, version=4, source=None):
        with patch("bmgeoip.interface.GeoIpSource.urlopen", return_value=BytesIO(data)) as opened:
            (source or GeoIpSource()).download(version, self.destination)
        return opened

    def assert_preserved(self):
        self.assertEqual(self.destination.read_bytes(), b"previous dataset")
        self.assertEqual(list(self.directory.iterdir()), [self.destination])

    def test_downloads_both_families_and_preserves_csv_fields(self):
        for version in DGeoIp.VERSIONS:
            with self.subTest(version=version):
                data = csv_data(version)
                opened = self.download(zipped(data, DGeoIp.MEMBER.format(version=version)), version)
                opened.assert_called_once_with(DGeoIp.URL.format(version=version),
                                               timeout=DGeoIp.DOWNLOAD_TIMEOUT)
                self.assertEqual(self.destination.read_bytes(), data)
                row, = GeoIpSource().rows(self.destination, version)
                self.assertEqual(tuple(row), DGeoIp.COLUMNS)
                self.assertEqual(row["city"], "É, Example\nCity")
                self.assertEqual(row["zip"], "00123")
                self.assertEqual(list(self.directory.iterdir()), [self.destination])

    def test_custom_provider_and_new_destination(self):
        self.destination = self.directory / "new.csv"
        source = GeoIpSource(url="https://example.com/ipv{version}.zip", member="data.csv", timeout=7)
        opened = self.download(zipped(csv_data(), "data.csv"), source=source)
        opened.assert_called_once_with("https://example.com/ipv4.zip", timeout=7)
        self.assertEqual(self.destination.read_bytes(), csv_data())

    def test_progress_reports_bytes_and_validation_and_rejects_short_transfer(self):
        archive = zipped(csv_data())
        response = BytesIO(archive)
        response.headers = {'Content-Length': str(len(archive))}
        updates = []
        with patch('bmgeoip.interface.GeoIpSource.urlopen', return_value=response):
            GeoIpSource().download(4, self.destination,
                                   progress=lambda *values: updates.append(values))
        self.assertIn(('downloading', len(archive), len(archive)), updates)
        self.assertIn(('extracting', 0, None), updates)
        self.assertIn(('validating', 0, None), updates)
        self.destination.write_bytes(b'previous dataset')
        response = BytesIO(archive)
        response.headers = {'Content-Length': str(len(archive) + 1)}
        with patch('bmgeoip.interface.GeoIpSource.urlopen', return_value=response):
            with self.assertRaisesRegex(OSError, 'Incomplete'):
                GeoIpSource().download(4, self.destination)
        self.assert_preserved()

    def test_network_failures_preserve_existing_dataset(self):
        for error in (URLError("unavailable"), TimeoutError("timeout"),
                      HTTPError("https://example.com", 404, "missing", {}, None)):
            with self.subTest(error=error):
                with patch("bmgeoip.interface.GeoIpSource.urlopen", side_effect=error):
                    with self.assertRaises(type(error)):
                        GeoIpSource().download(4, self.destination)
                self.assert_preserved()

    def test_interrupted_transfer_preserves_existing_dataset(self):
        class InterruptedResponse(BytesIO):
            def read(self, size=-1):
                if self.tell():
                    raise OSError("Connection lost")
                return super().read(8)

        with patch("bmgeoip.interface.GeoIpSource.urlopen", return_value=InterruptedResponse(b"partial archive")):
            with self.assertRaises(OSError):
                GeoIpSource().download(4, self.destination)
        self.assert_preserved()

    def test_invalid_archives_preserve_existing_dataset(self):
        for data, error in ((b"not a zip", BadZipFile), (zipped(csv_data(), "other.csv"), KeyError),
                            (zipped(csv_data())[:-12], BadZipFile)):
            with self.subTest(error=error):
                with self.assertRaises(error):
                    self.download(data)
                self.assert_preserved()

    def test_bad_csv_preserves_existing_dataset(self):
        for data in (b"unexpected\nvalue\n", (",".join(DGeoIp.COLUMNS) + "\n").encode(),
                     csv_data() + b"4,8.8.8.0\n", csv_data() + b"\xff\n",
                     csv_data() + b'"unterminated', csv_data() + csv_data().split(b"\n", 1)[1].replace(b"4,", b"6,", 1)):
            with self.subTest(data=data):
                with self.assertRaises((ValueError, csv.Error)):
                    self.download(zipped(data))
                self.assert_preserved()

    def test_invalid_ranges_and_coordinates_are_rejected(self):
        for changes in ({"ip_version": "6"}, {"start_ip": "bad"},
                        {"start_ip": "8.8.8.255", "end_ip": "8.8.8.0"},
                        {"end_ip": "::1"}, {"latitude": "91"}, {"longitude": "-181"},
                        {"latitude": "nan"}, {"longitude": "inf"}, {"latitude": "text"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.download(zipped(csv_data(changes=changes)))
                self.assert_preserved()

    def test_missing_and_boundary_coordinates_are_allowed(self):
        for changes in ({"latitude": " ", "longitude": ""},
                        {"latitude": "90", "longitude": "-180"},
                        {"latitude": "-90", "longitude": "180"}):
            with self.subTest(changes=changes):
                self.download(zipped(csv_data(changes=changes)))
                self.assertEqual(next(GeoIpSource().rows(self.destination, 4))["latitude"], changes["latitude"])

    def test_invalid_versions_fail_before_network_access(self):
        with patch("bmgeoip.interface.GeoIpSource.urlopen") as opened:
            for version in (0, 5, "4", 4.0, True, None):
                with self.subTest(version=version):
                    with self.assertRaises(ValueError):
                        GeoIpSource().download(version, self.destination)
                    with self.assertRaises(ValueError):
                        list(GeoIpSource().rows(self.destination, version))
            opened.assert_not_called()
        self.assert_preserved()

    def test_invalid_provider_configuration_is_rejected(self):
        for options in ({"timeout": 0}, {"timeout": -1}, {"timeout": float("nan")},
                        {"timeout": float("inf")}, {"url": "file:///tmp/data.zip"},
                        {"url": "https:///missing-host"}, {"member": ""}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    GeoIpSource(**options)

    def test_failed_first_download_leaves_no_dataset(self):
        destination = self.directory / "new.csv"
        with patch("bmgeoip.interface.GeoIpSource.urlopen", return_value=BytesIO(b"bad")):
            with self.assertRaises(BadZipFile):
                GeoIpSource().download(4, destination)
        self.assertFalse(destination.exists())
        self.assert_preserved()
