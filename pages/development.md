````markdown
---
title: BMGeoIP Development
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Use a separate development MariaDB database and settings file.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B bmgeoip-server.py --host 127.0.0.1 \
  --state-dir /tmp/bmgeoip-dev --database-env /tmp/bmgeoip-dev.env \
  --zmq-endpoint tcp://127.0.0.1:54301
```

MariaDB tests require `BMGEOIP_TEST_DATABASE_ENV`; otherwise they are skipped.

[Coding guidelines]({{ site.baseurl }}{% link pages/coding-guidelines.md %}) · [Server setup]({