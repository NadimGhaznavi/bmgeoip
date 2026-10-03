---
title: Coding Guidelines
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

Bear & Moose GeoIP should be easy to navigate, understand, and maintain. Keep the project
lean and build for the workflows that exist now. Prefer simple Markdown and
the shared theme's existing layouts to custom code or duplicated assets.

## Respect development and release ownership

The AI coding assistant is the lead developer and handles implementation,
checks, and documentation within the architecture and standards set by the
project owner. The project owner is the architect and release manager.
The assistant may perform Git operations and run release scripts as part of
the authorized workflow.

## Organize by responsibility

- `index.md` is the sole documentation root.
- `pages/` contains project guides and documentation images.
- `_config.yml` holds Jekyll settings and site-wide layout defaults.
- `scripts/` contains maintenance tooling.
- `bmgeoip/` contains Python code; `bmgeoip/constants/` holds project constants.
- `DBMGeoIP.VERSION` in `bmgeoip/constants/DBMGeoIP.py` holds the project version as a
  literal string.
- `CHANGELOG.md` records user-visible changes and releases.

The shared `NadimGhaznavi/minimal-mistakes` theme owns the site's presentation.
Keep GeoIP-specific settings in this repository. Introduce local layout or asset
overrides only when a requirement calls for them.

The repository currently contains the documentation site and project constants.
The planned service accepts IP addresses over ZMQ, returns location information,
runs under Linux systemd, and refreshes GeoIP data from a public provider on a
schedule. Add service modules, unit files, and tests as those responsibilities
are implemented; do not document planned components as existing code.

## Keep documentation focused

Keep `README.md` as a short project overview with a pointer to
[bmgeoip.osoyalce.com](https://bmgeoip.osoyalce.com), without duplicating navigation.
Every documentation page must be reachable by following links from `index.md`,
directly or through another reachable page. Update links when adding or moving
content.

Give each page YAML front matter with a lowercase `title` key and one clear
purpose. Use Jekyll's `link` tag for internal page links, prefixed with
`site.baseurl` as on the documentation index. Use fenced blocks for commands
and configuration examples, and tables for structured references.

Document implemented behavior and verified commands. Distinguish examples from
the current network configuration and identify incomplete or outdated records.
Keep credentials, tokens, and other secrets out of this public site.

## Make reviewable changes

Keep ZMQ request handling, GeoIP lookups, provider downloads, and service
lifecycle code separate as they are introduced. Validate IP addresses and
external configuration at the boundary. Define request and response formats,
including invalid input and unavailable lookup data, and document them alongside
the implementation. Let internal programming errors surface.

Use explicit timeouts for network operations. Validate downloaded GeoIP data
before replacing the active dataset, and preserve the last usable dataset when
a refresh fails. Keep provider URLs, refresh schedules, and data paths in
configuration rather than scattering them through application code.

When adding or changing service behavior, run the relevant Python checks and
cover lookup results, invalid requests, and refresh failures as appropriate.
Document verified setup and test commands when the service environment is
established. Service checks are separate from the GitHub Pages build.

Keep each change coherent. When moving a page, update incoming links and check
its generated URL. Preserve existing behavior unless the task calls for a change.
GitHub Pages builds the site. Do not add a Gemfile or require local Jekyll
builds. Keep generated site output out of source control.

Check YAML front matter and confirm that internal link targets exist. Verify
page titles, navigation, rendered tables, code blocks, and theme assets
when changing presentation. Report checks that could not be run.

## Update the changelog

Record meaningful changes under `## [Unreleased]` in `CHANGELOG.md`. For changes
with many details, add a `### Summary` explaining the problem and solution in
one or two sentences. Release tooling must update `DBMGeoIP.VERSION` and assign
the changelog version and timestamp. Before using `scripts/new-release.sh`,
verify that its version-file path and release messages match this project.
