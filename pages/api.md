---
title: BMGeoIP API
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

BMGeoIP serves HTTP on `0.0.0.0:54300` and ZeroMQ on
`tcp://0.0.0.0:54301` by default. Both interfaces have no authentication and are
intended for a trusted LAN. They share the same MariaDB lookup interface.
For installation and service management, see
[server setup]({{ site.baseurl }}{% link pages/server.md %}); for the browser form
and storage behavior, see
[IP address lookup]({{ site.baseurl }}{% link pages/ip-address-lookup.md %}).

## Shared lookup contract

Supply one IPv4 or IPv6 address as a string. Surrounding whitespace is trimmed;
the response contains the normalized address. Hostnames, CIDR prefixes, IPv6 zone
IDs, and empty or invalid addresses are rejected.

Matches include both range endpoints. Overlapping or nested ranges return every
matching record, ordered by numeric start and end addresses. A successful lookup
with no match returns `results: []`. An unimported IP family or unavailable lookup
storage is an error, rather than a successful empty result. HTTP and ZMQ listeners
remain available during dataset initialization.

| Response field | Type | Meaning |
| --- | --- | --- |
| `ip` | string | Normalized requested address. |
| `ip_version` | integer | Address family: `4` or `6`. |
| `results` | array of objects | All matching provider records. |

### Provider fields

Each result contains exactly these fourteen original CSV fields, all returned as
strings. Empty values remain `""`; Unicode, IPv6 text, and postal-code leading zeros
are preserved. The record's `ip_version` is a string, unlike the response's integer
`ip_version`. BMGeoIP retains provider values without enriching them or converting
coordinates and accuracy to JSON numbers.

| Field | Meaning |
| --- | --- |
| `ip_version` | Provider address family (`"4"` or `"6"`). |
| `start_ip` | Inclusive start of the provider range. |
| `end_ip` | Inclusive end of the provider range. |
| `continent` | Provider continent value. |
| `country_code` | Provider country code. |
| `country` | Country name. |
| `state` | State or region. |
| `city` | City or locality. |
| `zip` | Postal code. |
| `timezone` | Provider timezone value. |
| `latitude` | Latitude as provider text. |
| `longitude` | Longitude as provider text. |
| `accuracy` | Provider accuracy value, retained as text. |
| `source` | Provider source value. |

## HTTP API

All JSON replies use `Content-Type: application/json`. GET routes also accept HEAD,
which returns the same status and headers without a response body. Replies use
`Cache-Control: no-store`. Requests have a ten-second socket timeout.

### IP lookup

```sh
curl --max-time 30 'http://127.0.0.1:54300/api/lookup?ip=192.0.2.42'
```

`GET /api/lookup` requires exactly one `ip` query parameter. Missing, duplicate,
or extra parameters are invalid. URL-encode IPv6 addresses and whitespace when
constructing a query string.

The following populated HTTP 200 reply uses synthetic documentation data; it is
not a claim about the provider's current geolocation of this address:

```json
{
  "ip": "192.0.2.42",
  "ip_version": 4,
  "results": [
    {
      "ip_version": "4",
      "start_ip": "192.0.2.0",
      "end_ip": "192.0.2.255",
      "continent": "NA",
      "country_code": "CA",
      "country": "Canada",
      "state": "Ontario",
      "city": "Example City",
      "zip": "00123",
      "timezone": "America/Toronto",
      "latitude": "43.25",
      "longitude": "-79.87",
      "accuracy": "",
      "source": "documentation-example"
    }
  ]
}
```

| HTTP status | Meaning | Example body |
| --- | --- | --- |
| 200 | Lookup completed; `results` may be empty. | `{"ip":"::1","ip_version":6,"results":[]}` |
| 400 | Invalid query parameters or IP address. | `{"error":"Provide one ip query parameter."}` |
| 503 | Family not imported or lookup storage unavailable. | `{"error":"IPv6 lookup data is not available yet."}` |

HTTP errors contain a single `error` string; they do not use the ZMQ error object
or its `status` and `code` fields. Error messages describe the failure and can vary.

### Download schedule

`POST /api/download-schedule` requires `Content-Type: application/json`, a
`Content-Length` between 1 and 4096 bytes, and no `Transfer-Encoding` header.
The body must contain exactly `enabled` (boolean) and `expression` (a valid
five-field cron string, at most 255 characters, without newlines). Whitespace in
the expression is normalized. Cron uses the server's local timezone.

```json
{"enabled": true, "expression": "0 3 * * 0"}
```

HTTP 200 returns the saved settings:

```json
{"schedule": {"enabled": true, "expression": "0 3 * * 0"}}
```

Invalid input returns HTTP 400. If an `Origin` header is supplied, its scheme must
be HTTP or HTTPS and its authority must equal `Host`; otherwise the save returns
HTTP 403. Storage or cron failures return HTTP 503. Each error has an `error` string.
Settings are restored if writing the crontab fails.

### Status and health

| Route (GET/HEAD) | HTTP 200 response |
| --- | --- |
| `/status-messages` | Array of up to 1,000 objects with `timestamp` (UTC ISO 8601 string), `source` (module string), and `message` (string); absent history returns `[]`. |
| `/api/data-status` | Object with `phase` (string), `version` (integer `4`/`6` or `null`), `completed` (number), `total` (number or `null`), and `message` (string). Progress counts bytes during downloads and records during validation/import. |
| `/health` | `{"status":"ok","service":"bmgeoip-server"}` |
| `/ready` | `{"status":"ready","service":"bmgeoip-server"}`; web readiness, independent of GeoIP data availability. |

Dataset phases are `waiting`, `checking`, `downloading`, `extracting`, `validating`,
`importing`, `ready`, and `error`. Unreadable status history or dataset progress
returns HTTP 503 with an `error` string. Unknown paths return HTTP 404 with
`{"error":"Not found."}`.

## ZeroMQ API

The service runs a serial ZMQ REP worker alongside HTTP, using AX3L's modular
message-envelope and transport pattern. Send exactly one UTF-8 JSON frame from
a REQ socket. The version 1 request envelope is:

```json
{
  "protocol_version": 1,
  "sender": "example-client",
  "target": "bmgeoip",
  "method": "lookup",
  "payload": {"ip": "8.8.8.8"}
}
```

`sender` must be a nonempty string; `target` accepts `"bmgeoip"` or `null`.
The method must be `"lookup"` and the payload must contain exactly one `ip`
string. Address validation and matching use the shared lookup contract above.
A successful reply uses the same envelope,
with `sender: "bmgeoip"`, `target` set to the request sender, the original method,
and this payload:

```json
{
  "status": "ok",
  "ip": "8.8.8.8",
  "ip_version": 4,
  "results": []
}
```

The empty array above illustrates no matching range. For matches, `results` contains
records with the fourteen fields listed above; the populated HTTP example shows the
same result structure. Only ZMQ adds `status: "ok"` and the message envelope. Errors have `{"status":"error","error":{"code":"invalid_request","message":"..."}}`
in the payload. `invalid_request` covers malformed JSON/envelopes, unsupported
protocol versions, multiple frames, wrong methods or targets, and invalid IPs.
`data_unavailable` covers a missing database, an unimported family, and unavailable
lookup storage. Malformed envelopes receive method `"error"` and target `null`.
Expected request and data errors leave the worker available for the next request.
Internal programming errors and transport failures surface to the main service;
systemd restarts a failed process.

For example, using the installed virtual environment:

```python
import zmq

with zmq.Context() as context, context.socket(zmq.REQ) as socket:
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.SNDTIMEO, 15000)
    socket.setsockopt(zmq.RCVTIMEO, 15000)
    socket.connect("tcp://127.0.0.1:54301")
    socket.send_json({
        "protocol_version": 1, "sender": "example-client", "target": "bmgeoip",
        "method": "lookup", "payload": {"ip": "8.8.8.8"},
    })
    print(socket.recv_json())
```

Set explicit client timeouts; after a timeout, close the REQ socket and create a
new one before sending another request. The worker polls for shutdown every
100 milliseconds, uses a 15-second send timeout, and closes its socket and context
on shutdown. Each lookup opens and closes its own read-only database connection
inside the worker thread, separate from HTTP and dataset workers. Both listeners
are available while datasets initialize; lookups can return `data_unavailable`
until their family is ready. SIGTERM and Ctrl-C stop both listeners.
