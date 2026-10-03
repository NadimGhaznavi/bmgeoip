---
title: Local GeoIP Service
author_profile: true
layout: single
---

![Logo](/pages/images/bmgeoip.png)

The **Bear & Moose GeoIP Project** has a web interface running as a Linux
systemd service on port 54300. The planned GeoIP service will accept IP addresses
over ZMQ, return location information, and refresh public GeoIP data on a schedule.

## Project guides

- [Coding guidelines]({{ site.baseurl }}{% link pages/coding-guidelines.md %})
- [Server setup and development]({{ site.baseurl }}{% link pages/server.md %})
- [GeoIP CSV retrieval (phase 1)]({{ site.baseurl }}{% link pages/geoip-source.md %})
