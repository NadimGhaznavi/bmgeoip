---
title: GeoIP CSV Retrieval
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Phase 1 provides `bmgeoip.interface.GeoIpSource.GeoIpSource`, using the same
[ipapi.is public datasets](https://github.com/ipapi-is/ipapi) as MyCount.
It downloads an IPv4 or IPv6 ZIP archive and saves its CSV member as a UTF-8
file. The interface uses Python's standard library and requires no credentials.

## Usage

Run from the repository root with Python 3.11 or later:

```python
from pathlib import Path
from bmgeoip.interface.GeoIpSource import GeoIpSource

directory = Path("/tmp/bmgeoip-data")
directory.mkdir(parents=True, exist_ok=True)
source = GeoIpSource()
source.download(4, directory / "ipv4.csv")
source.download(6, directory / "ipv6.csv")
```

`download(version, destination)` accepts integer versions 4 and 6 and a file
path whose parent directory already exists. It returns `None` after success.
It streams downloads and extraction through temporary files beside the
destination, validates the entire CSV, then atomically replaces that file.
Temporary files are removed after success or failure. Each family is published
independently; the scheduled runner attempts each family separately.

Validation requires the expected fourteen-column header, complete rows, at least
one range, valid ordered IP endpoints matching the requested family, and optional
latitude/longitude within their geographic bounds. Nested ranges are permitted.
`rows(path, version)` yields validated dictionaries with all fourteen fields
preserved as text, including empty values, Unicode, and postal-code leading zeros.
Consumers must exhaust the iterator to validate the whole file.

Network, filesystem, ZIP, encoding, and CSV errors propagate to the caller;
invalid dataset content and unsupported versions raise `ValueError`. A failed
download or validation preserves an existing destination. No automatic retries
are performed.

## Configuration and verification

Provider defaults live in `bmgeoip/constants/DGeoIp.py`. The constructor accepts
`url`, `member`, and `timeout` overrides. URL and ZIP-member templates may contain
`{version}`. URLs must use HTTP or HTTPS; the default uses HTTPS. The timeout
defaults to 120 seconds and must be finite and positive. It limits blocking
network operations, rather than the total duration of a download.

```sh
python3 -B -m unittest discover -s tests -p 'test_geoip_source.py' -v
```

Tests use small in-memory archives and simulated network responses, covering
both families, malformed data, interrupted transfers, and preservation of an
existing dataset. They do not download the public datasets.

The [server download schedule]({{ site.baseurl }}{% link pages/server.md %})
uses this interface from an independent cron runner. Database import, IP lookup,
and ZMQ clients are later phases.
