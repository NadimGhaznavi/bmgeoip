---
title: IP Address Lookup
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Enter one IPv4 or IPv6 address and click Look Up. The form sits between CSV Data
Files and Status Messages. Lookup Results shows the complete JSON response,
including all fourteen original provider fields as strings. The form shows raw
error responses too. Without JavaScript, submitting opens the JSON endpoint directly.
The browser uses a 30-second request timeout.

The [BMGeoIP API reference]({{ site.baseurl }}{% link pages/api.md %}) defines the
shared lookup behavior, lists all provider fields, shows a populated response, and
documents HTTP and ZeroMQ requests and errors.

## Lookup storage

Each request opens and closes its own MariaDB connection with a read-only session,
separate from dataset workers. The `GeoIp` table uses an index on the IP family
and each range's smallest enclosing network prefix to find candidates, then
compares stored binary endpoints in SQL. This avoids converting and scanning every
provider range for each request.

Startup creates the MariaDB tables if needed and imports existing or newly
downloaded CSVs. Unchanged CSVs skip import using committed metadata. Range keys,
endpoints, provider records, and import metadata are replaced in one InnoDB
transaction per family, so committed records remain usable after a failed refresh.
Lookups can return HTTP 503 or ZMQ `data_unavailable` until their family is imported.

Existing SQLite deployments require an explicit migration into MariaDB; startup
does not migrate the old file automatically. See
[database setup and migration]({{ site.baseurl }}{% link pages/server.md %}#database-configuration).
