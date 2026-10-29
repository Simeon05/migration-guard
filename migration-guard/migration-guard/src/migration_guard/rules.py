from bisect import bisect_right

from migration_guard.adapters.parser_pglast import PglastParser
from migration_guard.model import Finding
from migration_guard.ports.parser import Parser, Token


def _line_and_column(source: str, offset: int) -> tuple[int, int]:
    """Convert a parser character offset to a one-based line and column.

    pglast exposes scanner and statement offsets in Python string coordinates.
    Keeping the conversion here means Unicode characters, CRLF newlines, and
    tabs are handled consistently for every finding.
    """
    if offset < 0 or offset > len(source):
        raise ValueError(f"offset {offset} is outside the source")

    line_starts = [0]
    line_starts.extend(
        index + 1 for index, character in enumerate(source) if character == "\n"
    )
    line_index = bisect_right(line_starts, offset) - 1
    return line_index + 1, offset - line_starts[line_index] + 1


def _drop_column_spans(
    sql: str, tokens: tuple[Token, ...], statement_start: int, statement_end: int
):
    """Yield exact source spans for DROP COLUMN token sequences."""
    statement_tokens = [
        token
        for token in tokens
        if statement_start <= token.start < statement_end
    ]
    for index, token in enumerate(statement_tokens):
        if token.name != "DROP" or index + 1 >= len(statement_tokens):
            continue
        if statement_tokens[index + 1].name != "COLUMN":
            continue

        end_index = index + 1
        if (
            end_index + 2 < len(statement_tokens)
            and statement_tokens[end_index + 1].name == "IF_P"
            and statement_tokens[end_index + 2].name == "EXISTS"
        ):
            end_index += 2
        column_index = end_index + 1
        if column_index >= len(statement_tokens):
            continue

        column_token = statement_tokens[column_index]
        yield token.start, column_token.end


def detect_dropped_columns(sql: str, file: str) -> list[Finding]:
    """Return findings for columns removed by ALTER TABLE statements.

    Parsing is intentionally allowed to raise pglast's ParseError so callers
    can decide how to present invalid SQL to users.
    """
    findings: list[Finding] = []
    parser: Parser = PglastParser()
    parse_result = parser.parse(sql)
    tokens = parser.tokenize(sql)

    for statement in parse_result.statements:
        if statement.kind != "AlterTableStmt":
            continue

        table = statement.table
        statement_start = statement.start
        statement_end = statement_start + statement.length

        drop_spans = iter(
            _drop_column_spans(sql, tokens, statement_start, statement_end)
        )
        for command in statement.commands:
            if command.kind != "AT_DropColumn":
                continue

            column = command.name
            try:
                start, end = next(drop_spans)
            except StopIteration as error:
                raise ValueError("could not locate DROP COLUMN command tokens") from error
            line, _column = _line_and_column(sql, start)
            findings.append(
                Finding(
                    rule_id="PG001",
                    severity="high",
                    title="Dropping a table column",
                    file=file,
                    line=line,
                    evidence=sql[start:end],
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
