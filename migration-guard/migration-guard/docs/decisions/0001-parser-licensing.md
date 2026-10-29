# ADR 0001: PostgreSQL parser licensing

Status: **Decision pending founder and legal review**  
Date: 2026-10-29

## Context

MigrationGuard currently uses `pglast` for PostgreSQL parsing. PyPI identifies
the package license as `GPL-3.0-or-later`:
<https://pypi.org/project/pglast/>.

That license is a material risk for a proprietary commercial distribution.
This document records the options; it is not legal advice.

## Options

1. **Open-core/process separation**: publish the parser-dependent core under a
   GPL-compatible license and keep paid components separate. Legal counsel must
   confirm whether the proposed process boundary is sufficient.
2. **Replace pglast**: use a permissively licensed `libpg_query` binding or a
   Rust parser/core. Verify the binding's own license; the upstream project
   license alone is not sufficient.
3. **Commercial license**: ask the pglast author whether a commercial license
   is available and evaluate its cost and distribution terms.
4. **Continue pglast temporarily**: acceptable only for prototype/internal
   validation, not a paid closed-source release without legal approval.

## Recommendation

Choose option 2 as the default commercial path, while retaining the parser
port and conformance tests. Option 3 should be investigated in parallel if it
materially reduces migration risk. Do not market or distribute a closed-source
paid product containing pglast until the founder records a decision with legal
advice.

## Consequences

- All pglast imports remain isolated in `adapters/parser_pglast/`.
- The parser port must have conformance tests for statements, tokens, and
  source spans before any replacement is accepted.
- `THIRD_PARTY_LICENSES.md` and CI license checks remain required.
