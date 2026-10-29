# MigrationGuard - Complete Build Blueprint

Audience: the AI engineer (and the founder) building MigrationGuard. Read together with `SKILL.md`, which defines how to behave. This document defines WHAT to build and WHY. Where this document and reality disagree (a library changed, a Postgres behaviour differs), verify against primary sources and record the correction in `docs/decisions/`.

Status labels used below: **[BUILT]** exists today, **[NEXT]** immediate, **[PLANNED]** committed roadmap, **[EXPLORE]** needs validation with real users before building.

---

## 1. Vision, positioning and differentiation

### 1.1 One-sentence pitch
MigrationGuard tells a team, before merge, whether a PostgreSQL migration is safe to deploy against the application that is actually running, and shows the safe way to do it if not.

### 1.2 The gap in the market
Existing tools lint SQL statements in isolation (is this statement dangerous?). Teams actually get hurt by a different question: **is this migration safe given the application version that is live while it runs, the tables it touches, and the order in which things deploy?** Plain statement linting is table stakes and is already served by free and paid tools. MigrationGuard must be built around the deeper question.

### 1.3 Six differentiation pillars (every feature must serve at least one)

| # | Pillar | What it means | Why it is hard to copy |
|---|--------|---------------|------------------------|
| 1 | **Compatibility Window analysis** | Classifies each migration as backward-compatible, forward-compatible, both, or breaking relative to the app version before and after deploy (expand/contract awareness) | Requires modelling deploy order, not just SQL |
| 2 | **Application blast radius** | Finds code (SQL strings, ORM models, queries) that still references a column/table/index the migration removes, renames or retypes, with file:line and confidence | Needs code scanning + ORM adapters, not just a SQL parser |
| 3 | **Safe Plan generator** | For a risky change, outputs a complete multi-step plan (migration files, ordering, deploy notes, rollback) not just "don't do that" | Needs correct per-version Postgres knowledge and templates |
| 4 | **Schema replay without a database** | Rebuilds schema state by replaying migrations (plus optional snapshot) so findings are contextual ("table has 2 FKs, 3 indexes, created earlier in this PR") with zero credentials | Needs a faithful DDL interpreter |
| 5 | **Proof Mode** | Every rule's claim can be demonstrated on an ephemeral local Postgres (Docker) by capturing locks and rewrites; users can run it on their own migration against synthetic data | Builds trust; turns opinions into evidence |
| 6 | **Agent guardrail + audit trail** | An MCP server/API so AI coding agents check migrations they write before committing; signed "migration attestations" give auditors evidence of review (SOC 2 change-management) | Timely distribution channel and an enterprise purchase reason |

Supporting qualities: local-first privacy, deterministic evidence-based findings, version-aware rules, very low false-positive rate.

### 1.4 Target users
1. **Backend engineer** writing migrations (wants fast, accurate, local feedback).
2. **Reviewer / tech lead** (wants a PR summary with risk, blast radius and safe plan).
3. **Platform/DBA/SRE** (wants org-wide policy, audit, no surprises).
4. **Compliance owner** (wants evidence that risky changes are reviewed).

### 1.5 Non-goals (for now)
No connection to production databases; no executing migrations on customer databases; no credentials collection; no non-Postgres dialects; no "AI decides if safe"; no web dashboard before 5+ design partners ask for one; no schema-management/migration-runner features (we complement Flyway/Alembic/Django/Rails/Prisma/Atlas, we do not replace them).

---

## 2. System architecture

### 2.1 Layered design

```
+--------------------------------------------------------------------------+
|  Delivery surfaces                                                       |
|  CLI | GitHub Action | GitLab CI | pre-commit | VS Code | MCP server |   |
|  Hosted API/bot (later)                                                  |
+---------------------------------+----------------------------------------+
                                  |  (all call the same Analysis API)
+---------------------------------v----------------------------------------+
|  Application layer: Orchestrator                                         |
|  discover files -> load config -> run pipeline -> apply policy ->        |
|  suppressions -> report                                                  |
+---------------------------------+----------------------------------------+
                                  |
+---------------------------------v----------------------------------------+
|  Core engine (pure library, no I/O, no network, no CLI deps)             |
|                                                                          |
|  Parser port --> Statement model --> Schema replay --> Rule engine -->   |
|  Finding model --> Compat-window classifier --> Safe-plan generator      |
|                                       ^                                  |
|                      App-reference index (from code scanner)             |
+---------------------------------+----------------------------------------+
                                  |
+---------------------------------v----------------------------------------+
|  Adapters (replaceable, isolated)                                        |
|  Parser adapter(s) | Migration-format adapters (raw SQL, Flyway, Alembic,|
|  Django, Rails, Prisma, Liquibase SQL) | Code scanners (tree-sitter)     |
|  | Reporters (text/json/sarif/markdown) | Proof runner (Docker)          |
+--------------------------------------------------------------------------+
```

Key architectural rules:

1. **Hexagonal / ports-and-adapters.** The core depends only on interfaces (`Parser`, `MigrationSource`, `CodeIndex`, `Reporter`). Anything touching the filesystem, subprocesses, network, Docker or a specific parser library lives in an adapter.
2. **Parser is a port.** The GPL-licensed `pglast` (confirmed GPL-3.0-or-later on PyPI) must sit behind a `Parser` interface so it can be replaced (permissive libpg_query binding, Rust core, commercial licence) without touching rules. This is both a legal and technical requirement. See 2.4.
3. **Core is pure and deterministic.** Same inputs produce byte-identical outputs. No clocks, randomness or environment reads inside core.
4. **One Analysis API, many frontends.** `analyze(request) -> AnalysisResult` is the only entry point. CLI, Action, MCP server and any hosted service are thin wrappers.
5. **Everything versioned.** Rule IDs, finding schema, config schema and attestation schema carry explicit versions.

### 2.2 Pipeline (data flow)

1. **Discover** migration files (adapter per framework; ordering rules per tool). Resolve which migrations are "new in this change" (git diff or explicit list) versus "history".
2. **Load config** (`.migrationguard.toml`), schema snapshot (optional), table hints (optional), code index config (optional).
3. **Parse** each file into `Statement` objects with exact spans (start/end line, column, byte offsets).
4. **Replay** history to build `SchemaState` *before* the new migrations; then step statement by statement, recording `SchemaDelta` and the state at each point.
5. **Evaluate rules** per statement with context `(statement, schema_before, schema_after, target_version, transaction_context, hints, config)`.
6. **Enrich**: attach blast radius (query code index), compute compatibility-window class, compute lock timeline/accumulation across the whole migration/transaction.
7. **Generate Safe Plans** for findings that have a template.
8. **Apply policy**: severity overrides, suppressions (audited), fail thresholds.
9. **Report** in requested formats; optionally sign an attestation.

### 2.3 Core data models (define as immutable dataclasses / pydantic models; no behaviour)

- `SourceSpan(file, start_line, start_col, end_line, end_col, start_byte, end_byte)`
- `Statement(kind, raw_span, ast_node_ref, in_transaction: bool|unknown, index_in_file)`
- `SchemaState(tables: {QualifiedName: Table}, indexes, constraints, sequences, enums, views, functions, extensions, pg_version)`; `Table(columns, constraints, indexes, partitioning, created_in: SourceRef|None, size_hint)`
- `Finding(rule_id, severity, confidence, title, message, why_it_matters, evidence, span, lock: LockInfo|None, rewrites_table: bool|unknown, compat: CompatClass, blast_radius: [Reference], safe_plan: SafePlan|None, docs_url, fingerprint)`
- `fingerprint`: stable hash of (rule_id, normalised statement, table/column) so findings survive line moves and can be baselined.
- `LockInfo(mode, relation, duration_class: instant|scan|rewrite|unbounded, blocks: [reads|writes|both], version_notes)`
- `CompatClass`: `backward_compatible | forward_compatible | both | breaking | unknown`.
- `Reference(file, span, kind: raw_sql|orm_model|query_builder|string_match, confidence, snippet_hash)`
- `SafePlan(steps: [Step(order, title, sql, phase: pre_deploy|deploy|post_deploy, notes)], rollback, caveats)`
- `AnalysisResult(findings, summary(stats, unanalysed_statements, suppressions), metadata(tool_version, ruleset_hash, target_version), attestation|None)`

### 2.4 Parser port and licensing strategy

- Interface: `Parser.parse(sql: str, *, version: PgVersion) -> ParseResult(statements, errors)`; `Parser.tokenize(sql)` for token-accurate spans.
- Stage A (validate the idea): keep `pglast` for speed of development. Do not distribute a closed-source product with it.
- Stage B (before any paid release): choose one and record an ADR: (a) open-source the core under GPL-3.0 and sell separate proprietary components that talk to it via a defined process boundary (get legal advice on whether that is sufficient); (b) swap to a permissively licensed libpg_query binding (libpg_query itself is BSD-licensed; verify the licence of any binding) or a Rust core; (c) negotiate a commercial licence with the pglast author.
- Contain the blast radius now: no `pglast` imports outside `adapters/parser_pglast/`; a CI import-linter rule enforces this.
- Conformance test suite for the `Parser` port so any replacement must pass the identical spans/AST-shape tests.

---

## 3. Schema replay engine [PLANNED]

Goal: know "what does the schema look like right now" with no database.

Inputs (in priority order): (1) migration history replayed in order; (2) optional `schema.sql` snapshot (`pg_dump --schema-only`) as a baseline, supplied by the user; (3) optional hints.

Requirements:
- Interpret the DDL subset that matters: CREATE/ALTER/DROP TABLE, columns, constraints (PK, FK, UNIQUE, CHECK, NOT NULL, defaults), indexes (incl. partial, unique, concurrently), sequences/identity, enums/domains, views/materialized views (for dependency detection), partitioning, extensions, `CREATE TABLE AS`, `ALTER TABLE ... RENAME`.
- Unknown or unsupported statements mark the state `partially_known`; rules then lower confidence instead of guessing.
- Dependency graph: which views/functions/triggers/FKs/indexes depend on which columns; powers "DROP COLUMN would break view X" findings.
- Track `created_in_this_change`: a table created in the same PR is empty in production, so most lock/rewrite risk disappears. This eliminates a major class of false positives.
- Optional **hints file** (`migrationguard.hints.toml`): per-table `rows`, `size_gb`, `write_rate`, `hot = true`. Used to scale severity and runtime estimates. Never fetched from a live DB by the tool; the user may generate it from their own monitoring.
- Tests: replay golden files; round-trip against a real Postgres in CI (apply migrations in Docker, compare `pg_dump --schema-only` structure with the replayed state for the supported subset).

---

## 4. Rule engine design

### 4.1 Rule interface
```
class Rule(Protocol):
    meta: RuleMeta                       # id, name, category, default_severity, since_version, pg_versions, status
    def check(self, stmt: Statement, ctx: RuleContext) -> Iterable[Finding]
```
- `RuleMeta.status`: `experimental | stable | deprecated`. Only `stable` rules fail CI by default.
- `RuleContext`: `schema_before`, `schema_after`, `target_version`, `in_transaction`, `hints`, `config`, `cumulative_locks` (locks already held earlier in the same transaction).
- Rules are pure, side-effect free, and unit-testable with a tiny builder DSL (`sql("...") -> findings`).
- Registry with discovery via entry points; each rule documented at `docs/rules/PGxxx.md` (enforced by a test that fails if a rule has no doc page).

### 4.2 Cross-statement ("whole-migration") analysis
Some risks only exist across statements; implement as `MigrationRule`s over the whole file/transaction:
- **Lock accumulation**: several `ACCESS EXCLUSIVE` operations in one transaction hold locks until commit; flag total lock-hold exposure.
- **Lock queue hazard**: even a metadata-only `ACCESS EXCLUSIVE` statement can cause an outage by queueing behind a long-running transaction and blocking everything behind it. Flag missing `lock_timeout` and recommend retry strategy.
- **DDL + large DML in one transaction.**
- **CONCURRENTLY inside a transaction** (will error) and tool-specific transaction wrapping (Flyway/Alembic/Django wrap by default; adapters must supply the real transactional context).
- **Order hazards**: dropping/renaming before dependants are updated within the same migration set.

### 4.3 Severity and confidence model
- Severity = f(lock mode, duration class, blocks, table hints, compat class, blast radius). Document the function in `docs/severity.md`; it must be deterministic and explainable ("HIGH because: ACCESS EXCLUSIVE + table rewrite + table marked hot").
- Confidence = `high | medium | low` reflecting how complete the schema knowledge and reference search were. Low-confidence findings never fail CI by default.
- Always show *why* a severity was assigned and *what would lower it*.

### 4.4 Version matrix
Maintain `data/pg_behaviour.yaml`, a machine-readable table of behaviours by PG major version (e.g., constant-default ADD COLUMN fast path from 11, SET NOT NULL scan skipping from 12, `REINDEX CONCURRENTLY` from 12, `DETACH PARTITION CONCURRENTLY` from 14), each with a docs link and the date verified. Rules read from this table instead of hard-coding versions. A scheduled CI job reminds maintainers to re-verify against each new Postgres release.

### 4.5 Rule catalog (initial target: 25 stable rules before charging)

Every item below must be re-verified against the PostgreSQL docs for the supported versions before implementation; the "typical lock" column is a starting hypothesis, not a source of truth.

| ID | Detects | Typical lock / effect | Safe alternative |
|----|---------|----------------------|------------------|
| PG001 | DROP COLUMN | brief ACCESS EXCLUSIVE; app break | expand/contract: stop reads/writes, deploy, then drop |
| PG002 | DROP TABLE / TRUNCATE / DROP SCHEMA / CASCADE | data loss; ACCESS EXCLUSIVE | rename-then-delay-drop, backups |
| PG003 | RENAME COLUMN / TABLE | brief lock; app break | add new + dual-write + backfill + switch |
| PG004 | ALTER COLUMN TYPE | usually rewrite under ACCESS EXCLUSIVE; some changes (e.g., widening varchar) are cheap | add column, backfill in batches, swap |
| PG005 | SET NOT NULL | full scan under ACCESS EXCLUSIVE (scan can be skipped on PG12+ with a validated CHECK) | CHECK ... NOT VALID, VALIDATE, then SET NOT NULL |
| PG006 | CREATE INDEX without CONCURRENTLY | blocks writes | CREATE INDEX CONCURRENTLY (outside txn) |
| PG007 | CONCURRENTLY inside transaction | statement fails | disable txn wrapper for that file |
| PG008 | ADD FOREIGN KEY / CHECK without NOT VALID | long lock + scan | NOT VALID then VALIDATE CONSTRAINT |
| PG009 | ADD UNIQUE / PRIMARY KEY directly | builds index under heavy lock | unique index concurrently, then ADD CONSTRAINT USING INDEX |
| PG010 | ADD COLUMN with volatile default (or any default on PG<11) / serial / identity on existing table | table rewrite | add nullable, backfill in batches, then constrain |
| PG011 | DROP INDEX without CONCURRENTLY | ACCESS EXCLUSIVE | DROP INDEX CONCURRENTLY |
| PG012 | Locking DDL without `lock_timeout` | lock queue outage | SET lock_timeout + retry |
| PG013 | VACUUM FULL / CLUSTER / non-concurrent REINDEX / REFRESH MATERIALIZED VIEW | long ACCESS EXCLUSIVE | concurrent variants / pg_repack-style tools |
| PG014 | NOT NULL column added without default | fails on non-empty table | nullable first, backfill, constrain |
| PG015 | UPDATE/DELETE without WHERE; unbatched backfill | long transaction, bloat, replication lag | batched backfill job |
| PG016 | ALTER TYPE ... ADD VALUE transactional caveats | new value unusable until commit | separate migration |
| PG017 | DDL mixed with large DML in one transaction | lock held for whole duration | split |
| PG018 | Drop/alter column used by a view, function, trigger, index, constraint (schema-aware) | failure or silent break | update dependants first |
| PG019 | Dropped/renamed object still referenced in application code (app-aware) | runtime errors | expand/contract |
| PG020 | Duplicate/redundant index; FK without supporting index | perf | indexing guidance |
| PG021 | SET LOGGED/UNLOGGED, tablespace moves | rewrite | schedule maintenance window |
| PG022 | Changing default/ownership/privileges that app roles rely on | access break | grant/revoke ordering |
| PG023 | Partition operations (ATTACH/DETACH) | scan / lock variance | CHECK constraint first / CONCURRENTLY detach (PG14+) |
| PG024 | Extension/collation/encoding changes affecting indexes | index invalidation | reindex plan |
| PG025 | Idempotency: missing IF [NOT] EXISTS where re-run is plausible | failed deploy retries | guard clauses |

Each rule ships with: doc page, positive/negative tests, version-matrix entry, Proof Mode scenario (where applicable), safe-plan template (where applicable), known false-positive/false-negative notes.

---

## 5. Compatibility Window analysis [PLANNED, flagship]

Concept: during a rolling deploy, **old app code and new schema coexist** (and sometimes new code with old schema). A migration is only safe if it is compatible with the app version(s) running at that moment.

Model: classify each change as
- **Expand** (additive: new nullable column, new table, new index) - backward-compatible;
- **Contract** (removal) - safe only after code stops using it;
- **Breaking** (rename, type change, NOT NULL on existing column) - needs multi-step.

Outputs:
- Per migration: `backward_compatible | forward_compatible | both | breaking`.
- Deploy-order guidance: "run migration BEFORE deploy" vs "AFTER deploy" vs "split into 3 steps".
- If the code index shows the old column is still referenced in the *current* branch, a contract step is classified `breaking` with evidence.
- Config option `deploy_model = "migrate-before-deploy" | "migrate-after-deploy" | "blue-green"` changes classification.

This is the feature that justifies the product's price; invest in correctness and clear explanation.

---

## 6. Application blast-radius analysis [PLANNED]

- **Code scanner adapter** using tree-sitter grammars (Python, TypeScript/JavaScript, Ruby, Java/Kotlin, Go, C#, PHP; start with two) plus a SQL-in-strings extractor.
- **ORM adapters** that map model fields to columns/tables (Django models, SQLAlchemy, Rails ActiveRecord schema, Prisma schema, TypeORM/Sequelize, GORM, Hibernate/JPA annotations). Start with the two most requested by design partners.
- Build a `CodeIndex`: map `(table, column) -> [Reference]` with `kind` and `confidence`:
  - `orm_model` / parsed SQL AST reference = high;
  - identifier appears in a raw SQL string parsed successfully = high;
  - plain-text identifier match = low (shown as "possible", never fails CI by default).
- Handle noise: ignore comments, tests (configurable), migrations directory, generated code, vendored directories; honour `.gitignore`.
- Report: "`users.email` is referenced in 14 places (9 high confidence). First 5 shown." Each with file:line and snippet.
- Limits must be stated in output: dynamic SQL, reflection, and other services reading the DB cannot be seen. Never imply completeness.
- Performance budget: index a 500k-LOC repo in under 60 seconds with caching (content-hash incremental).

---

## 7. Safe Plan generator [PLANNED]

For rules with templates, emit a runnable plan instead of a warning:

```
Plan: remove users.legacy_flag safely (3 steps)
 1. [deploy N]    Stop reading/writing the column in app code. (14 references listed)
 2. [deploy N+1]  Migration: ALTER TABLE users DROP COLUMN legacy_flag;  (after N is fully rolled out)
 3. Rollback note: data is not recoverable after step 2; take a backup/snapshot first.
```
- Plans are generated from templates parameterised by schema state and target version, never free-form AI text.
- Output formats: Markdown (PR comment), JSON, and optional generated migration files (`--emit-plan-files`) the user reviews and commits themselves.
- `--fix` is limited to mechanically safe rewrites (e.g., add `CONCURRENTLY`, add `NOT VALID`); anything involving data movement is plan-only.
- Every template is validated in Proof Mode.

---

## 8. Proof Mode [PLANNED, optional component]

`migration-guard verify <migration>` spins up an **ephemeral local Postgres** (Docker/Podman, user's machine only) at the target version, seeds synthetic data (configurable row counts via hints), applies the migration with lock/rewrite tracing, and reports observed locks, duration, rewrite detection (relfilenode change), and whether concurrent reads/writes were blocked. It compares observed behaviour with the static prediction.

Uses:
1. Our own CI: every rule's claim is proven per supported PG version.
2. Users: "show me" evidence for sceptical reviewers.
3. Calibration: measures prediction errors and feeds the precision dashboard.

Security: never accepts a production connection string; container has no network, no mounts beyond a temp dir, resource limits, auto-removed, pinned image digests. Clearly labelled as a simulation with synthetic data.

---

## 9. Policy-as-code and configuration

`.migrationguard.toml` (validated against a published JSON Schema; unknown keys are errors):
```
[core]
target_version = 15
fail_on = "high"
deploy_model = "migrate-before-deploy"

[rules]
PG001 = { severity = "high" }
PG012 = { enabled = true, require = "lock_timeout<=5s" }

[paths]
migrations = ["db/migrations/**/*.sql"]
exclude    = ["db/legacy/**"]

[code]
roots = ["src", "app"]
orm = ["django"]

[suppress]
require_reason = true
max_age_days = 90
```
- **Org policy file** (shared repo or URL, pinned by hash) that teams inherit and can only tighten, not loosen, unless allowed.
- **Declarative custom rules** (data-only, e.g. "no `ALTER TABLE` on tables tagged `hot` without `lock_timeout`") evaluated by the engine. **No arbitrary-code plugins** in default/hosted modes (see Security); a local Python plugin API may exist behind an explicit `--allow-plugins` flag.
- **Suppressions**: inline `-- migrationguard-ignore PG001 reason="..." expires=2026-12-31`; baseline file of fingerprints for adopting the tool on an existing repo without a wall of findings; expired suppressions fail.
- **Environment tags**: rules can vary by table tags (`hot`, `pii`, `ledger`).

---

## 10. Interfaces and integrations

1. **CLI** (thin): `check`, `explain`, `rules`, `init`, `verify`, `plan`, `baseline`, `attest`, `doctor`. Exit codes `0/1/2`, deterministic ordering, `NO_COLOR` support, `--format text|json|sarif|markdown|junit`.
2. **GitHub Action** (first-class): runs on PR, posts one updating summary comment (not spam), uploads SARIF to code scanning, annotates lines, sets a check status. Least-privilege token permissions, pinned action SHAs.
3. **GitLab / Bitbucket / Azure DevOps** equivalents via generic CI container + report conversions.
4. **pre-commit** hook and **VS Code extension** (inline diagnostics via LSP; build the LSP server once, reuse for other editors).
5. **MCP server**: tools `check_migration(sql|path)`, `explain_finding(id)`, `propose_safe_plan(finding)`. Lets AI coding agents self-check migrations they generate. Read-only by design; no file writes, no network, no shell.
6. **Migration-tool adapters**: Flyway/Liquibase (SQL), Alembic, Django (via `sqlmigrate`), Rails (structure.sql / SQL output), Prisma (`migration.sql`), Atlas, Goose, dbmate, node-pg-migrate, Knex. Adapters supply file ordering and **transaction-wrapping semantics**, which change rule results.
7. **Library API** (Python first; consider Rust core + bindings later).
8. **Hosted service** [EXPLORE]: org dashboard, trend of risk, policy management, attestation storage, Slack notifications. Only after validated demand.

---

## 11. Security architecture

### 11.1 Principles
Least privilege, local-first, no secrets, deny-by-default, defence in depth, verifiable supply chain, honest disclosure.

### 11.2 Threat model (STRIDE-style summary; maintain `docs/security/threat-model.md`)

| Threat | Example | Mitigation |
|--------|---------|------------|
| Malicious input file | Crafted SQL/huge file to crash or hang the parser | Size and time limits, resource caps, fuzz testing, parser run with timeouts (subprocess/worker isolation for the hosted mode), never `eval` |
| Malicious repo config/plugin | PR adds `.migrationguard.toml` or plugin that executes code in CI | Data-only config; no code plugins by default; on `pull_request` from forks run with read-only token and no secrets; never run untrusted plugins |
| Path traversal / symlinks | Config points outside repo; symlink to `/etc/passwd` | Resolve paths, confine to repo root, refuse symlinks that escape |
| Output injection | Evidence text containing Markdown/HTML/ANSI escapes poisoning PR comments or terminals | Escape/sanitise all rendered text per format; strip control characters; SARIF/JSON encoded via serialisers only |
| Supply-chain compromise | Malicious dependency/release | Pinned and hashed dependencies, `pip-audit`/OSV scans, dependency review in PRs, minimal deps, SBOM (CycloneDX/SPDX), Sigstore-signed releases, SLSA-style provenance, trusted publishing to PyPI, 2FA, protected branches, signed commits/tags |
| CI abuse | Over-permissive Action token, `pull_request_target` misuse | Document and ship least-privilege permissions; pinned action SHAs; never check out untrusted code with write tokens |
| Secret leakage | SQL containing credentials or PII (seed data, `CREATE ROLE ... PASSWORD`) echoed into reports/logs | Secret-pattern redaction in evidence output; PG rule flagging plaintext passwords in migrations; telemetry never includes SQL |
| Proof Mode escape | Malicious migration run in container | No network, dropped capabilities, read-only FS aside from temp, non-root user, resource limits, pinned image digests, clear warning |
| Hosted multi-tenancy (if built) | Cross-tenant data access | Tenant isolation at data layer, per-tenant encryption keys, row-level security, authz tests, rate limiting, audit logs, SSRF-safe webhooks |
| Attestation forgery | Fake "reviewed" evidence | Signed attestations (Sigstore/keyless or org key), include tool version, ruleset hash, input hashes, timestamp from a trusted source |

### 11.3 Secure development lifecycle
- Secure-coding checklist in PR template; mandatory review for parser/IO/config code.
- Static analysis (`ruff` security rules, `bandit`, CodeQL), secret scanning, dependency scanning, container scanning (if Docker image).
- Fuzzing (Hypothesis, Atheris) of tokenizer, location helper and config loader; corpus of malformed SQL kept in the repo.
- Security regression tests for each fixed vulnerability.
- `SECURITY.md` with a coordinated disclosure policy, security contact, response SLAs; publish advisories (GitHub Security Advisories) and CVEs when applicable.
- Annual third-party penetration test once a hosted component exists; consider SOC 2 Type I then II when selling to enterprises.

### 11.4 Privacy and compliance
- Default posture: nothing leaves the user's machine. Telemetry is opt-in, anonymous, aggregate (rule IDs fired, durations, tool version), documented in `PRIVACY.md`, and can be disabled with one flag/env var. Never collect SQL, table or column names, file paths or repo names.
- If a hosted service stores data: data-processing agreement, GDPR obligations (the founder is EU-based), data residency options, retention limits, deletion on request, sub-processor list.
- Publish a short "How we handle your SQL" page; it is a sales asset.

### 11.5 Licensing and IP hygiene
- Decide the parser licensing path (2.4) first; keep `THIRD_PARTY_LICENSES.md` generated in CI with an allow-list (permissive licences) and a block-list (GPL/AGPL in the proprietary distribution).
- Contributor Licence Agreement or DCO if accepting outside contributions to an open-core product.
- Trademark search for the name and domain before investing in branding.

---

## 12. Performance, scalability and reliability

- Targets: parse+analyse 1,000 migration files (10 MB SQL) in under 10 seconds on a laptop; incremental mode analyses only changed files plus dependants; cache parsed ASTs by content hash.
- Memory-bounded streaming for very large files (e.g., big `INSERT` dumps): detect and skip data statements, count them in the summary.
- Deterministic parallelism (stable ordering after merge).
- Graceful degradation: parse failure in one file does not hide findings from others, but exit code reflects the error.
- Benchmarks tracked in CI with regression thresholds.

---

## 13. Testing and quality strategy

1. **Unit tests** per rule (positive, near-miss negative, comments, strings, quoting, schema-qualified names, multi-command statements, suppression).
2. **Golden tests** for reporters (text/JSON/SARIF/Markdown) using snapshot testing.
3. **Location accuracy tests** (CRLF, Unicode, tabs, dollar quotes, multiple statements per line).
4. **Schema replay tests** and Postgres round-trip comparisons.
5. **Corpus-based precision/recall**: a labelled corpus of real-world-style migrations (anonymised, licence-clean); CI computes per-rule precision and recall and blocks promotion of a rule to `stable` below threshold (suggest >= 95% precision).
6. **Proof Mode integration tests** on the supported PG matrix (e.g., 13-17) verifying lock/rewrite claims.
7. **Property/fuzz tests** for parsers/tokenizers/config.
8. **Mutation testing** on rules periodically.
9. **Packaging tests**: build wheel, install in clean venv on Linux/macOS/Windows, run CLI without `PYTHONPATH`.
10. **Docs tests**: every rule has a doc page; every code example in docs is executed.
11. **Dogfooding**: run the tool in its own CI against its own example migrations.

---

## 14. Repository structure, tooling and release

```
migration-guard/
  src/migration_guard/
    core/{model,engine,schema,rules,compat,plan,policy}/
    ports/                # Parser, MigrationSource, CodeIndex, Reporter protocols
    adapters/{parser_pglast,migrations_*,code_*,reporters,proof}/
    api.py                # analyze()
    cli/                  # thin
    mcp_server/
  data/pg_behaviour.yaml
  docs/{rules,decisions,security,competitors.md,launch-checklist.md,severity.md}
  tests/{unit,golden,corpus,integration,fuzz,packaging}
  examples/
  .github/workflows/      # ci, release, codeql, scorecards
  pyproject.toml  SECURITY.md  PRIVACY.md  LICENSE  THIRD_PARTY_LICENSES.md  CHANGELOG.md
```
- Tooling: `uv` or `pip-tools` with hashes, `ruff`, `mypy --strict` (core), `pytest`, `import-linter` (enforce layering and the parser-port boundary), `pre-commit`, `towncrier`/Keep-a-Changelog, SemVer.
- CI: lint, type-check, unit, golden, corpus metrics, packaging matrix, security scans, docs build. Release: tag -> build -> SBOM -> sign -> publish via trusted publishing -> GitHub release with notes.
- Distribution: PyPI package, `pipx` install, Docker image, single-file binary (consider PyInstaller/Nuitka or a Rust core), Homebrew tap, GitHub Marketplace Action.
- Version policy: stable rule IDs; deprecation window of two minor versions; changelog lists any finding changes (so CI failures after upgrade are explainable). Provide `--ruleset-version` pinning for reproducibility.

---

## 15. Product experience details (what makes it feel premium)

- Finding output includes: severity, rule ID, exact line/column, evidence, **lock level and duration class**, **why it matters**, **blast radius**, **compatibility class**, **safe plan**, and a one-line "how to suppress with a reason".
- A PR summary comment with: overall verdict, a risk table, a lock timeline ("this migration holds ACCESS EXCLUSIVE on `orders` for the duration of statements 2-5"), and collapsible details.
- Clear language about uncertainty ("depends on table size; add a hint to refine").
- `explain PG004` produces a teaching-quality page; link every finding to it.
- Fast: first result in under 1 second for a single file.
- Great errors: parse errors show the offending line with a caret.

---

## 16. Commercial model [EXPLORE - validate with design partners]

- **Open-core suggestion** (confirm against the licensing decision): Free: CLI, core rules (PG001-PG017), text/JSON/SARIF, pre-commit, GitHub Action basics. **Team** (paid): schema replay + hints, blast-radius analysis, compatibility window, Safe Plans, PR bot, policy-as-code, baselines, MCP server. **Enterprise**: org policy, attestations and audit export, SSO/SAML, self-hosted/air-gapped, support SLA, security review pack.
- Pricing hypotheses to test (do not assume): per-repo or per-developer monthly; annual contracts for enterprise. Interview before setting numbers.
- Go-to-market: publish deep, accurate content (Postgres lock cheat-sheet, "migration postmortems", rule explainers); targeted communities (Postgres, Rails/Django/Prisma ecosystems, platform engineering); open-source credibility; comparison pages; free scan of a public repo as a hook; MCP/agent angle (AI-generated migrations are a growing risk surface).
- Metrics: activation (first successful check in CI), weekly active repos, findings acted on vs suppressed (precision proxy), time-to-first-value, paid conversion, churn reasons.
- Validation plan: 5-10 design partners; for each, run on their real migration history and report what it would have caught; ask "what would you pay for" and "what blocked adoption".

---

## 17. Roadmap with exit criteria

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M0 Foundation fix [NEXT] | accurate spans, packaging works without `PYTHONPATH`, 2 regression tests green, parser port + import-linter, licensing ADR, competitor doc | clean-install CI green; all location tests pass; ADR merged |
| M1 Reliable engine | rule API, severity/confidence model, JSON + SARIF, suppression/baseline, config schema, PG002-PG012 | each rule documented and tested; corpus precision measured |
| M2 Proven rules | Proof Mode in CI for rule claims; version matrix; PG013-PG017; experimental->stable gating | every stable rule has a verified claim for PG13-17 |
| M3 Context | schema replay engine, dependency graph, "created in this change" suppression, hints file, PG018 | replay round-trip passes; measurable drop in false positives |
| M4 Differentiators v1 | Safe Plan generator for top 6 rules; compatibility window classifier; GitHub Action PR comment | design partners confirm plans are correct and useful |
| M5 App-aware | code index + 2 ORM/language adapters; blast radius; PG019 | blast-radius precision measured on partner repos |
| M6 Agent + audit | MCP server; signed attestations; org policy | agents can self-check migrations; auditors accept evidence format |
| M7 Commercial launch | docs site, pricing, licensing complete, security page, SBOM/signing, support process | launch checklist 100%; >=3 paying design partners |
| M8 Scale [EXPLORE] | hosted dashboard, more ORMs/languages, SSO | demand proven by partners |

---

## 18. Risks and mitigations

| Risk | Likelihood/impact | Mitigation |
|------|-------------------|------------|
| GPL parser blocks commercial distribution | High / High | parser port + ADR now; swap or relicense before paid release |
| Crowded market; "just another linter" | High / High | build pillars 1-4 early; validate with users; clear comparison docs |
| False positives erode trust | High / High | precision-first, confidence levels, corpus metrics, schema context |
| Postgres behaviour misstated | Medium / High | version matrix with doc links; Proof Mode verification; expert review |
| Scope creep (dashboard, multi-DB) | High / Medium | explicit non-goals; milestone exit criteria |
| App-aware analysis over-promises | Medium / High | confidence labels; stated limits; never fail CI on low confidence |
| Solo-founder bandwidth | High / Medium | narrow scope; automate quality gates; use AI under `SKILL.md` discipline; seek design partners/co-maintainers |
| Supply-chain or vulnerability incident | Low / High | section 11 controls; fast disclosure process |
| Competitors copy features | Medium / Medium | depth in compatibility-window + blast radius; speed; trust and docs quality |

---

## 19. Definition of done (any feature)

1. Acceptance criteria written first; tests added and passing (real output shown).
2. Docs updated (rule page, config reference, changelog).
3. Verified from a clean install; no `PYTHONPATH` hacks.
4. Static analysis, type check, security scans clean; licences checked for any new dependency.
5. Findings carry correct spans and escaped output; JSON/SARIF schema valid.
6. False-positive scenarios identified and tested.
7. Performance budget not regressed.
8. Self-review checklist from `SKILL.md` completed.

---

## 20. First tasks for the AI builder (copy/paste order)

1. Run the full test suite including the two regression tests; paste results. Do not assume they pass.
2. Introduce the `Parser` port and move all `pglast` usage into `adapters/parser_pglast/`; add `import-linter` to enforce it.
3. Replace regex-based location logic with parser offsets and a tested offset-to-line/column helper; one finding per `DROP COLUMN` command.
4. Fix packaging; add clean-install CI (Linux + macOS + Windows).
5. Write `docs/decisions/0001-parser-licensing.md` and `docs/competitors.md`; present options to the founder for a decision.
6. Define the `Finding`, `LockInfo`, `SourceSpan`, `Severity/Confidence` models and JSON schema v1; add the JSON and SARIF reporters.
7. Implement suppression (inline + baseline) and the config schema.
8. Create `data/pg_behaviour.yaml` and the rule doc template; then implement PG002 and PG003 test-first.
9. Stand up the Docker-based Proof Mode harness for test-time verification of lock claims, starting with PG001, PG005, PG006.
10. Begin the schema replay engine with `CREATE TABLE`, `ALTER TABLE ADD/DROP COLUMN`, and index tracking.

At the end of each task report: what changed, real evidence it works, what remains unverified, and the next most valuable step.