---
title: Changelog
layout: single
permalink: /CHANGELOG/
---

## [Unreleased]

- Rename the Downloads navigation link and page title to GeoIP.
- Display CSV data file sizes in MB with two decimal places.
- Remove the redundant “Web interface running” text from the download page header.

## [0.3.0] - 2026-10-03 @ 10:17

- Add a CMDB-style Status Messages box with Timestamp, Source, and Message
  columns, live updates, and a shared bounded history covering startup,
  scheduled refreshes, dataset processing, schedule changes, and failures.

- Restore the theme's narrow left author sidebar on all documentation pages
  by applying the single layout and author profile defaults to pages.
- Download missing IPv4/IPv6 CSVs automatically at server startup, show live
  download/validation/import progress, and import validated records into SQLite
  after startup and scheduled downloads. Preserve previous records on failed
  imports and skip unchanged CSVs on restart.
- Add CMDB-style database mechanics and domain interfaces, DAL coding guidance,
  and an isolated `--state-dir` option for development.

## [0.2.0] - 2026-10-03 @ 09:10

- Add CMDB-style upgrade and uninstall scripts. Upgrades reuse installation and
  preserve state; uninstallation removes the service, application, CSVs, settings,
  logs, service account crontab, Linux account, and group.

## [0.1.2] - 2026-10-03 @ 08:30

- Capture and verify the expected schedule-save error log in server tests so
  simulated permission failures do not print an unexplained traceback.

## [0.1.0] - 2026-10-03 @ 08:22

- Fix release tooling to update BMGeoIP's version constant and use BMGeoIP
  names in help and error messages.

- Match the documentation and download interface to the logo with forest green
  backgrounds, cream text, and golden yellow and orange accents.

- Add a CMDB-style CSV download schedule page in dark blue and teal, with enabled
  and cron controls, persistent service-account cron scheduling, validated IPv4/IPv6
  downloads, and CSV paths, modification times, and sizes. Update installation
  permissions and document scheduling and download logs.

- Add a configurable GeoIP source interface for IPv4/IPv6 CSV retrieval from
  ipapi.is, with full validation, atomic file replacement, failure preservation,
  and retrieval tests and documentation.

- Add a CMDB-style systemd web server on port 54300 with Jinja2 templates,
  health endpoints, a dedicated service account, installation tooling, and server tests.

- Adapt coding guidelines to the GeoIP project and link them from the documentation index.

- Establish the Bear & Moose GeoIP project documentation site and logo.
- Use the project logo as the site favicon.
- Add a project version constant and changelog to prepare for release tooling.
