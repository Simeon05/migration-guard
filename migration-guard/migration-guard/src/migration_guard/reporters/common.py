from collections.abc import Iterable

from migration_guard.model import Finding


def ordered_findings(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda finding: (finding.file, finding.line, finding.column, finding.rule_id),
    )
