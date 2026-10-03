```markdown
---
title: Coding Guidelines
---

[Documentation index]({{ site.baseurl }}{% link index.md %})

These are BMGeoIP's development standards. MUST identifies a requirement;
SHOULD identifies a default whose exceptions need a concrete reason.

## Ownership and scope

The project owner is the architect and release manager. The AI assistant is
the lead developer, responsible for implementation, verification, and documentation.

Changes MUST follow the owner's architecture and the requested scope.
Preserve existing behavior unless the task requires changing it.
Do not expand a task into an unrelated refactor.

ANY edits to files outside of the repository MUST be approved by the user.

Git operations and release scripts may be used within the authorized workflow.

## Architecture

- Each component MUST have a clear responsibility and resource owner.
- Transport, domain rules, persistence, background workflows, and presentation
  MUST remain separate.
- Dependencies SHOULD use narrow interfaces or injected callables.
- Construct and connect resources at explicit application entry points.
- Reuse sound distributed patterns where they provide clear ownership or reuse.
- Introduce abstractions and services only for demonstrated requirements.

Where an authoritative model or specification is adopted, implementations MUST
preserve its semantics. Verify inheritance, relationships, and cardinalities
against that source. Do not substitute an ad-hoc schema for the accepted model.

CWM-based work MUST use OMG CWM 1.1 as its authority. CWM is not required for
unrelated application data.

## Project structure

| Location | Responsibility |
| --- | --- |
| `index.md` | Sole documentation root |
| `pages/` | Guides and documentation images |
| `_config.yml` | Jekyll configuration |
| `scripts/` | Maintenance and release tooling |
| `bmgeoip/constants/` | Project constants |
| `bmgeoip/interface/` | Database and external-service interfaces |
| `bmgeoip/activity/` | Background workflows |
| `bmgeoip/server/` | HTTP handling and service lifecycle |
| `bmgeoip/zmq/` | Message envelopes and transport |
| `CHANGELOG.md` | User-visible changes |

`DBMGeoIP.VERSION` MUST remain a literal string in
`bmgeoip/constants/DBMGeoIP.py`.

The shared theme owns site presentation. Local overrides SHOULD be added only
for a specific requirement.

## Data access

- `DbMgr.py` MUST own connection, cursor, batch, and transaction mechanics.
- Domain interfaces such as `GeoIpDb.py` MUST own application SQL and schema.
- HTTP handlers, templates, and ZMQ transport MUST NOT execute SQL.
- Each worker MUST own and close its database connection.
- Connections MUST NOT be shared between request threads or background workers.
- External values MUST use bound parameters. Dynamic identifiers MUST come
  from trusted project constants.
- Query results MUST be materialized and cursors closed before returning.

Use MariaDB through PyMySQL and InnoDB transactions. Keep database provisioning
separate from application schema creation.

Preserve all fourteen provider fields as text. Validate CSVs while streaming
and insert bounded batches. Replace each IP family's records and import metadata
in one transaction. Failed imports MUST preserve the previous usable records.

Keep schema creation outside import transactions. Skip unchanged CSVs using
committed import metadata.

## ZMQ and external interfaces

Transport MUST accept configuration and injected handlers without importing
database or workflow implementations.

Envelope validation, routing, and domain validation MUST have distinct owners.
HTTP and ZMQ MUST use the same authoritative lookup interface.

Document implemented request and response contracts, including invalid input
and unavailable data. Preserve protocol compatibility; incompatible changes
require an explicit version or migration.

- Network operations MUST have explicit timeouts.
- Sockets MUST remain within their owning thread.
- Owned resources MUST be closed; borrowed contexts MUST remain available.
- Long-running work MUST execute outside request handlers.
- Mutating requests MUST NOT be automatically retried without defined
  server-side idempotency.
- PUB/SUB notifications MUST NOT be described as guaranteed delivery.

Validate downloads before replacing datasets. Keep endpoints, paths, and
schedules in configuration.

Expected input and availability errors MUST produce defined responses.
Programming errors and failed workers MUST surface to the service supervisor.

## Documentation

Public documentation MUST be short, direct, and task-focused.

Include only what readers need to install, use, or develop the software.
Omit implementation narration, repeated explanations, development history,
and speculative features. Put detailed contracts in one reference and link to it.

- Keep `README.md` to a brief overview and website link.
- Every page MUST be reachable from `index.md`.
- Give each page one purpose and YAML front matter with a `title` key.
- Use `site.baseurl` and Jekyll's `link` tag for internal page links.
- Use fenced examples and tables where useful.
- Document verified behavior and commands.
- Credentials and secrets MUST NOT appear in the public site.

## Verification and review

Run checks appropriate to the change. Database changes MUST cover initial import,
IPv4/IPv6, unchanged-file handling, refresh replacement, and rollback after
malformed input. Service changes MUST cover relevant success and failure paths.

Review architectural changes with `$review-architecture` when available.
These standards apply whether or not the skill is installed.

Reviews MUST identify concrete evidence, consequences, and bounded corrections.
Trace a normal operation and a relevant failure path. Distinguish defects from
preferences; passing tests alone does not establish architectural correctness.

Check documentation front matter, link targets, and navigation.
Inspect rendered output when presentation changes.

GitHub Pages builds the site. Do not add a Gemfile, require local Jekyll builds,
or commit generated site output. Report checks that could not be run.

## Changelog and releases

Record meaningful changes under `## [Unreleased]` in `CHANGELOG.md`.
Keep entries focused on user-visible outcomes.

Release tooling MUST update `DBMGeoIP.VERSION` and assign the changelog version
and timestamp. Verify project paths and release messages before running
`scripts/new-release.sh`.
```