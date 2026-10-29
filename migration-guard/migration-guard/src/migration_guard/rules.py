import re
from dataclasses import dataclass

from pglast import ast
from pglast.parser import parse_sql


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    title: str
    file: str
    line: int
    evidence: str
    reason: str
    recommendation: str


def detect_dropped_columns(sql: str, file: str) -> list[Finding]:
    """Return findings for columns removed by ALTER TABLE statements.

    Parsing is intentionally allowed to raise pglast's ParseError so callers
    can decide how to present invalid SQL to users.
    """
    findings: list[Finding] = []
    statements = parse_sql(sql)

    for raw_statement in statements:
        statement = raw_statement.stmt
        if not isinstance(statement, ast.AlterTableStmt):
            continue

        table = statement.relation.relname
        statement_start = max(raw_statement.stmt_location, 0)
        statement_end = statement_start + raw_statement.stmt_len
        statement_sql = sql[statement_start:statement_end]
        line = sql.count("\n", 0, statement_start) + 1

        for command in statement.cmds:
            if command.subtype.name != "AT_DropColumn":
                continue

            column = command.name
            match = re.search(
                r"\bDROP\s+COLUMN\b",
                statement_sql,
                re.IGNORECASE,
            )
            if match:
                line = (
                    sql.count(
                        "\n",
                        0,
                        statement_start + match.start(),
                    )
                    + 1
                )
            findings.append(
                Finding(
                    rule_id="PG001",
                    severity="high",
                    title="Dropping a table column",
                    file=file,
                    line=line,
                    evidence=f"DROP COLUMN {column}",
                    reason=(
                        f"Dropping {table}.{column} may break application queries "
                        "or dependents that still reference the column."
                    ),
                    recommendation=(
                        "Verify all application and database references before "
                        "removing the column, then deploy the removal separately."
                    ),
                )
            )

    return findings
