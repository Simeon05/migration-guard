from pglast import ast
from pglast.parser import ParseError, parse_sql, scan

from migration_guard.ports.parser import (
    Command,
    ParseResult,
    ParserError,
    Statement,
    Token,
)


class PglastParser:
    def parse(self, sql: str) -> ParseResult:
        try:
            raw_statements = parse_sql(sql)
        except ParseError as error:
            raise ParserError(str(error)) from error

        statements: list[Statement] = []
        for raw_statement in raw_statements:
            node = raw_statement.stmt
            commands: tuple[Command, ...] = ()
            table: str | None = None
            if isinstance(node, ast.AlterTableStmt):
                table = node.relation.relname
                commands = tuple(
                    Command(
                        kind=command.subtype.name,
                        name=getattr(command, "name", None),
                    )
                    for command in node.cmds
                )

            statements.append(
                Statement(
                    kind=type(node).__name__,
                    table=table,
                    commands=commands,
                    start=max(raw_statement.stmt_location, 0),
                    length=raw_statement.stmt_len,
                )
            )
        return ParseResult(statements=tuple(statements))

    def tokenize(self, sql: str) -> tuple[Token, ...]:
        return tuple(
            Token(start=token.start, end=token.end + 1, name=token.name)
            for token in scan(sql)
        )
