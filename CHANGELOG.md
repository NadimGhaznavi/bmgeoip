---
title: Changelog
layout: single
permalink: /CHANGELOG/
---

## [Unreleased]

## [1.2.2] - 2026-10-03 @ 19:29

- Add a GitHub account link to the documentation's left author pane.

## [1.2.1] - 2026-10-03 @ 19:25

- Add a screenshot gallery covering the web interface and its main sections.
- Display CSV file update times in the browser's local timezone as `yyyy-mm-dd HH:MM`.

## [1.2.0] - 2026-10-03 @ 18:56

- Complete re-write of the website docs.
- Recover missing MariaDB credentials during upgrade: generate a private
  database.env, create the local BMGeoIP database/account if needed, reset the
  application password, and grant database access. Preserve existing credentials.

## [1.1.0] - 2026-10-03 @ 18:18

- Add the Rebuild Jekyll Site GitHub Pages workflow, based on AX3L's build and
  deployment workflow, with automatic builds on pushes to main and manual runs.

## [1.0.0] - 2026-10-03 @ 18:12

- Website homepage updates.

- Align storage and setup documentation with MariaDB, consolidate HTTP and ZMQ
  contracts in the API reference, and document all fourteen provider fields with
  a populated example. Clarify explicit legacy migration and installer limits.

- Main page rewrite.

- Move IP address lookup and ZeroMQ request documentation into separate guides,
  and name the ZeroMQ guide BMGeoIP ZMQ API.

- Split server setup and development into separate guides, linked from the
  documentation index.

- Add a modular ZMQ lookup worker on `tcp://0.0.0.0:54301`, using AX3L's
  versioned JSON envelope and the shared IPv4/IPv6 lookup interface. Report
  invalid requests and unavailable data, manage worker startup/shutdown with
  HTTP, and document the protocol and client timeouts.

## [0.4.1] - 2026-10-03 @ 11:11

- Fix IP lookup timeouts by indexing numeric range prefixes and matching packed
  endpoints in SQL. Migrate existing records at startup without downloading or
  reimporting unchanged CSVs; preserve all provider fields and overlapping matches.

## [0.4.0] - 2026-10-03 @ 11:00

- Add an IP Address Lookup form between CSV Data Files and Status Messages,
  with raw JSON in a nested Lookup Results box. Search local IPv4/IPv6 ranges,
  preserve all provider fields, and report invalid input and unavailable data.
- Rename the Dataset Progress panel to Dataset Status.

## [0.3.1] - 2026-10-03 @ 10:34

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
