from bisect import bisect_right
from dataclasses import dataclass
import re

from migration_guard.adapters.parser_pglast import PglastParser
from migration_guard.model import Finding


@dataclass(frozen=True)
class Suppression:
    rule_id: str
    line: int
    reason: str | None


@dataclass(frozen=True)
class SuppressionResult:
    findings: list[Finding]
    suppressed: list[Suppression]


_DIRECTIVE = re.compile(
    r"^\s*--\s*migrationguard-ignore\s+(?P<rules>[A-Z0-9_, ]+)"
    r"(?:\s+reason=\"(?P<reason>[^\"]*)\")?"
    r"(?:\s+expires=(?P<expires>\S+))?\s*$"
)


def _line(source: str, offset: int) -> int:
    starts = [0]
    starts.extend(index + 1 for index, char in enumerate(source) if char == "\n")
    return bisect_right(starts, offset)


def _directives(sql: str) -> list[Suppression]:
    parser = PglastParser()
    directives: list[Suppression] = []
    for token in parser.tokenize(sql):
        if token.name != "SQL_COMMENT":
            continue
        match = _DIRECTIVE.match(sql[token.start : token.end])
        if not match:
            continue
        reason = match.group("reason")
        for rule_id in match.group("rules").replace(",", " ").split():
            directives.append(Suppression(rule_id, _line(sql, token.start), reason))
    return directives


def apply_suppressions(
    sql: str, findings: list[Finding], *, require_reason: bool = False
) -> SuppressionResult:
    directives = _directives(sql)
    remaining: list[Finding] = []
    used: list[Suppression] = []
    for finding in findings:
        match = next(
            (
                directive
                for directive in directives
                if directive.rule_id == finding.rule_id
                and directive.line <= finding.line <= directive.line + 1
            ),
            None,
        )
        if match is None:
            remaining.append(finding)
            continue
        if require_reason and not match.reason:
            raise ValueError(f"suppression for {match.rule_id} requires a reason")
        used.append(match)
    return SuppressionResult(findings=remaining, suppressed=used)
