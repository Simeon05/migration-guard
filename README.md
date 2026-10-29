# MigrationGuard

MigrationGuard is a local-first PostgreSQL migration risk checker. It parses
migration SQL with PostgreSQL-aware AST and scanner data, then reports risky
operations with source evidence, reasons, and safer alternatives.

> Early prototype: the rule engine and CLI are still evolving. Do not treat
> findings as a replacement for database review or a production test plan.

## Install

Use a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
```

For development:

```sh
python -m pip install ".[dev]"
python -m pytest -q
lint-imports
```

## Check migrations

```sh
migration-guard check examples/drop_email.sql
migration-guard check examples --format json
migration-guard check examples --format sarif
```

Exit codes are `0` for no findings, `1` for findings at or above the failure
threshold, and `2` for parse, configuration, or usage errors.

## Current rules

- PG001: drop column
- PG002: drop table/schema and truncate
- PG003: rename table/column
- PG004: change column type
- PG005: set `NOT NULL`
- PG006: create index without `CONCURRENTLY`
- PG007: concurrent index creation inside a transaction
- PG008: foreign-key or CHECK constraint without `NOT VALID`
- PG009: direct UNIQUE or PRIMARY KEY constraint creation
- PG010: add column with a default
- PG011: drop index without `CONCURRENTLY`
- PG012: locking operation without `lock_timeout`

Each rule has a page under `docs/rules/` describing its rationale, safer
alternative, and limitations.

## Configuration and suppression

Use `.migrationguard.toml` for the target PostgreSQL version, failure
threshold, rule overrides, paths, and suppression policy. Inline suppressions
are comment-only directives:

```sql
-- migrationguard-ignore PG001 reason="removal approved after compatibility window"
ALTER TABLE users DROP COLUMN legacy_email;
```

Suppressions should explain why a finding is safe to ignore. Static analysis
does not know table size, live traffic, application references, or deployment
order unless that context is supplied by future schema and application
analysis features.

## Design principles

- PostgreSQL-aware parsing; no regex detection over SQL.
- Deterministic output with source evidence.
- Local-first operation with no production database connection.
- Conservative severity and explicit uncertainty.
- Structured text, JSON, and SARIF output for CI integration.

## Development status

The next major capabilities are schema replay from migration history or a
user-provided `pg_dump --schema-only` snapshot, PostgreSQL Proof Mode, and
application compatibility analysis. These are not implemented yet.
