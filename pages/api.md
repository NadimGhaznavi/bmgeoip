````markdown
---
title: BMGeoIP API
author_profile: true
layout: single
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

BMGeoIP provides HTTP (`54300`) and ZeroMQ (`54301`) lookup services. Both are unauthenticated and intended for a trusted LAN.

## HTTP

```sh
curl 'http://localhost:54300/api/lookup?ip=8.8.8.8'
```

Supply one IPv4 or IPv6 address. Replies contain `ip`, numeric `ip_version`, and `results`. No match returns an empty array.

| Status | Meaning |
| --- | --- |
| 200 | Lookup completed |
| 400 | Invalid request or address |
| 503 | Lookup data unavailable |

Errors return `{"error":"..."}`.

## ZeroMQ

Send one JSON frame using a REQ socket connected to `tcp://<server>:54301`:

```json
{
  "protocol_version": 1,
  "sender": "my-client",
  "target": "bmgeoip",
  "method": "lookup",
  "payload": {"ip": "8.8.8.8"}
}
```

Replies use the same envelope. Successful payloads contain `status: "ok"`, `ip`, `ip_version`, and `results`. Errors contain `status: "error"` and an `error` object with `code` and `message`.

Set client timeouts and recreate the REQ socket after a timeout.

## Result fields

Each matching record contains these fields, all strings:

`ip_version`, `start_ip`, `end_ip`, `continent`, `country_code`, `country`, `state`, `city`, `zip`, `timezone`, `latitude`, `longitude`, `accuracy`, `source`.

## Other HTTP endpoints

- `POST /api/download-schedule`: `{"enabled":true,"expression":"0 3 * * 0"}`
- `GET /status-messages`: recent activity
- `GET /api/data-status`: dataset progress
- `GET /health` and `/ready`: service checks

[Server setup]({{ site.baseurl }}{% link pages/server.md %})
````