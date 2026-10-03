---
title: Changelog
layout: single
permalink: /CHANGELOG/
---

## [Unreleased]

- Add a configurable GeoIP source interface for IPv4/IPv6 CSV retrieval from
  ipapi.is, with full validation, atomic file replacement, failure preservation,
  and retrieval tests and documentation.

- Add a CMDB-style systemd web server on port 54300 with Jinja2 templates,
  health endpoints, a dedicated service account, installation tooling, and server tests.

- Adapt coding guidelines to the GeoIP project and link them from the documentation index.

- Establish the Bear & Moose GeoIP project documentation site and logo.
- Use the project logo as the site favicon.
- Add a project version constant and changelog to prepare for release tooling.
