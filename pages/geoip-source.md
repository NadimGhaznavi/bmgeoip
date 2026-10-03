````markdown
---
title: GeoIP CSV Retrieval
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Download public [ipapi.is datasets](https://github.com/ipapi-is/ipapi) without credentials:

```python
from pathlib import Path
from bmgeoip.interface.GeoIpSource import GeoIpSource

directory = Path("/tmp/bmgeoip-data")
directory.mkdir(parents=True, exist_ok=True)
source = GeoIpSource()
source.download(4, directory / "ipv4.csv")
source.download(6, directory / "ipv6.csv")
```

Downloads are validated before replacing existing files. Failures preserve the previous dataset.

[Server setup]({{ site.baseurl }}{% link pages/server.md %}) · [API reference]({{ site.baseurl }}{% link pages/api.md %})
````