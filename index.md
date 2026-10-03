---
title: Local GeoIP Service
author_profile: true
layout: single
---

![Logo](/pages/images/bmgeoip.png)

The **Bear & Moose GeoIP Project** provides an *easy-to-use* GeoIP service for your applications and for interactive lookups.

- BmGeoIP has simple `install.sh`, `upgrade.sh`, and `uninstall.sh` scripts.
- Downloads public geolocation data from [ipapi.is](https://ipapi.is/) on a configurable schedule.
- Stores records in an optimized MariaDB database.
- Provides a [web interface](/pages/images/web-interface.png) for interactive IP lookups at [https://localhost:54300](https://localhost:54300) and for configuring the download schedule.
- Accepts application lookup requests through **ZeroMQ** and **HTTP**.

## Project Documents

- [Server setup]({{ site.baseurl }}{% link pages/server.md %})
- [IP address lookup]({{ site.baseurl }}{% link pages/ip-address-lookup.md %})
- [BMGeoIP API]({{ site.baseurl }}{% link pages/api.md %})
- [Development]({{ site.baseurl }}{% link pages/development.md %})
- [GeoIP CSV retrieval (phase 1)]({{ site.baseurl }}{% link pages/geoip-source.md %})
- [Coding guidelines]({{ site.baseurl }}{% link pages/coding-guidelines.md %})
