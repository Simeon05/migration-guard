# Competitive baseline

Research verified 2026-10-29. Pricing and product scope change; re-check
before positioning or pricing decisions.

| Product | Verified capability | License/pricing | MigrationGuard opportunity |
|---|---|---|---|
| [Squawk](https://github.com/sbdchd/squawk) | PostgreSQL migration/SQL linter, configurable rules, CLI, GitHub integration, pre-commit, VS Code/language-server support. | Repository shows Apache-2.0 and MIT license files; open source. | Compete on application compatibility windows, schema replay without a database, and evidence-backed safe plans rather than statement linting alone. |
| [Atlas](https://github.com/ariga/atlas) | Schema-as-code and versioned migrations across many databases; 50+ safety analyzers; schema-aware linting and CI integrations. | Atlas documents `migrate lint` as an Atlas Pro feature requiring login; public pricing was not treated as verified here. | Stay PostgreSQL-focused and local-first: replay migration history without customer DB credentials, index application references, and provide a smaller auditable evidence model. |
| [Bytebase](https://www.bytebase.com/sql-review/) | SQL linting, schema-aware semantic rules, policy approvals, GitOps/change management, rollback and governance workflows. | [Pricing](https://www.bytebase.com/pricing/) lists Community free, Pro at $20/user/month, and Enterprise contact pricing. | Avoid competing as a broad governance platform; focus on migration correctness during rolling deploys and compatibility with the application code actually running. |
| Eugene | Mentioned in project planning as a migration linter, but no primary source was verified during this baseline pass. | Unknown. | Do not make claims about Eugene until its repository, rules, license, and pricing are verified. |

## Positioning conclusion

A PG001-style linter is not differentiated by itself. MigrationGuard should
lead with compatibility-window analysis, application blast radius, schema
replay, safe multi-step plans, and Proof Mode. These claims require measured
precision and verified PostgreSQL behaviour before being used in marketing.
